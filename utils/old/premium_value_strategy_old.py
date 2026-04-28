import os
import json
import pandas as pd

from framework.strategy_framework import (
    BaseDataReader, BaseDataProcessor, BaseStockFilter,
    BaseFeatureCalculator, BaseStockSelector, BaseStrategy
)
from utils.helpers import (
    execute_query, WIND_DB, JYLH_DB, FINCHINA_DB,
    filter_and_clean_dataframe, get_stock_listing_data,
    filter_stocks_by_listing_age,calculate_revenue_cagr,filter_double_low
)


# 示例：重构Premium_value_strategy.py为使用新框架的实现

class PremiumValueDataReader(BaseDataReader):
    """
    优质价值策略的数据读取器
    """
    def __init__(self):
        self.need_start_date = False  # 该策略不需要开始日期
        
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
        
        # 获取估值指标数据
        sql = "select S_INFO_WINDCODE,TRADE_DT,S_VAL_PB_NEW,S_VAL_PE_TTM from ASHAREEODDERIVATIVEINDICATOR where TRADE_DT = :date_param"
        df2 = execute_query(WIND_DB, sql, (end_date,))
        print(f'df2:{df2.shape}')
        
        # 获取财务指标数据
        sql = ("select S_INFO_WINDCODE,ANN_DT,REPORT_PERIOD,S_FA_ROE_DEDUCTED,S_FA_DEBTTOASSETS,S_FA_CURRENT,S_FA_FCFF,S_FA_ARTURN "
               "from ASHAREFINANCIALINDICATOR where ANN_DT < :date_param "
               "and REPORT_PERIOD BETWEEN TO_CHAR(ADD_MONTHS(TO_DATE(:date_param, 'YYYY-MM-DD'), -48), 'YYYYMMDD') AND TO_CHAR(TO_DATE(:date_param, 'YYYY-MM-DD'), 'YYYYMMDD')"
               "ORDER BY S_INFO_WINDCODE, REPORT_PERIOD")
        df3 = execute_query(WIND_DB, sql, (end_date,))
        print(f'df3:{df3.shape}')
        
        # 获取企业价值倍数数据
        sql = "select SYMBOL,TRADEDATE,EVEBITDA from TQ_SK_FININDIC where TRADEDATE = :date_param"
        df4 = execute_query(FINCHINA_DB, sql, (end_date,))
        print(f'df4:{df4.shape}')
        
        # 获取现金流数据
        sql = ("select S_INFO_WINDCODE,ACTUAL_ANN_DT,REPORT_PERIOD,STATEMENT_TYPE,NET_CASH_FLOWS_OPER_ACT "
               "from ASHARECASHFLOWHIS where ACTUAL_ANN_DT< :date_param and STATEMENT_TYPE IN (408001000,408005000,408027000,408028000,408003600,408045000) "
               "and  REPORT_PERIOD BETWEEN TO_CHAR(ADD_MONTHS(TO_DATE(:date_param, 'YYYY-MM-DD'), -36), 'YYYYMMDD') AND TO_CHAR(TO_DATE(:date_param, 'YYYY-MM-DD'), 'YYYYMMDD')"
               "ORDER BY S_INFO_WINDCODE, REPORT_PERIOD")
        df5 = execute_query(WIND_DB, sql, (end_date,))
        print(f'df5:{df5.shape}')
        
        # 获取利润表数据
        sql = ("select  S_INFO_WINDCODE,ACTUAL_ANN_DT,REPORT_PERIOD,STATEMENT_TYPE,NET_PROFIT_EXCL_MIN_INT_INC,OPER_REV "
               "from ASHAREINCOMEHIS where ACTUAL_ANN_DT< :date_param and STATEMENT_TYPE IN (408001000,408005000,408027000,408028000,408003600,408045000) "
               "and REPORT_PERIOD BETWEEN TO_CHAR(ADD_MONTHS(TO_DATE(:date_param, 'YYYY-MM-DD'), -48), 'YYYYMMDD') AND TO_CHAR(TO_DATE(:date_param, 'YYYY-MM-DD'), 'YYYYMMDD')"
               "ORDER BY S_INFO_WINDCODE, REPORT_PERIOD")
        df6 = execute_query(WIND_DB, sql, (end_date,))
        print(f'df6:{df6.shape}')
        
        # 获取资产负债表数据
        sql = ("select S_INFO_WINDCODE,ANN_DT,REPORT_PERIOD,STATEMENT_TYPE,ACCT_RCV "
               "from ASHAREBALANCESHEET where ANN_DT< :date_param and STATEMENT_TYPE IN (408001000,408005000,408027000,408028000,408003600,408045000)"
               "and REPORT_PERIOD BETWEEN TO_CHAR(ADD_MONTHS(TO_DATE(:date_param, 'YYYY-MM-DD'), -36), 'YYYYMMDD') AND TO_CHAR(TO_DATE(:date_param, 'YYYY-MM-DD'), 'YYYYMMDD')"
               "ORDER BY S_INFO_WINDCODE, REPORT_PERIOD")
        df7 = execute_query(WIND_DB, sql, (end_date,))
        print(f'df7:{df7.shape}')
        
        return {
            'listing_data': df_date,
            'industry_classification': df,
            'industry_dimension': df1,
            'valuation_data': df2,
            'financial_indicators': df3,
            'enterprise_value_data': df4,
            'cashflow_data': df5,
            'income_data': df6,
            'balance_sheet_data': df7,
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

        # 计算连续三年ROE(扣非)，连续三年ROE(扣非)波动率
        self._calculate_roe_metrics(data_dict)
        
        # 计算经营现金流净额/净利润
        self._calculate_cash_flow_to_profit_ratio(data_dict)
        
        # 计算营业收入3年CAGR
        self._calculate_revenue_cagr(data_dict)
        
        # 计算应收账款/营业收入
        self._calculate_accounts_receivable_to_revenue(data_dict)

        return data_dict
    
    def _calculate_roe_metrics(self, data_dict):
        """计算ROE相关指标"""
        # 计算REPORT_PERIOD与ANN_DT的时间差
        df = data_dict['financial_indicators'].copy()
        df['ANN_DT'] = pd.to_datetime(df['ANN_DT'])
        df['REPORT_PERIOD'] = pd.to_datetime(df['REPORT_PERIOD'])
        df['date_diff'] = df['ANN_DT'] - df['REPORT_PERIOD']
        # 按照股票和ANN_DT分组，选择date_diff最小的记录
        df_filter = (
            df.sort_values('date_diff')
            .groupby(['S_INFO_WINDCODE', 'ANN_DT'])
            .first().reset_index().drop(columns='date_diff')
        )
        df_sorted = df_filter.sort_values('ANN_DT')
        df_lst = df_sorted.groupby('S_INFO_WINDCODE').last()
        df_lst = df_lst.reset_index()
        data_dict['df_lst'] = df_lst

        # 仅保留年报（REPORT_PERIOD为12-31）
        df_annual = df_filter[df_filter['REPORT_PERIOD'].dt.month == 12].copy()
        # 按股票和财报截止日排序
        df_annual = df_annual.sort_values(['S_INFO_WINDCODE', 'REPORT_PERIOD'])
        # 标记连续年份(确保每年递增一年)
        df_annual['year'] = df_annual['REPORT_PERIOD'].dt.year
        df_annual['year_diff'] = df_annual.groupby('S_INFO_WINDCODE')['year'].diff().fillna(1)

        # 筛选最近连续3年的数据(year_diff为1表示连续)
        valid_records = []
        for code, group in df_annual.groupby('S_INFO_WINDCODE'):
            group = group.sort_values('year', ascending=False)
            # 查找最近连续为3年的区间
            if len(group) >= 3:
                for i in range(len(group) - 2):
                    if all(group['year_diff'].iloc[:3] == 1):
                        valid_records.append(group.iloc[:3])
                        break
        df_3years = pd.concat(valid_records) if valid_records else pd.DataFrame()
        
        # 计算ROE均值和波动率
        if not df_3years.empty:
            df_pivot = df_3years.pivot_table(
                index='S_INFO_WINDCODE',
                columns='year',
                values='S_FA_ROE_DEDUCTED',
                aggfunc='first'
            )
            df_pivot['ROE_3y_AVG'] = df_pivot.mean(axis=1)
            df_pivot['ROE_3y_STD'] = df_pivot.std(axis=1)
            df_pivot['ROE_VOLATILITY'] = df_pivot['ROE_3y_STD'] / df_pivot['ROE_3y_AVG'].abs()
            df_result = df_pivot.reset_index()
            data_dict['df_result'] = df_result
        else:
            # 创建空的结果DataFrame
            data_dict['df_result'] = pd.DataFrame(columns=['S_INFO_WINDCODE', 'ROE_3y_AVG', 'ROE_VOLATILITY'])
    
    def _calculate_cash_flow_to_profit_ratio(self, data_dict):
        """计算经营现金流净额/净利润"""
        df_NCFO_NPEMII = pd.merge(data_dict['cashflow_data'], data_dict['income_data'], on=['S_INFO_WINDCODE', 'REPORT_PERIOD'], how='left')
        df_NCFO_NPEMII['NCFO_NPEMII'] = df_NCFO_NPEMII['NET_CASH_FLOWS_OPER_ACT'] / df_NCFO_NPEMII['NET_PROFIT_EXCL_MIN_INT_INC']
        # 根据股票分组选择最近的报告日期的数据
        df_NCFO_NPEMII = df_NCFO_NPEMII.sort_values('REPORT_PERIOD')
        df_NCFO_NPEMII = df_NCFO_NPEMII.groupby('S_INFO_WINDCODE').last()
        df_NCFO_NPEMII = df_NCFO_NPEMII.reset_index()
        data_dict['df_NCFO_NPEMII'] = df_NCFO_NPEMII


    def _calculate_revenue_cagr(self, data_dict):
        """计算营业收入3年CAGR"""
        df_oi3CAGR = data_dict['income_data'].copy()
        df_oi3CAGR = df_oi3CAGR[df_oi3CAGR['REPORT_PERIOD'].str.endswith('1231')]  # 筛选年报
        df_oi3CAGR = df_oi3CAGR.sort_values(['S_INFO_WINDCODE', 'REPORT_PERIOD'])
        # 分组应用计算
        cagr_result = df_oi3CAGR.groupby('S_INFO_WINDCODE').apply(calculate_revenue_cagr).reset_index()
        cagr_result.columns = ['S_INFO_WINDCODE', 'OPER_REV_CAGR3']
        data_dict['cagr_result'] = cagr_result
    
    def _calculate_accounts_receivable_to_revenue(self, data_dict):
        """计算应收账款/营业收入"""
        df_OIAR = pd.merge(data_dict['balance_sheet_data'], data_dict['income_data'], on=['S_INFO_WINDCODE', 'REPORT_PERIOD'], how='left')
        df_OIAR['OIAR'] = df_OIAR['ACCT_RCV'] / df_OIAR['OPER_REV']
        # 根据股票分组选择最近的公告日期的数据
        df_OIAR = df_OIAR.sort_values('REPORT_PERIOD')
        df_OIAR = df_OIAR.groupby('S_INFO_WINDCODE').last()
        df_OIAR = df_OIAR.reset_index()
        data_dict['df_OIAR'] = df_OIAR


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
        
        # 合并PB、PE-TTM信息
        merged_df2 = pd.merge(merged_df1, data_dict['valuation_data'], on=['S_INFO_WINDCODE'], how='left')
        
        # 合并资产负债率，流动比率，自由现金流，应收账款周转率信息
        merged_df3 = pd.merge(merged_df2, data_dict['df_lst'], on=['S_INFO_WINDCODE'], how='left')
        
        # 合并连续三年ROE(扣非)，连续三年ROE(扣非)波动率信息
        merged_df4 = pd.merge(merged_df3, data_dict['df_result'][['S_INFO_WINDCODE', 'ROE_3y_AVG', 'ROE_VOLATILITY']],
                              on=['S_INFO_WINDCODE'], how='left')
        
        # 合并企业价值倍数财务数据
        merged_df4['CaihuiCODE'] = merged_df4['S_INFO_WINDCODE'].str.split(".").str[0]
        merged_df5 = pd.merge(merged_df4, data_dict['enterprise_value_data'], left_on=['CaihuiCODE'], right_on=['SYMBOL'], how='left')
        
        # 合并财务数据
        merged_df6 = pd.merge(merged_df5, data_dict['df_NCFO_NPEMII'][['S_INFO_WINDCODE', 'NCFO_NPEMII']], on=['S_INFO_WINDCODE'],
                              how='left')
        merged_df7 = pd.merge(merged_df6, data_dict['cagr_result'], on=['S_INFO_WINDCODE'], how='left')
        merged_df8 = pd.merge(merged_df7, data_dict['df_OIAR'][['S_INFO_WINDCODE', 'OIAR']], on=['S_INFO_WINDCODE'], how='left')

        print(f'merged_df8:{merged_df8.shape}')
        print(f'最终股票数量：{len(merged_df8["S_INFO_WINDCODE"].unique())}')

        # 筛选所需的数据列
        res_df = merged_df8[
            ['S_INFO_WINDCODE', 'TRADE_DT', 'INDECODE', 'NAME', 'S_VAL_PB_NEW', 'S_VAL_PE_TTM', 'ROE_3y_AVG',
             'ROE_VOLATILITY', 'EVEBITDA', 'S_FA_DEBTTOASSETS', 'S_FA_CURRENT', 'NCFO_NPEMII', 'S_FA_FCFF', 'OIAR',
             'S_FA_ARTURN', 'OPER_REV_CAGR3']]
        res_df = res_df.dropna()
        
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
                self.config_path=os.path.join('', 'premium_value_strategy.json')

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
                 use_config=False,config_path=None):
        """
        初始化策略
        
        参数:
            start_date: 开始日期
            end_date: 结束日期
            rebalance_freq: 调仓频率，默认为季度('Q')
            rebalance_period: 调仓周期(天数)
            use_config: 是否使用配置文件
            config_path: 配置文件路径
        """
        data_reader = PremiumValueDataReader()
        data_processor = PremiumValueDataProcessor()
        stock_filter = PremiumValueStockFilter()
        feature_calculator = PremiumValueFeatureCalculator()

        #如果使用配置文件
        if use_config:
            if config_path is None:
                config_path = os.path.join('', 'premium_value_strategy.json')

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
    pv_strategy_config = PremiumValueStrategy(use_config=True)
    pv_rebalance_config = pv_strategy_config.run()
    pv_strategy_config.save_results(pv_rebalance_config,'premium_value_strategy_config.csv')


    # print("\n===== 优质价值策略 - 等权重分配 =====")
    # pv_strategy_equal = PremiumValueStrategy('20200427', '20210425',rebalance_period=60)  #调仓周期(交易日天数)，默认为60天
    # pv_strategy_equal.stock_selector = PremiumValueStockSelector(weight_method='equal', use_config=True, config_path='utils/premium_value_strategy.json')
    # pv_rebalance_equal = pv_strategy_equal.run()
    # # pv_strategy_equal.save_results(pv_rebalance_equal, 'premium_value_strategy_equal_weight.csv')
    # pv_strategy_equal.save_results(pv_rebalance_equal)


if __name__ == "__main__":
    main()