import os
from framework.strategy_framework import BaseStockSelector

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
                self.config_path=os.path.join('config','premium_value_strategy.json')

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
        return [],[]