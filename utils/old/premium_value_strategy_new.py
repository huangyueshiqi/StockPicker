import os
import json
import pandas as pd

from framework.strategy_framework import (
    BaseDataReader, BaseDataProcessor, BaseStockFilter,
    BaseFeatureCalculator, BaseStockSelector, BaseStrategy
)
from utils.helpers import (
    execute_query, JYLH_DB, filter_and_clean_dataframe, get_stock_listing_data,
    filter_stocks_by_listing_age
)
from framework.old.factor_loader import FactorLoader

# 示例：重构Premium_value_strategy.py为使用新框架的实现

class PremiumValueDataReader(BaseDataReader):
    """
    优质价值策略的数据读取器
    """
    def __init__(self,config_dir,factor_filename,config_filename):
        self.need_start_date = False  # 该策略不需要开始日期
        self.config_dir = config_dir
        self.factor_filename = factor_filename
        self.config_filename = config_filename
        
    def read_data(self, start_date=None, end_date=None) -> dict:
        """
        从数据库读取所需数据
        
        参数:
            start_date: 开始日期（本策略不使用）
            end_date: 结束日期
            
        返回:
            包含所有数据的字典
        """
        # 获取股票上市日期数据
        df_date = get_stock_listing_data()
        print(f'df_date:{df_date.shape}')
        
        # 获取股票行业分类数据
        sql = "select TRADEDATE,STOCKCODE,INDECODE from JY_QY_STOCKQUOTATION_CS where TRADEDATE = :date_param order by TRADEDATE asc"
        df = execute_query(JYLH_DB, sql, (end_date,))
        
        # 获取行业维度数据
        querycode = '2222' if end_date >= "20220101" else '2214'
        sql = "select NAME,CODE from JY_QY_DIMENSION where FCODE= :querycode"
        df1 = execute_query(JYLH_DB, sql, (querycode,))

        loader = FactorLoader(f"{self.config_dir}")
        merged_data = loader.load_and_calculate(end_date, f"{self.factor_filename}",f"{self.config_filename}")
        
        return {
            'listing_data': df_date,
            'industry_classification': df,
            'industry_dimension': df1,
            'factor_data':merged_data
        }


class PremiumValueDataProcessor(BaseDataProcessor):
    """
    优质价值策略的数据处理器
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
        # 去重，删除包含NAN值行
        for key, df in data_dict.items():
            data_dict[key] = filter_and_clean_dataframe(df)
            print(f'去重和删除NaN值后{key}:{data_dict[key].shape}')

        return data_dict
    



class PremiumValueStockFilter(BaseStockFilter):
    """
    优质价值策略的股票筛选器
    """
    def filter_stocks(self, data_dict, date, **kwargs):
        """
        筛选符合条件的股票
        
        参数:
            data_dict: 包含所有数据的字典
            date: 当前日期
            
        返回:
            符合条件的股票代码列表
        """
        # 筛选上市时间符合条件的股票
        selected_stocks = filter_stocks_by_listing_age(data_dict['listing_data'], date)
        return selected_stocks


class PremiumValueFeatureCalculator(BaseFeatureCalculator):
    """
    优质价值策略的特征计算器
    """
    def calculate_features(self, data_dict, stock_list):
        """
        计算特征
        
        参数:
            data_dict: 包含所有数据的字典
            stock_list: 股票列表
            
        返回:
            包含特征的DataFrame
        """
        # 筛选符合条件的股票数据
        res_df = data_dict['listing_data'][data_dict['listing_data']['S_INFO_WINDCODE'].isin(stock_list)].dropna()
        res_df1 = data_dict['industry_classification'][data_dict['industry_classification']['STOCKCODE'].isin(stock_list)].dropna()
        merged_df = pd.merge(res_df, res_df1, left_on=['S_INFO_WINDCODE'], right_on=['STOCKCODE'], how='left')
        
        # 合并行业编码名字
        merged_df1 = pd.merge(merged_df, data_dict['industry_dimension'], left_on=['INDECODE'], right_on=['CODE'],
                              how='left').dropna()
        # 筛选所需的数据列
        merged_df2= merged_df1[['S_INFO_WINDCODE', 'TRADEDATE', 'INDECODE', 'NAME']]
        merged_df2.rename(columns={'TRADEDATE':'TRADE_DT'},inplace=True)

        merged_df3 = pd.merge(merged_df2, data_dict['factor_data'], on=['S_INFO_WINDCODE','TRADE_DT'],
                              how='left')
        res_df = merged_df3.dropna()
        print(f'res_df:{res_df.shape}')
        print(f'最终股票数量：{len(res_df["S_INFO_WINDCODE"].unique())}')
        
        return res_df


class PremiumValueStockSelector(BaseStockSelector):
    """
    使用新框架实现的优质价值策略选股器
    """

    def __init__(self, weight_method: str = 'equal',use_config:bool=True,config_path:str=None):
        """
        初始化优质价值策略选股器

        参数:
            weight_method: 权重分配方式，支持'equal'(等权), 'market_cap'(市值加权),
                          'industry_equal'(行业等权), 'factor'(因子加权)
            use_config:是否使用配置文件模式
            config_path:配置文件路径，当use_config=True时使用
        """
        self.weight_method = weight_method
        self.use_config=use_config
        self.config_path=config_path

        #如果使用配置模式，初始化ConfigurableStockSelector
        if self.use_config:
            if self.config_path is None:
                #默认使用内置的优质价值策略配置
                self.config_path=os.path.join('../../config', 'premium_value_strategy.json')

            from framework.configurable_strategy import ConfigurableStockSelector
            self.configurable_selector=ConfigurableStockSelector(config_path=self.config_path)


    def select_stocks(self, feature_df, **kwargs):
        """
        选择股票

        参数:
            feature_df: 包含特征的DataFrame

        返回:
            选中的股票列表
        """
        # 使用带权重的方法，但只返回股票列表
        stocks, _ = self.select_stocks_with_weights(feature_df, **kwargs)
        return stocks

    def select_stocks_with_weights(self, feature_df, **kwargs):
        """
        选择股票并返回权重

        参数:
            feature_df: 包含特征的DataFrame

        返回:
            (选中的股票列表, 对应的权重列表)
        """

        #如果使用配置模式，直接调用配置选择器
        if self.use_config:
            print(f'----使用配置模式-----')
            return self.configurable_selector.select_stocks_with_weights(feature_df,**kwargs)


class PremiumValueStrategy(BaseStrategy):
    """
    优质价值策略
    """
    def __init__(self, start_date=None, end_date=None, rebalance_freq='Q', rebalance_period=60,
                 use_config=True,factor_filename=None,config_filename=None,
                 config_dir="/home/quant/zc/backtrader/QuantStockPicker/config"):
        """
        初始化策略
        
        参数:
            start_date: 开始日期
            end_date: 结束日期
            rebalance_freq: 调仓频率，默认为季度('Q')
            rebalance_period: 调仓周期(天数)
            use_config: 是否使用配置文件
            factor_filename: 因子csv文件名
            config_filename: 策略配置json文件名
            config_dir: 配置文件夹路径
        """
        data_reader = PremiumValueDataReader(config_dir=config_dir,factor_filename=factor_filename,config_filename=config_filename)
        data_processor = PremiumValueDataProcessor()
        stock_filter = PremiumValueStockFilter()
        feature_calculator = PremiumValueFeatureCalculator()

        #如果使用配置文件
        if use_config:
            if config_filename is None:
                config_filename = "premium_value_strategy.json"

            config_path = os.path.join(config_dir,config_filename)

            # 从配置文件读取参数
            with open(config_path, 'r', encoding='utf-8') as f:
                config =  json.load(f)

            #优先使用配置文件中的参数
            global_params = config.get('global_params', {})
            start_date = start_date or global_params.get('start_date')
            end_date = end_date or global_params.get('end_date')
            rebalance_period = rebalance_period or global_params.get('rebalance_period')

            #创建使用配置文件的选股器
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


# 使用示例
def main():
    # 创建并运行策略
    print("\n===== 使用配置文件的优质价值策略 =====")
    factor_filename="factor.csv"
    config_filename="premium_value_strategy.json"
    pv_strategy_config = PremiumValueStrategy(use_config=True,factor_filename=factor_filename,config_filename=config_filename)
    pv_rebalance_config = pv_strategy_config.run()
    pv_strategy_config.save_results(pv_rebalance_config,'premium_value_strategy_config.csv')


if __name__ == "__main__":
    main()