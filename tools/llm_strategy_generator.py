import os
import sys
import json
import csv
import logging
from typing import List, Dict, Any, Optional
try:
    from pydantic import BaseModel, Field
except ImportError:
    BaseModel = object
    def Field(*args, **kwargs):
        return None
import argparse

try:
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import JsonOutputParser
except ImportError:
    ChatOpenAI = None
    ChatPromptTemplate = None
    JsonOutputParser = None
from tools.strategy_field_utils import extract_required_fields

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('LLMStrategyGenerator')

# ==========================================
# 1. 策略配置生成相关模型与 Prompt
# ==========================================


class GlobalParams(BaseModel):
    top_K: int = Field(default=20, description="最大选股数量")
    start_date: str = Field(default="20200101", description="回测开始日期 YYYYMMDD")
    end_date: str = Field(default="20240101", description="回测结束日期 YYYYMMDD")
    rebalance_period: int = Field(default=20, description="调仓周期(天)")
    folder_name: str = Field(default="generated_strategy", description="输出文件夹名称")
    lookback_years: int = Field(default=5, description="数据回看窗口(年)，用于需要历史窗口计算的指标(如3年CAGR)")

class FilterConfig(BaseModel):
    type: str = Field(..., description="过滤器类型: 'simple', 'range', 'rank', 'rank_range'")
    name: str = Field(..., description="筛选器名称")
    column: str = Field(..., description="因子字段名（如 S_VAL_PB_NEW, S_FA_CURRENT 等）")
    operator: Optional[str] = Field(default=None, description="操作符: '>', '>=', '<', '<=', '==' (适用于 simple, rank)")
    threshold: Optional[float] = Field(default=None, description="阈值 (适用于 simple, rank)")
    min_value: Optional[float] = Field(default=None, description="最小值 (适用于 range, rank_range)")
    max_value: Optional[float] = Field(default=None, description="最大值 (适用于 range, rank_range)")
    rank_type: Optional[str] = Field(default=None, description="当 type 包含 'rank' 时填写，例如 'percentile' 或 'absolute'")
    scope: Optional[str] = Field(default=None, description="排名范围，例如 'industry' 或 'market'")
    industry_column: Optional[str] = Field(default=None, description="行业列名，通常为 'NAME'")
    ascending: Optional[bool] = Field(default=None, description="是否升序排名")
    description: str = Field(..., description="过滤条件描述")

class RankComponent(BaseModel):
    name: str = Field(..., description="排序组件名称")
    column: str = Field(..., description="因子字段名")
    ascending: bool = Field(default=True, description="是否升序")
    scope: str = Field(default="industry", description="排名范围，如 'industry' 或 'market'")
    industry_column: str = Field(default="NAME", description="行业列名")
    weight: float = Field(default=1.0, description="该因子的权重")
    description: str = Field(default="", description="描述")

class Ranking(BaseModel):
    method: str = Field(default="multi_simple", description="排序方法: 'simple' 或 'multi_simple'")
    name: str = Field(..., description="排序名称")
    description: str = Field(default="", description="描述")
    column: Optional[str] = Field(default=None, description="当 method='simple' 时的因子字段名")
    ascending: Optional[bool] = Field(default=None, description="当 method='simple' 时是否升序")
    scope: Optional[str] = Field(default=None, description="当 method='simple' 时的排名范围")
    components: Optional[List[RankComponent]] = Field(default=None, description="当 method='multi_simple' 时的排序组件列表")

class WeightAllocation(BaseModel):
    type: str = Field(default="equal", description="权重分配类型，如 'equal'")
    name: str = Field(default="等权重分配", description="名称")
    description: str = Field(default="为同一调仓日中股票分配相同权重", description="描述")

class StrategyConfigSchema(BaseModel):
    name: str = Field(..., description="策略名称")
    description: str = Field(..., description="策略描述")
    global_params: GlobalParams = Field(..., description="全局参数")
    filters: List[FilterConfig] = Field(..., description="过滤器列表")
    ranking: Ranking = Field(..., description="打分排序配置")
    weight_allocation: WeightAllocation = Field(default_factory=WeightAllocation, description="权重分配配置")


LLM_STRATEGY_PROMPT = """
你是一个量化投资策略专家。请根据用户的自然语言描述，自动生成一个符合指定 JSON 格式的策略配置文件。

用户输入:
{user_input}

策略配置需要包含以下主要模块：
1. `name` 和 `description`: 策略的基本信息。
2. `global_params`: 包含 top_K (最大选股数量), start_date, end_date, rebalance_period, folder_name 等。
   - 额外要求：请给出 lookback_years（数据回看窗口，单位年）。如果策略包含“X年复合增长率/过去X年均值/长期波动率”等需要历史窗口的指标，lookback_years 至少覆盖该窗口；否则可使用默认 5 年。
3. `filters`: 筛选条件列表。支持的 type 有 'simple', 'range', 'rank', 'rank_range'。
   - 'simple': 需要 column, operator (>, >=, <, <=, ==), threshold
   - 'range': 需要 column, min_value, max_value
   - 'rank': 需要 column, operator, threshold, rank_type ('percentile' 或 'absolute'), scope ('industry' 或 'market'), ascending (布尔值)
   - 'rank_range': 需要 column, min_value, max_value, rank_type, scope, ascending
   - 注意：如果涉及行业内比较，scope 设置为 'industry'，industry_column 设置为 'NAME'。
4. `ranking`: 最终打分排序规则。支持 method 为 'simple'（单因子）或 'multi_simple'（多因子加权）。
5. `weight_allocation`: 权重分配，通常为 type="equal"。

请确保输出严格符合要求的 JSON 结构。你可以根据用户的描述合理推断因子字段名（如 PE 对应 S_VAL_PE_TTM，PB 对应 S_VAL_PB_NEW，流动比率对应 S_FA_CURRENT，等）。如果不确定具体的列名，可使用常见Wind/Qlib因子名称。

{format_instructions}
"""

# ==========================================
# 2. 字段映射相关模型与 Prompt
# ==========================================

class RelatedField(BaseModel):
    table_name: str = Field(..., description="数据库表名")
    field_name: str = Field(..., description="真实字段名")
    description: str = Field(..., description="字段中文名或注释说明")

class FieldMapping(BaseModel):
    strategy_field: str = Field(..., description="策略配置中使用的字段名")
    related_fields: List[RelatedField] = Field(..., description="从候选集合中匹配到的真实表和字段")

class MappingResultSchema(BaseModel):
    mappings: List[FieldMapping] = Field(..., description="所有字段的映射结果")

LLM_MAPPING_PROMPT = """
你是一个金融数据专家。我有一组量化策略中需要使用的字段名称（可能包含英文缩写或中文描述），以及一份包含许多真实数据库表和字段的候选对照表。
请根据策略所需的字段，从候选对照表中挑选出最匹配的真实字段（可能不止一个，但一般一个对应一个核心业务字段）。

需要映射的策略字段集合:
{target_fields}

候选的真实字段集合（格式为: table_name, field_name, 中文注释）:
{candidate_fields}

请输出严格的 JSON 格式，结构如下：
{{
  "mappings": [
    {{
      "strategy_field": "策略里的名字",
      "related_fields": [
        {{
          "table_name": "匹配到的表名",
          "field_name": "匹配到的真实字段名",
          "description": "对应的中文说明"
        }}
      ]
    }}
  ]
}}

{format_instructions}
"""

class LLMStrategyGenerator:
    """使用大模型自动生成策略配置的工具类"""
    
    def __init__(self, 
                 model="gpt-4o", 
                 base_url=None, 
                 api_key=None, 
                 temperature=0.2):
        
        # 从环境变量获取 API 配置，或者使用传入的值
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        
        if not self.api_key:
            logger.error("未找到 OPENAI_API_KEY，请设置环境变量或通过参数传入")
            sys.exit(1)
            
        # 初始化 LLM
        self.llm = ChatOpenAI(
            model=model,
            base_url=self.base_url,
            api_key=self.api_key,
            temperature=temperature
        )
        
    def generate(self, user_input: str, output_file: str) -> bool:
        """
        根据用户输入生成配置文件
        
        参数:
            user_input: 策略的自然语言描述
            output_file: 保存生成的 JSON 文件的路径
        """
        logger.info(f"正在分析用户描述并生成策略配置...")
        
        parser = JsonOutputParser(pydantic_object=StrategyConfigSchema)
        prompt = ChatPromptTemplate.from_template(
            template=LLM_STRATEGY_PROMPT,
            partial_variables={"format_instructions": parser.get_format_instructions()}
        )
        
        chain = prompt | self.llm | parser
        
        try:
            strategy_config = chain.invoke({"user_input": user_input})
            
            # 排除掉 None 值
            cleaned_config = strategy_config.copy()
            for filter_item in cleaned_config.get("filters", []):
                for k in list(filter_item.keys()):
                    if filter_item[k] is None:
                        del filter_item[k]
                        
            ranking = cleaned_config.get("ranking", {})
            for k in list(ranking.keys()):
                if ranking[k] is None:
                    del ranking[k]
            
            # 将生成的配置保存为 JSON 文件
            os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(cleaned_config, f, ensure_ascii=False, indent=2)
                
            logger.info(f"策略配置已成功生成并保存到: {output_file}")
            return cleaned_config
            
        except Exception as e:
            logger.error(f"生成策略配置失败: {e}")
            return None

    def read_csv_fields(self, file_paths: List[str]) -> List[str]:
        """
        读取 CSV 字段文件，生成候选字段集合字符串
        """
        all_fields = []
        for file_path in file_paths:
            if not os.path.exists(file_path):
                logger.warning(f"候选字段对照表不存在，跳过: {file_path}")
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        desc = row.get('中文名') or row.get('注释') or ''
                        field_info = f"{row.get('table_name', '')},{row.get('field_name', '')}, {desc}"
                        all_fields.append(field_info)
            except Exception as e:
                logger.error(f"读取 {file_path} 时出错: {e}")
        return all_fields

    def extract_required_fields(self, strategy_config: Dict) -> List[str]:
        return extract_required_fields(strategy_config)

    def generate_mapping(self, strategy_config: Dict, csv_files: List[str], mapping_output_file: str) -> bool:
        """
        根据策略配置和本地的 CSV 字段表，利用 LLM 生成字段映射 mapping_result.json
        """
        if os.path.exists(mapping_output_file):
            logger.info(f"映射文件 {mapping_output_file} 已存在，跳过生成步骤。如果需要重新生成请先删除。")
            return True
            
        required_fields = self.extract_required_fields(strategy_config)
        logger.info(f"需要映射的策略字段: {required_fields}")
        
        candidate_fields = self.read_csv_fields(csv_files)
        if not candidate_fields:
            logger.error("候选字段为空，无法执行字段映射，请检查 CSV 文件路径是否正确。")
            return False
            
        candidate_str = "\n".join(candidate_fields)
        
        logger.info("正在调用 LLM 进行字段映射...")
        parser = JsonOutputParser(pydantic_object=MappingResultSchema)
        prompt = ChatPromptTemplate.from_template(
            template=LLM_MAPPING_PROMPT,
            partial_variables={"format_instructions": parser.get_format_instructions()}
        )
        
        chain = prompt | self.llm | parser
        
        try:
            mapping_result = chain.invoke({
                "target_fields": ", ".join(required_fields),
                "candidate_fields": candidate_str
            })
            
            os.makedirs(os.path.dirname(os.path.abspath(mapping_output_file)), exist_ok=True)
            with open(mapping_output_file, 'w', encoding='utf-8') as f:
                json.dump(mapping_result, f, ensure_ascii=False, indent=2)
                
            logger.info(f"字段映射已成功生成并保存到: {mapping_output_file}")
            return True
            
        except Exception as e:
            logger.error(f"生成字段映射失败: {e}")
            return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM 量化策略配置生成器")
    parser.add_argument("--prompt", type=str, required=True, help="策略的自然语言描述")
    parser.add_argument("--output", type=str, default="config/generated_strategy.json", help="输出的 JSON 配置文件路径")
    parser.add_argument("--model", type=str, default="gpt-4o", help="使用的模型名称")
    parser.add_argument("--base-url", type=str, default=None, help="LLM API Base URL")
    
    args = parser.parse_args()
    
    generator = LLMStrategyGenerator(model=args.model, base_url=args.base_url)
    
    # 1. 生成策略配置
    strategy_config = generator.generate(args.prompt, args.output)
    
    if strategy_config:
        # 2. 如果存在本地 CSV 对照表，则自动进行字段映射
        csv_files = [
            "documents/财务字段中英文对照表.csv",
            "documents/宏观微观字段名对照表.csv",
            "documents/量价字段中英文对照表.csv"
        ]
        
        # 将输出文件同级目录作为 mapping 文件的保存路径
        mapping_file = os.path.join(os.path.dirname(args.output), "mapping_result.json")
        generator.generate_mapping(strategy_config, csv_files, mapping_file)
