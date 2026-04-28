import os
import json
import logging
from pathlib import Path
from typing import Dict, Optional, List
import pandas as pd
import qlib
from qlib.data import D
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field,RootModel
from framework.strategy_framework import BaseDataReader
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.absolute()

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('QlibDataLoader')


class FieldFillStrategies(RootModel[Dict[str,str]]):
    """定义字段填充策略的数据模型"""
    root: Dict[str, str] = Field(..., description="列名与对应的填充策略映射（'0' 或 'ffill'）")


# 定义 LLM 提示模板
LLM_PREPROCESS_PROMPT_TEMPLATE = """
你是一个金融数据预处理专家。请根据以下目标字段和参考信息，为每个字段建议一个缺失值填充策略。

策略只能是 "0"（填充为0）或 "ffill"（前向填充）。

通常：
- 财务指标（如收入、利润）如果是缺失，更可能是0，建议用 "0"
- 价格、估值指标、宏观经济数据如果缺失，更可能需要用前值，建议用 "ffill"

目标字段: {target_fields_str}
参考信息: {reference_info}

请返回JSON格式，键为字段名，值为策略("0" 或 "ffill")。
"""


class QlibDataReader(BaseDataReader):
    """
    基于 Qlib 的数据读取器，实现 BaseDataReader 接口
    替换原有的基于 Oracle 数据库的读取逻辑
    """

    def __init__(self,
                 mapping_file: str,
                 stock_pool_file: str,
                 macro_file: str,
                 backtest_start_date: Optional[str] = None,
                 backtest_end_date: Optional[str] = None,
                 lookback_years: int = 1,
                 model: str = "deepseek-v3",
                 base_url: str = "http://172.21.16.9/ms-r6rcvnnp/v1",
                 api_key: str = "key",
                 temperature: float = 0.2,
                 timeout: float = 240.0,
                 price_data_path: str = "/home/quant/zc/finance_deal/qlib_data/price_data0821",
                 fin_data_path: str = "/home/quant/zc/finance_deal/qlib_data/pit_data",
                 inst_stock_file: str = Path(f"{PROJECT_ROOT.parent}/documents/inst_stock.csv"),
                 external_data_files: Optional[List[str]] = None,
                 config_path: Optional[str] = None):
        """
        初始化 Qlib 数据读取器

        参数:
            mapping_file: 字段映射 JSON 文件路径
            stock_pool_file: 股票池 JSON 文件路径
            macro_file: 宏观数据 CSV 文件路径
            model: LLM 模型名称
            base_url: LLM API 基础 URL
            api_key: LLM API Key
            temperature: LLM 温度参数
            timeout: LLM 超时时间
            price_data_path: Qlib 价格数据路径
            fin_data_path: Qlib 财务数据路径
            inst_stock_file: 包含行业信息的CSV文件路径
            external_data_files: 外部数据文件列表
            config_path:策略配置文件路径，用于重写实际列名
        """
        self.need_start_date = True  # 该读取器可能需要时间段来拉取序列数据
        self.mapping_file = mapping_file
        self.stock_pool_file = stock_pool_file
        self.macro_file = macro_file
        self.external_data_files = external_data_files
        self.price_data_path = price_data_path
        self.fin_data_path = fin_data_path
        self.inst_stock_file=inst_stock_file
        self.config_path=config_path
        self.backtest_start_date=backtest_start_date
        self.backtest_end_date=backtest_end_date
        self.lookback_years=lookback_years
        self._prefetch_full_data:Optional[pd.DataFrame] = None

        # 初始化 LLM
        self.llm = ChatOpenAI(
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
            timeout=timeout
        )

        # 定义支持的表名
        self.fin_tables = [
            "ASHARECASHFLOW", "ASHARECASHFLOWHIS", "ASHAREBALANCESHEET",
            "ASHAREBALANCESHEETHIS", "ASHAREINCOME", "ASHAREINCOMEHIS",
            "ASHARETTMHIS", "ASHARECONSENSUSINDEXHIS", "ASHAREPROFITEXPRESSHIS",
            "ASHAREFINANCIALINDICATOR"
        ]
        self.price_tables = [
            "ASHAREEODPRICES", "AShareAuction", "AShareEODDerivativeIndicator",
            "AShareEODPricesMKT", "AShareEVIndicator", "AShareEnergyindex",
            "AShareEnergyindexADJ", "AShareL2Indicators", "AShareMoneyFlow",
            "AShareTechIndicators", "AShareValuationIndicator", "AShareYield",
            "AShareswingReversetrend", "AShareswingReversetrendADJ",
            "Ashareintensitytrend", "AshareintensitytrendADJ",
            "AsharesFndfactor_ConFcst", "DailyValuationFactor",
            "PITFinancialFactor", "RevenueTechnicalFactor"
        ]



        # 将表名转小写
        self.fin_tables_lower = {name.lower() for name in self.fin_tables}
        self.price_tables_lower = {name.lower() for name in self.price_tables}

    def preprocess_with_llm(self, df: pd.DataFrame, field_descriptions: dict = None) -> pd.DataFrame:
        """使用 LLM 处理缺失值"""
        valid_fields = [f for f in df.columns if f not in ['datetime', 'instrument', 'TRADE_DT', 'S_INFO_WINDCODE']]
        logger.info(f"正在使用 LLM 为字段 {valid_fields} 生成缺失值处理策略...")
        target_fields_str = ", ".join(valid_fields)
        reference_info = json.dumps(field_descriptions, ensure_ascii=False,
                                    indent=2) if field_descriptions else "无额外描述信息"
        prompt = ChatPromptTemplate.from_template(LLM_PREPROCESS_PROMPT_TEMPLATE)
        parser = JsonOutputParser(pydantic_object=FieldFillStrategies)
        chain = prompt | self.llm | parser
        try:
            strategies = chain.invoke({"target_fields_str": target_fields_str, "reference_info": reference_info})
            # 兼容 Pydantic v1/v2 的返回格式
            if isinstance(strategies,dict):
                strategies_dict=strategies
            else:
                strategies_dict=strategies.root
            logger.info(f"LLM建议的填充策略: {strategies_dict}")
            # Apply strategies
            df_processed = df.copy()
            for col, strategy in strategies_dict.items():
                if col in df_processed.columns:
                    if strategy == "0":
                        df_processed[col] = df_processed[col].fillna(0)
                    elif strategy == "ffill":
                        df_processed[col] = df_processed[col].fillna(method='ffill')
            return df_processed
        except Exception as e:
            logger.info(f"LLM预处理失败: {e}")
            return df

    def json_parse(self, results: dict):
        """解析映射 JSON"""
        fin_fields = set()
        price_fields = set()
        macro_fields = set()
        desc_dict = {}
        for mapping in results.get('mappings', []):
            for field_info in mapping.get('related_fields', []):
                table_name = field_info.get('table_name', '').lower()
                mapped_field = field_info.get('field_name', '')
                desc_info = field_info.get('description', '')
                desc_dict[mapped_field] = desc_info
                if table_name in self.fin_tables_lower:
                    mapped_field1 = f'$cor_{mapped_field}_{table_name}'
                    mapped_field2 = f'$adj_{mapped_field}_{table_name}'
                    fin_fields.add(mapped_field1)
                    fin_fields.add(mapped_field2)
                elif table_name in self.price_tables_lower:
                    mapped_field1 = f'${mapped_field}_{table_name}'
                    if mapped_field in ['close']:
                        mapped_field1 = f'${mapped_field}'
                    price_fields.add(mapped_field1)
                elif table_name in ['宏观']:
                    macro_fields.add(mapped_field)
        return sorted(fin_fields), sorted(price_fields), sorted(macro_fields), desc_dict

    def read_qlibdata(self, instruments: list, fields: list, data_type: str, start_time: str,
                      end_time: str) -> pd.DataFrame:
        """从 Qlib 读取数据"""
        if not fields:
            return None
        # 格式化日期 (从 YYYYMMDD 转为 YYYY-MM-DD)
        start_time_fmt = f"{start_time[:4]}-{start_time[4:6]}-{start_time[6:]}" if start_time else None
        end_time_fmt = f"{end_time[:4]}-{end_time[4:6]}-{end_time[6:]}"

        if data_type == 'price':
            qlib.init(provider_uri=self.price_data_path)
            # 在指定时间范围内获取数据
            data = D.features(
                instruments=instruments,
                fields=fields,
                start_time=start_time_fmt,
                end_time=end_time_fmt,
                freq='day',
            )
            data = data.reset_index()
        elif data_type == 'fin':
            qlib.init(provider_uri=self.fin_data_path)
            data = D.features(
                instruments=instruments,
                fields=fields,
                start_time=start_time_fmt,
                end_time=end_time_fmt,
                freq='day',
            )
            data = data.reset_index()

        if data is None or data.empty:
            return data

        # 清洗列名
        original_columns = data.columns
        cleaned_columns = original_columns.str.replace(r'^P\(\$\$', '', regex=True) \
            .str.replace(r'_q\)', '', regex=True) \
            .str.replace(r'\$', '', regex=True)
        data = data.set_axis(cleaned_columns, axis=1)
        return data

    def check_nullcols(self, df: pd.DataFrame) -> pd.DataFrame:
        """移除全为空的列"""
        if df is None or df.empty:
            return df
        empty_cols = df.columns[df.isnull().all()].tolist()
        if empty_cols:
            logger.info(f"删除全为空的列: {empty_cols}")
            df = df.drop(columns=empty_cols)
        return df

    def rewrite_strategy_config(self, mapping_results: dict, actual_columns: pd.Index):
        """将实际列名重新写入到策略配置的 column 字段中"""
        if not hasattr(self, 'config_path') or not self.config_path or not os.path.exists(self.config_path):
            return

        field_to_actual = {}
        for mapping in mapping_results.get('mappings', []):
            strategy_field = mapping.get('strategy_field')
            for field_info in mapping.get('related_fields', []):
                table_name = field_info.get('table_name', '').lower()
                mapped_field = field_info.get('field_name', '')

                possible_cols = []
                if table_name in self.fin_tables_lower:
                    possible_cols = [f'cor_{mapped_field}_{table_name}', f'adj_{mapped_field}_{table_name}']
                elif table_name in self.price_tables_lower:
                    if mapped_field in ['close']:
                        possible_cols = [f'{mapped_field}']
                    else:
                        possible_cols = [f'{mapped_field}_{table_name}']
                elif table_name in ['宏观']:
                    possible_cols = [mapped_field]

                # 寻找在数据框中实际存在的列名
                for p_col in possible_cols:
                    if p_col in actual_columns:
                        field_to_actual[strategy_field] = p_col
                        break

                if strategy_field in field_to_actual:
                    break

        if not field_to_actual:
            return

        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        updated = False

        # 更新 filters
        for f_conf in config.get('filters', []):
            old_col = f_conf.get('column')
            if old_col in field_to_actual and field_to_actual[old_col] != old_col:
                f_conf['column'] = field_to_actual[old_col]
                updated = True

        # 更新 ranking
        ranking = config.get('ranking', {})
        if 'column' in ranking:
            old_col = ranking.get('column')
            if old_col in field_to_actual and field_to_actual[old_col] != old_col:
                ranking['column'] = field_to_actual[old_col]
                updated = True

        for comp in ranking.get('components', []):
            old_col = comp.get('column')
            if old_col in field_to_actual and field_to_actual[old_col] != old_col:
                comp['column'] = field_to_actual[old_col]
                updated = True

        if updated:
            logger.info(f"将实际的 Qlib 列名重写回策略配置文件 {self.config_path} 中: {field_to_actual}")
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)


    def read_data(self, start_date: str = None, end_date: str = None) -> Dict[str, pd.DataFrame]:
        logger.info(f"QlibDataReader 开始读取数据，时间范围: {start_date} 至 {end_date}")

        if self.backtest_start_date and self.backtest_end_date and self.lookback_years and end_date:
            if self._prefetch_full_data is None:
                try:
                    from datetime import datetime
                    from dateutil.relativedelta import relativedelta
                    bt_start_dt = datetime.strptime(self.backtest_start_date, "%Y%m%d")
                    prefetch_start = (bt_start_dt - relativedelta(years=int(self.lookback_years))).strftime("%Y%m%d")
                except Exception:
                    prefetch_start = start_date

                self._prefetch_full_data = self._load_merged_data(
                    start_date=prefetch_start,
                    end_date=self.backtest_end_date,
                    filter_end_date=False
                )

            slice_df = self._prefetch_full_data
            if 'TRADE_DT' in slice_df.columns and end_date:
                slice_df = slice_df[slice_df['TRADE_DT'] == end_date].copy()

            return {
                'qlib_data': slice_df,
                'listing_data': pd.DataFrame(columns=['S_INFO_WINDCODE', 'LISTING_DATE']),
                'industry_classification': pd.DataFrame(columns=['STOCKCODE', 'INDECODE']),
                'industry_dimension': pd.DataFrame(columns=['CODE', 'NAME'])
            }

        merge_data = self._load_merged_data(start_date=start_date, end_date=end_date, filter_end_date=True)
        return {
            'qlib_data': merge_data,
            'listing_data': pd.DataFrame(columns=['S_INFO_WINDCODE', 'LISTING_DATE']),
            'industry_classification': pd.DataFrame(columns=['STOCKCODE', 'INDECODE']),
            'industry_dimension': pd.DataFrame(columns=['CODE', 'NAME'])
        }

    def _load_merged_data(self, start_date: str, end_date: str, filter_end_date: bool) -> pd.DataFrame:

        # 1. 解析映射文件和股票池
        with open(self.mapping_file, 'r', encoding='utf-8') as f:
            mapping_results = json.load(f)
        fin_fields, price_fields, macro_fields, desc_dict = self.json_parse(mapping_results)
        df_stock = pd.read_csv(
            self.stock_pool_file,
            sep='\s+',
            header=None,
            names=['col1', 'col2', 'col3']
        )
        instruments=list(df_stock['col1'])
        merge_data = pd.DataFrame()

        # 2. 读取财务数据
        if fin_fields:
            fin_data = self.read_qlibdata(instruments, fin_fields, 'fin', start_date, end_date)
            fin_data = self.check_nullcols(fin_data)
            if fin_data is not None and not fin_data.empty:
                merge_data = fin_data

        # 3. 读取价格数据
        if price_fields:
            price_data = self.read_qlibdata(instruments, price_fields, 'price', start_date, end_date)
            price_data = self.check_nullcols(price_data)
            if price_data is not None and not price_data.empty:
                if merge_data.empty:
                    merge_data = price_data
                else:
                    merge_data = pd.merge(price_data, merge_data, on=['datetime', 'instrument'], how='left')

        # 4. 读取并合并宏观数据
        if macro_fields:
            logger.info(f"合并宏观数据字段: {macro_fields}")
            macro_data = pd.read_csv(self.macro_file)
            macro_data['datetime'] = pd.to_datetime(macro_data['datetime'])
            current_macro_fields = list(macro_fields)
            if 'datetime' not in current_macro_fields:
                current_macro_fields.append('datetime')
            macro_data = macro_data[current_macro_fields]
            macro_data = self.preprocess_with_llm(macro_data, desc_dict)
            if merge_data.empty:
                merge_data = macro_data
            else:
                merge_data = pd.merge(merge_data, macro_data, on='datetime', how='left')

        # 5. 读取并合并外部数据
        if self.external_data_files:
            logger.info(f"合并外部已生成指标文件: {self.external_data_files}")
            for ext_file in self.external_data_files:
                if Path(ext_file).exists():
                    ext_df = pd.read_csv(ext_file)
                    if 'datetime' in ext_df.columns:
                        ext_df['datetime'] = pd.to_datetime(ext_df['datetime'])
                        ext_df = self.preprocess_with_llm(ext_df, desc_dict)
                        if merge_data.empty:
                            merge_data = ext_df
                        else:
                            on_cols = ['datetime']
                            if 'instrument' in ext_df.columns and 'instrument' in merge_data.columns:
                                on_cols.append('instrument')
                            merge_data = pd.merge(merge_data, ext_df, on=on_cols, how='left')
                    else:
                        logger.warning(f"外部文件 {ext_file} 缺少 'datetime' 列，已跳过")

        # 6. 读取并合并行业数据 (inst_stock)
        if os.path.exists(self.inst_stock_file):
            logger.info(f"正在读取并合并行业信息文件: {self.inst_stock_file}")
            try:
                inst_df = pd.read_csv(self.inst_stock_file)
                # 根据新格式重命名列：STOCKCODE -> instrument
                if 'STOCKCODE' in inst_df.columns:
                    inst_df = inst_df.rename(columns={'STOCKCODE': 'instrument'})

                # 检查必需列
                required_cols = {'instrument', 'NAME', 'BEGINDATE', 'ENDDATE'}
                if required_cols.issubset(inst_df.columns) and not merge_data.empty:
                    # 将 BEGINDATE 和 ENDDATE 转为数值类型(YYYYMMDD)以便比较
                    inst_df['BEGINDATE'] = pd.to_numeric(inst_df['BEGINDATE'], errors='coerce').fillna(0)
                    inst_df['ENDDATE'] = pd.to_numeric(inst_df['ENDDATE'], errors='coerce').fillna(99999999)

                    # 准备宽表的 datetime 列用于比较 (YYYYMMDD 格式整数)
                    merge_data['temp_date_int'] = merge_data['datetime'].dt.strftime('%Y%m%d').astype(int)

                    # 由于行业信息是分时间段生效的，使用 pandasql 或者按条件 merge 较为复杂
                    # 这里我们先做 instrument 维度的 outer/left join，然后按时间条件过滤
                    inst_subset = inst_df[['instrument', 'NAME', 'BEGINDATE', 'ENDDATE']].copy()

                    # 先根据 instrument 合并，这会产生笛卡尔积（一只股票在多个时间段有多个行业记录）
                    merged_with_inst = pd.merge(merge_data, inst_subset, on='instrument', how='left')

                    # 过滤出时间匹配的行：BEGINDATE <= 当前数据日期 <= ENDDATE
                    # 包含NaN的情况（即该股票没有行业数据），直接保留
                    mask_valid_industry = (merged_with_inst['temp_date_int'] >= merged_with_inst['BEGINDATE']) & \
                                          (merged_with_inst['temp_date_int'] <= merged_with_inst['ENDDATE'])
                    mask_no_industry = merged_with_inst['NAME'].isna()

                    merge_data = merged_with_inst[mask_valid_industry | mask_no_industry].copy()

                    # 清理临时列
                    merge_data = merge_data.drop(columns=['temp_date_int', 'BEGINDATE', 'ENDDATE'])

                    # 防止因为时间交叠导致重复记录，基于原有的键去重
                    merge_data = merge_data.drop_duplicates(subset=['datetime', 'instrument'])

                elif 'instrument' in inst_df.columns and 'NAME' in inst_df.columns:
                    # 兼容老格式（没有 BEGINDATE/ENDDATE，直接根据 instrument 合并）
                    inst_df = inst_df[['instrument', 'NAME']].drop_duplicates()
                    if not merge_data.empty:
                        merge_data = pd.merge(merge_data, inst_df, on='instrument', how='left')
                else:
                    logger.warning(f"行业信息文件 {self.inst_stock_file} 缺少必要的列。当前列: {inst_df.columns}")
            except Exception as e:
                logger.error(f"读取或合并行业信息文件出错: {e}")
        else:
            logger.warning(f"未找到行业信息文件 {self.inst_stock_file}，将缺少行业分类列(NAME)。")

        # 7. 数据清洗
        if not merge_data.empty:
            # 统一列名以兼容 QuantStockPicker 框架
            # Qlib 使用 'instrument' 和 'datetime'
            # QuantStockPicker 使用 'S_INFO_WINDCODE' 和 'TRADE_DT'
            if 'instrument' in merge_data.columns:
                merge_data = merge_data.rename(columns={'instrument': 'S_INFO_WINDCODE'})
            if 'datetime' in merge_data.columns:
                # 将 datetime 转为 YYYYMMDD 字符串格式，以匹配原框架
                merge_data['TRADE_DT'] = merge_data['datetime'].dt.strftime('%Y%m%d')
            # 过滤只取特定日期（如果 end_date 不为 None）
            if  filter_end_date and  end_date:
                merge_data = merge_data[merge_data['TRADE_DT'] == end_date]
            value_cols = [col for col in merge_data.columns if col not in ['S_INFO_WINDCODE', 'TRADE_DT', 'datetime']]
            if value_cols:
                merge_data = merge_data.dropna(subset=value_cols, how='all')
            merge_data = merge_data.drop_duplicates()

        logger.info(f"数据合并完成，数据形状: {merge_data.shape}")

        # 将实际获取到的列名重写回策略配置中，确保筛选条件引用的字段一致
        if not merge_data.empty and hasattr(self, 'config_path') and self.config_path:
            self.rewrite_strategy_config(mapping_results, merge_data.columns)

        return merge_data