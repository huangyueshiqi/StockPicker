import os
import pandas as pd
from typing import Dict,List,Tuple,Any,Callable,Optional

from framework.strategy_framework import BaseStockSelector
from framework.strategy_config import StrategyConfigLoader,StrategyFactory
from utils.helpers import filter_double_low


class ConfigurableStockSelector(BaseStockSelector):
    """
    基于配置文件的可配置策略选股器
    """
    def __init__(self,config_path:str=None,config_dict:Dict=None):
        """
        初始化可配置策略选股器

        参数：
            config_path: 配置文件路径(JSON或YAML格式)
            config_dict: 配置字典(直接提供配置内容)

        注意：
            config_path和config_dict只需要提供一个，如果都提供，优先使用config_path
        """
        if config_path is None and config_dict is None:
            raise ValueError("config_path和config_dict至少需要提供一个")

        self.config_path=config_path
        self.config_dict=config_dict

        #注册自定义过滤函数
        self.custom_filter_func={
            'filter_double_low':filter_double_low,
            'calculate_industry_stats':self._calculate_industry_stats,
        }

        #延迟初始化，等到调用select_stocks时再创建
        self._pipeline=None
        self._factory=None

    def _initialize(self):
        """
        初始化策略工厂和流水线
        """
        if self._factory is not None:
            return

        #加载配置
        if self.config_path is not None:
            config_loader=StrategyConfigLoader(self.config_path)
        else:
            #如果是字典配置，先保存为临时文件
            import tempfile
            import json

            temp_dir=tempfile.gettempdir()
            temp_file=os.path.join(temp_dir,'temp_strategy_config.json')

            with open(temp_file,'w',encoding='utf-8') as f:
                json.dump(self.config_dict,f,ensure_ascii=False,indent=2)

            config_laoder=StrategyConfigLoader(temp_file)

        #创建策略工厂
        self._factory=StrategyFactory(config_loader)

        #注册自定义过滤函数
        for name,func in self.custom_filter_func.items():
            self._factory.register_custom_filter(name,func)

        #创建流水线
        self._pipeline=self._factory.create_filter_pipeline()


    def _calculate_industry_stats(self,df:pd.DataFrame) -> pd.DataFrame:
        """
        计算行业统计数据

        参数：
            df: 输入数据框

        返回：
            添加了行业统计列的数据框
        """
        industry_stats = df.groupby('NAME').agg({
            'ROE_3y_AVG': 'median',
            'EVEBITDA': 'median',
            'S_FA_DEBTTOASSETS': 'median',
            'OIAR': 'median',
            'S_FA_ARTURN': lambda x: x.quantile(0.5)  # 行业中位数
        }).reset_index()

        industry_stats.columns = ['NAME', 'industry_ROE3yAVG', 'industry_EVEBITDA', 'industry_DEBTTOASSETS',
                                  'industry_OIAR', 'industry_ARTURN']

        return pd.merge(df, industry_stats, on='NAME', how='left')

    def select_stocks(self, feature_df, **kwargs):
        """
        选择股票

        参数:
            feature_df: 包含特征的DataFrame

        返回:
            选中的股票列表
        """
        #使用带权重的方法，但只返回股票列表
        stocks,_=self.select_stocks_with_weights(feature_df,**kwargs)
        return stocks

    def select_stocks_with_weights(self, feature_df, **kwargs):
        """
        选择股票并返回对应权重

        参数:
            feature_df: 包含特征的DataFrame
            kwargs: 其他参数,会覆盖配置文件中的全局参数

        返回:
            (选中的股票列表, 对应的权重列表)
        """
        # 初始化流水线(如果尚未初始化)
        self._initialize()

        #获取全局参数
        global_params=self._factory.config.get_global_params()

        #合并全局参数和kwargs
        #kwargs优先级更高，会覆盖全局参数
        all_params={**global_params,**kwargs}

        # 获取top_K参数
        top_K = all_params.get('top_K',10)  #默认选择前20只股票

        #运行流水线
        result_df,stock_list,weight_list=self._pipeline.run(feature_df,top_k=top_K)

        print(f'top_stocks:{stock_list}')
        print(f'weights:{[round(w, 4) for w in weight_list]}')

        return stock_list,weight_list













