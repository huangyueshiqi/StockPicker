import abc
import time
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional, Union, Callable

from utils.helpers import rebalancing_day,rebalancing_by_period


class BaseDataReader(abc.ABC):
    """
    数据读取基类，定义数据获取接口
    """
    @abc.abstractmethod
    def read_data(self, start_date: str = None, end_date: str = None) -> Dict[str, pd.DataFrame]:
        """
        从数据库读取所需数据
        
        参数:
            start_date: 开始日期
            end_date: 结束日期
            
        返回:
            包含所有数据的字典
        """
        pass


class BaseDataProcessor(abc.ABC):
    """
    数据预处理基类，定义数据处理接口
    """
    @abc.abstractmethod
    def process_data(self, data_dict: Dict[str, pd.DataFrame], end_date: str) -> Dict[str, pd.DataFrame]:
        """
        数据预处理
        
        参数:
            data_dict: 包含原始数据的字典
            end_date: 结束日期
            
        返回:
            处理后的数据字典
        """
        pass


class BaseStockFilter(abc.ABC):
    """
    股票筛选基类，定义股票筛选接口
    """
    @abc.abstractmethod
    def filter_stocks(self, data_dict: Dict[str, pd.DataFrame], date: str, **kwargs) -> List[str]:
        """
        筛选符合条件的股票
        
        参数:
            data_dict: 包含所有数据的字典
            date: 当前日期
            kwargs: 其他参数
            
        返回:
            符合条件的股票代码列表
        """
        pass


class BaseFeatureCalculator(abc.ABC):
    """
    特征计算基类，定义特征计算接口
    """
    @abc.abstractmethod
    def calculate_features(self, data_dict: Dict[str, pd.DataFrame], stock_list: List[str]) -> pd.DataFrame:
        """
        计算特征
        
        参数:
            data_dict: 包含所有数据的字典
            stock_list: 股票列表
            
        返回:
            包含特征的DataFrame
        """
        pass


class BaseStockSelector(abc.ABC):
    """
    选股基类，定义选股接口
    """
    @abc.abstractmethod
    def select_stocks(self, feature_df: pd.DataFrame, **kwargs) -> List[str]:
        """
        选择股票
        
        参数:
            feature_df: 包含特征的DataFrame
            kwargs: 其他参数
            
        返回:
            选中的股票列表
        """
        pass
    
    def select_stocks_with_weights(self, feature_df: pd.DataFrame, **kwargs) -> Tuple[List[str], List[float]]:
        """
        选择股票并返回对应权重
        
        参数:
            feature_df: 包含特征的DataFrame
            kwargs: 其他参数
            
        返回:
            (选中的股票列表, 对应的权重列表)
        """
        # 默认实现：调用select_stocks并为所有股票分配等权重
        stocks = self.select_stocks(feature_df, **kwargs)
        if not stocks:
            return [], []
        weights = [1.0 / len(stocks)] * len(stocks)
        return stocks, weights


class BaseStrategy(abc.ABC):
    """
    策略基类，定义策略接口
    """
    def __init__(self, 
                 data_reader: BaseDataReader,
                 data_processor: BaseDataProcessor,
                 stock_filter: BaseStockFilter,
                 feature_calculator: BaseFeatureCalculator,
                 stock_selector: BaseStockSelector,
                 start_date: str,
                 end_date: str,
                 rebalance_freq: str = 'Q',
                 rebalance_period: int = 60):
        """
        初始化策略
        
        参数:
            data_reader: 数据读取器
            data_processor: 数据处理器
            stock_filter: 股票筛选器
            feature_calculator: 特征计算器
            stock_selector: 选股器
            start_date: 开始日期
            end_date: 结束日期
            rebalance_freq: 调仓频率，默认为季度('Q')，此参数已弃用
            rebalance_period: 调仓周期(交易日天数)，默认为60天
        """
        self.data_reader = data_reader
        self.data_processor = data_processor
        self.stock_filter = stock_filter
        self.feature_calculator = feature_calculator
        self.stock_selector = stock_selector
        self.start_date = start_date
        self.end_date = end_date
        self.rebalance_freq = rebalance_freq
        self.rebalance_period = rebalance_period
        
    def run(self) -> pd.DataFrame:
        """
        运行策略
        
        返回:
            调仓表DataFrame
        """
        # 记录开始时间
        start_time = time.time()
        
        # 获取调仓日期
        # dates = rebalancing_day(self.start_date, self.end_date, freq=self.rebalance_freq)
        # if '2020-04-01' in dates:
        #     dates.remove('2020-04-01')  # 特殊处理
        dates =rebalancing_by_period(self.start_date,self.end_date,self.rebalance_period)
        rebalance_dates = [date.replace('-', '') for date in dates]
        stock_lists = []
        
        # 对每个调仓日执行策略
        for end_date in rebalance_dates:
            print(f'调仓日：{end_date}')
            # end_date='20250102'
            # 计算开始日期（如果策略需要）
            start_date = None
            if hasattr(self.data_reader, 'need_start_date') and self.data_reader.need_start_date:
                end_dt = datetime.strptime(end_date, '%Y%m%d')
                start_dt = self._calculate_start_date(end_dt)
                start_date = start_dt.strftime("%Y%m%d")
            
            # 读取数据
            raw_data = self.data_reader.read_data(start_date=start_date, end_date=end_date)
            
            # 数据预处理
            processed_data = self.data_processor.process_data(raw_data, end_date)
            
            # 初步筛选股票
            selected_stocks = self.stock_filter.filter_stocks(processed_data, end_date)
            print(f'selected_stocks:{len(selected_stocks)}')
            
            # 计算特征
            feature_df = self.feature_calculator.calculate_features(processed_data, selected_stocks)
            
            # 选股
            # 检查select_stocks方法是否返回权重信息
            result = self.stock_selector.select_stocks(feature_df)
            
            # 处理返回结果，兼容不同返回格式
            if isinstance(result, tuple) and len(result) >= 2:
                # 返回格式为 (股票列表, 权重列表) 或 (DataFrame, 股票列表, 权重列表)
                if isinstance(result[0], list) and isinstance(result[1], list):
                    stock_list = result[0]
                else:
                    stock_list = result[1]
            else:
                # 只返回股票列表
                stock_list = result
            
            stock_lists.append(stock_list)
        
        # 生成调仓表
        rebalance_table = self._generate_rebalance_table(rebalance_dates, stock_lists)
        
        # 输出总运行时间
        end_time = time.time()
        print(f'回测总运行时间：{end_time - start_time:.2f}秒')
        
        return rebalance_table
    
    def _calculate_start_date(self, end_dt: datetime) -> datetime:
        """
        计算开始日期，默认为5年前
        
        参数:
            end_dt: 结束日期
            
        返回:
            开始日期
        """
        from dateutil.relativedelta import relativedelta
        return end_dt - relativedelta(years=5)
    
    def _generate_rebalance_table(self, rebalance_dates: List[str], stock_lists: List[List[str]]) -> pd.DataFrame:
        """
        生成调仓表
        
        参数:
            rebalance_dates: 调仓日期列表
            stock_lists: 每个调仓日对应的股票列表
            
        返回:
            调仓表DataFrame
        """
        data = []
        for date, stocks in zip(rebalance_dates, stock_lists):
            # 将 YYYYMMDD 格式的日期转换为 YYYY-MM-DD
            formatted_date = f"{date[:4]}-{date[4:6]}-{date[6:]}" if len(date) == 8 else date
            for stock in stocks:
                data.append({
                    'datetime': formatted_date,
                    'instrument': stock
                })
        return pd.DataFrame(data)
    
    def save_results(self, rebalance_table: pd.DataFrame, filename: str = None) -> None:
        """
        保存调仓表
        
        参数:
            rebalance_table: 调仓表DataFrame
            filename: 文件名，默认为策略名称
        """
        if filename is None:
            filename = f'{self.__class__.__name__.lower()}_result.csv'
        rebalance_table.to_csv(filename, index=False)
