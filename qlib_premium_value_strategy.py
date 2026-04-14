import os
import json
import pandas as pd

from framework.strategy_framework import (
    BaseDataProcessor, BaseStockFilter,
    BaseFeatureCalculator, BaseStrategy
)
from framework.qlib_data_reader import QlibDataReader
from premium_value_strategy_new import PremiumValueStockSelector


class QlibPremiumValueDataProcessor(BaseDataProcessor):
    """
    基于 Qlib 数据源的数据处理器
    """
    def process_data(self, data_dict, end_date):
        """
        数据预处理
        
        参数:
            data_dict: 包含原始数据的字典
            end_date: 结束日期
            
        返回:
            处理后的数据字典
        """
        if 'qlib_data' in data_dict and not data_dict['qlib_data'].empty:
            df = data_dict['qlib_data']
            # 基本的清洗逻辑
            df = df.dropna(how='all', axis=1)  # 删除全为NaN的列
            data_dict['qlib_data'] = df
            print(f'去重和删除NaN值后 Qlib 数据形状: {data_dict["qlib_data"].shape}')

        return data_dict


class QlibPremiumValueStockFilter(BaseStockFilter):
    """
    基于 Qlib 数据源的股票筛选器
    """
    def filter_stocks(self, data_dict, date, **kwargs):
        """
        初步筛选符合条件的股票
        
        参数:
            data_dict: 包含所有数据的字典
            date: 当前日期
            
        返回:
            符合条件的股票代码列表
        """
        # 由于是基于提前设定好的 stock_pool_file 提取，
        # 如果有进一步的基于上市时间的筛选需求，可以在这里补充，
        # 目前直接返回所有获取到的股票。
        if 'qlib_data' in data_dict and not data_dict['qlib_data'].empty:
            return data_dict['qlib_data']['S_INFO_WINDCODE'].unique().tolist()
        return []


class QlibPremiumValueFeatureCalculator(BaseFeatureCalculator):
    """
    基于 Qlib 数据源的特征计算器
    """
    def calculate_features(self, data_dict, stock_list):
        """
        计算特征并合并最终宽表
        
        参数:
            data_dict: 包含所有数据的字典
            stock_list: 股票列表
            
        返回:
            包含特征的DataFrame
        """
        if 'qlib_data' not in data_dict or data_dict['qlib_data'].empty:
            return pd.DataFrame()

        res_df = data_dict['qlib_data']
        # 仅保留股票列表中的数据
        res_df = res_df[res_df['S_INFO_WINDCODE'].isin(stock_list)].copy()
        
        print(f'最终特征宽表形状: {res_df.shape}')
        print(f'最终股票数量：{len(res_df["S_INFO_WINDCODE"].unique())}')
        
        return res_df


class QlibPremiumValueStrategy(BaseStrategy):
    """
    使用 Qlib 作为数据源的优质价值策略
    """
    def __init__(self, 
                 mapping_file: str,
                 stock_pool_file: str,
                 macro_file: str,
                 start_date=None, 
                 end_date=None, 
                 rebalance_freq='Q', 
                 rebalance_period=60,
                 use_config=True,
                 config_filename=None,
                 config_dir="config"):
        """
        初始化策略
        """
        # 实例化基于 Qlib 的 Reader
        data_reader = QlibDataReader(
            mapping_file=mapping_file,
            stock_pool_file=stock_pool_file,
            macro_file=macro_file
        )
        
        data_processor = QlibPremiumValueDataProcessor()
        stock_filter = QlibPremiumValueStockFilter()
        feature_calculator = QlibPremiumValueFeatureCalculator()

        if use_config:
            if config_filename is None:
                config_filename = "premium_value_strategy.json"

            config_path = os.path.join(config_dir, config_filename)

            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            global_params = config.get('global_params', {})
            start_date = start_date or global_params.get('start_date')
            end_date = end_date or global_params.get('end_date')
            rebalance_period = rebalance_period or global_params.get('rebalance_period')

            # 复用原有的 Selector，因为其基于 Pipeline，只依赖 DataFrame 中的列名
            stock_selector = PremiumValueStockSelector(
                weight_method='equal',
                use_config=True,
                config_path=config_path
            )
        else:
            stock_selector = PremiumValueStockSelector()
        
        super().__init__(
            data_reader=data_reader,
            data_processor=data_processor,
            stock_filter=stock_filter,
            feature_calculator=feature_calculator,
            stock_selector=stock_selector,
            start_date=start_date,
            end_date=end_date,
            rebalance_freq=rebalance_freq,
            rebalance_period=rebalance_period,
        )


def main():
    print("\n===== 使用 Qlib 数据源的优质价值策略 =====")
    
    # 这里的路径需要替换为真实的配置路径
    mapping_file = "config/mapping_result.json"
    stock_pool_file = "config/filtered_stock_pool.json"
    macro_file = "documents/macro_data.csv"
    
    # 为了演示创建空文件避免报错
    os.makedirs("documents", exist_ok=True)
    if not os.path.exists(macro_file):
        with open(macro_file, 'w') as f: f.write("datetime,macro_value\n")
    if not os.path.exists(mapping_file):
        with open(mapping_file, 'w') as f: json.dump({"mappings": []}, f)
    if not os.path.exists(stock_pool_file):
        with open(stock_pool_file, 'w') as f: json.dump(["000001.SH"], f)

    config_filename = "premium_value_strategy.json"
    
    strategy = QlibPremiumValueStrategy(
        mapping_file=mapping_file,
        stock_pool_file=stock_pool_file,
        macro_file=macro_file,
        use_config=True,
        config_filename=config_filename,
        config_dir="config"
    )
    
    rebalance_result = strategy.run()
    strategy.save_results(rebalance_result, 'qlib_premium_value_strategy_result.csv')


if __name__ == "__main__":
    main()
