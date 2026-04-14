import os
import sys
import json
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import argparse

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('LLMStrategyGenerator')

# 定义 Pydantic 模型，用于约束大模型输出的 JSON 格式

class GlobalParams(BaseModel):
    top_K: int = Field(default=20, description="最大选股数量")
    start_date: str = Field(default="20200101", description="回测开始日期 YYYYMMDD")
    end_date: str = Field(default="20240101", description="回测结束日期 YYYYMMDD")
    rebalance_period: int = Field(default=20, description="调仓周期(天)")
    folder_name: str = Field(default="generated_strategy", description="输出文件夹名称")

class FilterConfig(BaseModel):
    type: str = Field(..., description="过滤器类型: 'simple', 'range', 'rank', 'rank_range'")
    name: str = Field(..., description="筛选器名称")
    column: str = Field(..., description="因子字段名（如 S_VAL_PB_NEW, S_FA_CURRENT 等）")
    operator: Optional[str] = Field(None, description="操作符: '>', '>=', '<', '<=', '==' (适用于 simple, rank)")
    threshold: Optional[float] = Field(None, description="阈值 (适用于 simple, rank)")
    min_value: Optional[float] = Field(None, description="最小值 (适用于 range, rank_range)")
    max_value: Optional[float] = Field(None, description="最大值 (适用于 range, rank_range)")
    rank_type: Optional[str] = Field(None, description="当 type 包含 'rank' 时填写，例如 'percentile' 或 'absolute'")
    scope: Optional[str] = Field(None, description="排名范围，例如 'industry' 或 'market'")
    industry_column: Optional[str] = Field(None, description="行业列名，通常为 'NAME'")
    ascending: Optional[bool] = Field(None, description="是否升序排名")
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
    column: Optional[str] = Field(None, description="当 method='simple' 时的因子字段名")
    ascending: Optional[bool] = Field(None, description="当 method='simple' 时是否升序")
    scope: Optional[str] = Field(None, description="当 method='simple' 时的排名范围")
    components: Optional[List[RankComponent]] = Field(None, description="当 method='multi_simple' 时的排序组件列表")

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
            return True
            
        except Exception as e:
            logger.error(f"生成策略配置失败: {e}")
            return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM 量化策略配置生成器")
    parser.add_argument("--prompt", type=str, required=True, help="策略的自然语言描述")
    parser.add_argument("--output", type=str, default="config/generated_strategy.json", help="输出的 JSON 配置文件路径")
    parser.add_argument("--model", type=str, default="gpt-4o", help="使用的模型名称")
    parser.add_argument("--base-url", type=str, default=None, help="LLM API Base URL")
    
    args = parser.parse_args()
    
    generator = LLMStrategyGenerator(model=args.model, base_url=args.base_url)
    generator.generate(args.prompt, args.output)
