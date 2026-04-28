import time
import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta

from framework.stock_logic_framework import (
    SimpleFilterCondition, CompoundFilterCondition, CustomFilterCondition,
    StockFilterPipeline, EqualWeightAllocator, MarketCapWeightAllocator,
    IndustryEqualWeightAllocator, FactorWeightAllocator, DimensionalRankMethod
)

from framework.strategy_framework import (
    BaseDataReader, BaseDataProcessor, BaseStockFilter,
    BaseFeatureCalculator, BaseStockSelector, BaseStrategy
)
from utils.helpers import rebalancing_day
from utils.helpers import (
    execute_query, WIND_DB, JYLH_DB, FINCHINA_DB,
    get_date_range, filter_and_clean_dataframe, get_stock_listing_data,
    filter_stocks_by_listing_age,calculate_year_cagr,select_recent_5years,
    calculate_financial_ratios,rank_indicators
)


"""
   巴菲特策略
   已废弃，但可能有参考价值，待修改
"""

class BuffettDataReader(BaseDataReader):
    """
    巴菲特策略的数据读取器
    """
    def __init__(self):
        self.need_start_date = True  # 该策略需要开始日期
        
    def read_data(self, start_date=None, end_date=None) -> dict:
        """
        从数据库读取所需数据
        
        参数:
            start_date: 开始日期
            end_date: 结束日期
            
        返回:
            包含所有数据的字典
        """
        # 获取股票上市日期数据
        df_date = get_stock_listing_data()
        print(f'df_date:{df_date.shape}')
        
        # 获取成交金额数据
        sql = "select S_INFO_WINDCODE,TRADE_DT,S_DQ_AMOUNT from ASHAREEODPRICES where TRADE_DT between :start_date and :end_date"
        df_amount = execute_query(WIND_DB, sql, (start_date, end_date))
        print(f'df_amount:{df_amount.shape}')
        
        # 获取财务指标数据
        sql = ("select S_INFO_WINDCODE,ANN_DT,REPORT_PERIOD,S_FA_ROE,S_FA_GROSSPROFITMARGIN,S_FA_ROIC,RD_EXPENSE,S_FA_DEBTTOASSETS,S_FA_INTERESTDEBT,S_FA_EBITDA "
               "from ASHAREFINANCIALINDICATOR where ANN_DT < :date_param "
               "and REPORT_PERIOD BETWEEN TO_CHAR(ADD_MONTHS(TO_DATE(:date_param, 'YYYY-MM-DD'), -60), 'YYYYMMDD') AND TO_CHAR(TO_DATE(:date_param, 'YYYY-MM-DD'), 'YYYYMMDD')")
        df = execute_query(WIND_DB, sql, (end_date,))
        print(f'df:{df.shape}')
        
        # 获取估值指标数据
        sql = "select S_INFO_WINDCODE,TRADE_DT,S_VAL_MV,S_VAL_PB_NEW,S_VAL_PE_TTM,S_VAL_PCF_OCF from ASHAREEODDERIVATIVEINDICATOR where TRADE_DT between :start_date and :end_date"
        df1 = execute_query(WIND_DB, sql, (start_date, end_date))
        print(f'df1:{df1.shape}')
        
        # 获取现金流数据
        sql = ("select S_INFO_WINDCODE,STATEMENT_TYPE,ACTUAL_ANN_DT,REPORT_PERIOD,NET_CASH_FLOWS_OPER_ACT,NET_PROFIT,CASH_CASH_EQU_END_PERIOD "
               "from ASHARECASHFLOWHIS where STATEMENT_TYPE IN (408001000,408005000,408027000,408028000,408003600,408045000) "
               "and  ACTUAL_ANN_DT < :date_param and  REPORT_PERIOD BETWEEN TO_CHAR(ADD_MONTHS(TO_DATE(:date_param, 'YYYY-MM-DD'), -60), 'YYYYMMDD') AND TO_CHAR(TO_DATE(:date_param, 'YYYY-MM-DD'), 'YYYYMMDD')")
        df2 = execute_query(WIND_DB, sql, (end_date,))
        print(f'df2:{df2.shape}')
        
        # 获取利润表数据
        sql = ("select S_INFO_WINDCODE,STATEMENT_TYPE,ACTUAL_ANN_DT,REPORT_PERIOD,NET_PROFIT_EXCL_MIN_INT_INC,TOT_OPER_REV "
               "from ASHAREINCOMEHIS where STATEMENT_TYPE IN (408001000,408005000,408027000,408028000,408003600,408045000) "
               "and ACTUAL_ANN_DT< :date_param  and  REPORT_PERIOD BETWEEN TO_CHAR(ADD_MONTHS(TO_DATE(:date_param, 'YYYY-MM-DD'), -60), 'YYYYMMDD') AND TO_CHAR(TO_DATE(:date_param, 'YYYY-MM-DD'), 'YYYYMMDD')")
        df3 = execute_query(WIND_DB, sql, (end_date,))
        print(f'df3:{df3.shape}')
        
        # 获取企业价值倍数数据
        sql = "select SYMBOL,TRADEDATE,LYDY,EVEBITDA from TQ_SK_FININDIC where TRADEDATE between :start_date and :end_date"
        df4 = execute_query(FINCHINA_DB, sql, (start_date, end_date))
        print(f'df4:{df4.shape}')
        
        # 获取净利润数据（用于计算CAGR）
        five_years_ago = get_date_range(end_date, 6)  # 往前推6年以确保有足够数据计算5年增长率
        sql = ("select S_INFO_WINDCODE,STATEMENT_TYPE,ACTUAL_ANN_DT,REPORT_PERIOD,NET_PROFIT_EXCL_MIN_INT_INC "
               "from ASHAREINCOMEHIS where STATEMENT_TYPE IN (408001000,408005000,408027000,408028000,408003600,408045000) "
               "and ACTUAL_ANN_DT < :date_param and  REPORT_PERIOD BETWEEN TO_CHAR(ADD_MONTHS(TO_DATE(:date_param, 'YYYY-MM-DD'), -72), 'YYYYMMDD') AND TO_CHAR(TO_DATE(:date_param, 'YYYY-MM-DD'), 'YYYYMMDD')  order by REPORT_PERIOD")
        df5 = execute_query(WIND_DB, sql, (end_date,))
        print(f'df5:{df5.shape}')
        
        # 获取分红数据
        sql = "select ID,STOCKCODE,AFTTAXCASHDVCNY,XDRDATE from JY_QY_STOCKDIVIDENTS_CS where (GRAOBJTYPE = '1' or GRAOBJTYPE = '2') and DIVITYPE in ('1','5','15','18','58','158') and XDRDATE between :start_date and :end_date"
        df6 = execute_query(JYLH_DB, sql, (start_date, end_date))
        print(f'df6:{df6.shape}')
        
        return {
            'listing_data': df_date,
            'turnover_data': df_amount,
            'financial_indicators': df,
            'valuation_data': df1,
            'cashflow_data': df2,
            'income_data': df3,
            'enterprise_value_data': df4,
            'profit_data': df5,
            'dividend_data': df6,
        }


class BuffettDataProcessor(BaseDataProcessor):
    """
    巴菲特策略的数据处理器
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
        
        # 过滤成交金额为0的行
        data_dict["turnover_data"] = data_dict["turnover_data"][data_dict["turnover_data"]['S_DQ_AMOUNT'] > 0]
        print(f'过滤成交金额后turnover_data:{data_dict["turnover_data"].shape}')

        # 计算净利润3年CAGR
        self._calculate_profit_cagr(data_dict, end_date)
        
        # 计算分红稳定性（连续五年分红）
        self._calculate_dividend_stability(data_dict)
        
        # 计算盈利波动性（过去5年净利润标准差（变异系数））
        self._calculate_profit_volatility(data_dict, end_date)

        return data_dict



    def _calculate_profit_cagr(self, data_dict, end_date):
        """计算净利润3年CAGR"""
        data_dict["profit_data"] = data_dict["profit_data"][data_dict["profit_data"]['REPORT_PERIOD'].str.endswith('1231')]  # 筛选年报
        data_dict["profit_data"] = data_dict["profit_data"].sort_values(['S_INFO_WINDCODE', 'REPORT_PERIOD'])
        cagr_result = data_dict["profit_data"].groupby('S_INFO_WINDCODE').apply(calculate_year_cagr).reset_index()
        cagr_result.columns = ['S_INFO_WINDCODE', 'NPEMII_CAGR3']
        data_dict['profit_cagr'] = cagr_result
    
    def _calculate_dividend_stability(self, data_dict):
        """计算分红稳定性（连续五年分红）"""
        # 提取年份并分组统计
        data_dict["dividend_data"]['year'] = pd.to_datetime(data_dict["dividend_data"]['XDRDATE']).dt.year
        yearly_counts = data_dict["dividend_data"].groupby(['STOCKCODE', 'year']).size().reset_index(name='count')
        # 计算每只股票有分红的年份数
        years_with_dividends = yearly_counts.groupby('STOCKCODE')['year'].nunique().reset_index(name='dividend_years')
        # 合并回原数据，处理缺失值
        result_dividend = years_with_dividends[years_with_dividends['dividend_years'] >= 5]
        data_dict["years_with_dividends"] = years_with_dividends
    
    def _calculate_profit_volatility(self, data_dict, end_date):
        """计算盈利波动性（过去5年净利润标准差（变异系数））"""
        # 将报告日期转换为datetime格式，并提取年份
        df_volatility = data_dict["profit_data"].copy()
        df_volatility = df_volatility[df_volatility['REPORT_PERIOD'].str.endswith('1231')]  # 筛选年报
        df_volatility['REPORT_PERIOD'] = pd.to_datetime(df_volatility['REPORT_PERIOD'], format='%Y%m%d')
        df_volatility['year'] = df_volatility['REPORT_PERIOD'].dt.year
        # 同一股票同一年份多条记录，保留最后一条
        df_annual = df_volatility.sort_values('REPORT_PERIOD').groupby(['S_INFO_WINDCODE', 'year']).last().reset_index()
        # 筛选过去五年数据
        df_past5 = df_annual.groupby('S_INFO_WINDCODE').apply(select_recent_5years).reset_index(drop=True)

        # 剔除数据不完整的股票
        valid_stocks = df_past5.groupby('S_INFO_WINDCODE').filter(lambda x: len(x) == 5)['S_INFO_WINDCODE'].unique()
        df_final = df_past5[df_past5['S_INFO_WINDCODE'].isin(valid_stocks)]
        # 计算CV
        cv_results = df_final.groupby('S_INFO_WINDCODE')['NET_PROFIT_EXCL_MIN_INT_INC'].agg(
            lambda x: x.std() / x.mean()
        )
        cv_df = cv_results.reset_index()
        cv_df.columns = ['S_INFO_WINDCODE', '5year_cv']
        data_dict["profit_volatility"] = cv_df


class BuffettStockFilter(BaseStockFilter):
    """
    巴菲特策略的股票筛选器
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
        # 筛选上市时间超过阈值且日成交额达标的股票
        listing_threshold = kwargs.get('listing_threshold', 3)  # 最小上市年限(默认三年)
        min_daily_turnover = kwargs.get('min_daily_turnover', 50000)  # 最小日成交额(默认5000万)
        
        # 筛选上市时间符合条件的股票
        eligible_stocks = filter_stocks_by_listing_age(data_dict['listing_data'], date, listing_threshold)
        
        # 筛选日成交额达标的股票
        filtered_amount = data_dict['turnover_data'].groupby('S_INFO_WINDCODE').filter(
            lambda x: (x['S_DQ_AMOUNT'] >= min_daily_turnover).all())  # 日成交额S_DQ_AMOUNT字段单位为千元

        s1 = list(filtered_amount['S_INFO_WINDCODE'])
        s2 = eligible_stocks

        # 取交集
        inter_stock = list(set(s1) & set(s2))
        return inter_stock


class BuffettFeatureCalculator(BaseFeatureCalculator):
    """
    巴菲特策略的特征计算器
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
        res_df = data_dict['financial_indicators'][data_dict['financial_indicators']['S_INFO_WINDCODE'].isin(stock_list)].dropna()
        res_df1 = data_dict['valuation_data'][data_dict['valuation_data']['S_INFO_WINDCODE'].isin(stock_list)].dropna()
        merged_df = pd.merge(res_df, res_df1, left_on=['S_INFO_WINDCODE', 'REPORT_PERIOD'], right_on=['S_INFO_WINDCODE', 'TRADE_DT'], how='left')
        
        # 根据股票代码和公告日期进行合并其它指标数据
        merged_df1 = pd.merge(merged_df, data_dict['cashflow_data'], left_on=['S_INFO_WINDCODE', 'REPORT_PERIOD'],
                              right_on=['S_INFO_WINDCODE', 'REPORT_PERIOD'], how='left')
        merged_df2 = pd.merge(merged_df1, data_dict['income_data'], left_on=['S_INFO_WINDCODE', 'REPORT_PERIOD'],
                              right_on=['S_INFO_WINDCODE', 'REPORT_PERIOD'], how='left')
        
        # 合并财汇的数据，财汇的股票编码只有前六位
        merged_df2['CaihuiCODE'] = merged_df2['S_INFO_WINDCODE'].str.split(".").str[0]
        merged_df3 = pd.merge(merged_df2, data_dict['enterprise_value_data'], left_on=['CaihuiCODE', 'REPORT_PERIOD'], right_on=['SYMBOL', 'TRADEDATE'],
                              how='left')
        # 去除NaN值
        merged_df4 = merged_df3.dropna()

        # 合并CAGR数据
        merged_df5 = pd.merge(merged_df4, data_dict["profit_cagr"], on=['S_INFO_WINDCODE'], how='left')
        
        # 合并分红数据
        merged_df6 = pd.merge(merged_df5, data_dict["years_with_dividends"], left_on=['S_INFO_WINDCODE'], right_on=['STOCKCODE'],
                              how='left')
        
        # 合并波动性数据
        merged_df7 = pd.merge(merged_df6, data_dict["profit_volatility"], left_on=['S_INFO_WINDCODE'], right_on=['S_INFO_WINDCODE'],
                              how='left')

        merged_df7 = merged_df7.dropna()
        print(f'merged_df7:{merged_df7.shape}')
        print(f'最终股票数量：{len(merged_df7["S_INFO_WINDCODE"].unique())}')

        # 计算财务比率
        result_df = calculate_financial_ratios(merged_df7)
        
        return result_df


# 巴菲特策略改造示例
class BuffettStockSelector(BaseStockSelector):
    """
    使用新框架实现的巴菲特策略选股器
    """

    def __init__(self, weight_method: str = 'equal'):
        """
        初始化巴菲特策略选股器

        参数:
            weight_method: 权重分配方式，支持'equal'(等权), 'market_cap'(市值加权),
                          'industry_equal'(行业等权), 'factor'(因子加权)
        """
        self.weight_method = weight_method

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
        top_K = kwargs.get('top_K', 20)  # 默认选择前20只股票

        # 创建筛选排序流水线
        pipeline = StockFilterPipeline(name="巴菲特策略流水线", description="巴菲特价值投资策略")

        # 设置排序方法 - 使用多维度排序
        dimension_weights = {
            '盈利能力': 0.3,
            '成长能力': 0.2,
            '分红能力': 0.15,
            '安全性': 0.2,
            '价值水平': 0.15,
        }

        indicator_groups = {
            '盈利能力': ['S_FA_ROE', 'S_FA_GROSSPROFITMARGIN', 'S_FA_ROIC', 'NCFOA_NP'],
            '成长能力': ['NPEMII_CAGR3', 'RE_TOR'],
            '分红能力': ['LYDY', 'dividend_years'],
            '安全性': ['S_FA_DEBTTOASSETS', 'SFI_SFE', 'CCEEP_SVM', '5year_cv'],
            '价值水平': ['S_VAL_PB_NEW', 'S_VAL_PE_TTM', 'S_VAL_PCF_OCF', 'EVEBITDA'],
        }

        indicator_directions = {
            'S_FA_ROE': True,
            'S_FA_GROSSPROFITMARGIN': True,
            'S_FA_ROIC': True,
            'NCFOA_NP': True,
            'NPEMII_CAGR3': True,
            'RE_TOR': True,
            'LYDY': True,
            'dividend_years': True,
            'S_FA_DEBTTOASSETS': False,
            'SFI_SFE': False,
            'CCEEP_SVM': True,
            '5year_cv': False,
            'S_VAL_PB_NEW': False,
            'S_VAL_PE_TTM': False,
            'S_VAL_PCF_OCF': False,
            'EVEBITDA': False,
        }

        rank_method = DimensionalRankMethod(
            name="巴菲特多维度排序",
            dimension_weights=dimension_weights,
            indicator_groups=indicator_groups,
            indicator_directions=indicator_directions,
            description="基于巴菲特投资理念的多维度指标排序"
        )

        pipeline.set_rank_method(rank_method)

        # 设置权重分配器
        if self.weight_method == 'equal':
            # 等权重分配
            pipeline.set_weight_allocator(EqualWeightAllocator())
        elif self.weight_method == 'market_cap':
            # 市值加权分配
            pipeline.set_weight_allocator(MarketCapWeightAllocator(market_cap_column='S_VAL_MV'))
        elif self.weight_method == 'industry_equal':
            # 行业等权分配
            pipeline.set_weight_allocator(IndustryEqualWeightAllocator(industry_column='NAME'))
        elif self.weight_method == 'factor':
            # 基于ROE的因子加权
            pipeline.set_weight_allocator(FactorWeightAllocator(factor_column='S_FA_ROE', is_ascending=False))
        else:
            # 默认使用等权重
            pipeline.set_weight_allocator(EqualWeightAllocator())

        # 运行流水线
        result_df, stock_list, weight_list = pipeline.run(feature_df, top_k=top_K)

        print(f'top_stocks:{stock_list}')
        print(f'weights:{[round(w, 4) for w in weight_list]}')

        return stock_list, weight_list


class BuffettStrategy(BaseStrategy):
    """
    巴菲特策略
    """
    def __init__(self, start_date, end_date, rebalance_freq='Q'):
        """
        初始化策略
        
        参数:
            start_date: 开始日期
            end_date: 结束日期
            rebalance_freq: 调仓频率，默认为季度('Q')
        """
        data_reader = BuffettDataReader()
        data_processor = BuffettDataProcessor()
        stock_filter = BuffettStockFilter()
        feature_calculator = BuffettFeatureCalculator()
        stock_selector = BuffettStockSelector()
        
        super().__init__(
            data_reader=data_reader,
            data_processor=data_processor,
            stock_filter=stock_filter,
            feature_calculator=feature_calculator,
            stock_selector=stock_selector,
            start_date=start_date,
            end_date=end_date,
            rebalance_freq=rebalance_freq
        )


# 使用示例
def main():
    # 创建并运行策略
    print("\n===== 巴菲特策略 - 等权重分配 =====")
    buffett_strategy_equal = BuffettStrategy('20200320', '20250410')
    buffett_strategy_equal.stock_selector = BuffettStockSelector(weight_method='equal')
    buffett_rebalance_equal = buffett_strategy_equal.run()
    buffett_strategy_equal.save_results(buffett_rebalance_equal, 'buffett_strategy_equal_weight1.csv')


if __name__ == "__main__":
    main()