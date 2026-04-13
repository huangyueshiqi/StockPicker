import cx_Oracle
import pandas as pd
import numpy as np
from contextlib import contextmanager
from datetime import datetime
from dateutil.relativedelta import relativedelta


'''
该文件中存在一些被弃用的方法，未被删除
'''

@contextmanager
def oracle_connection(username, password, host, service):
    """
    Oracle数据库连接上下文管理器
    
    使用上下文管理器模式确保数据库连接正确关闭，防止资源泄漏
    
    参数:
        username: 数据库用户名
        password: 数据库密码
        host: 数据库主机地址
        service: 数据库服务名
        
    返回:
        数据库连接对象
    """
    connection = cx_Oracle.connect(f'{username}/{password}@{host}/{service}')
    try:
        yield connection
    finally:
        connection.close()


def execute_query(connection_params, sql, params=None):
    """
    执行SQL查询并返回DataFrame
    
    参数:
        connection_params: 包含连接参数的字典 {username, password, host, service}
        sql: SQL查询语句
        params: 查询参数(可选)
        
    返回:
        查询结果DataFrame
    """
    with oracle_connection(
        connection_params['username'],
        connection_params['password'],
        connection_params['host'],
        connection_params['service']
    ) as connection:
        cursor = connection.cursor()
        try:
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
                
            columns = [col[0] for col in cursor.description]
            results = cursor.fetchall()
            df = pd.DataFrame(results, columns=columns)
            
            return df
        finally:
            cursor.close()


# 常用数据库连接参数
WIND_DB = {
    'username': 'wind',
    'password': 'wind',
    'host': '10.6.60.114:1521',
    'service': 'wind'
}

JYLH_DB = {
    'username': 'jylh',
    'password': 'jylh',
    'host': '10.6.60.114:1521',
    'service': 'wind'
}

FINCHINA_DB = {
    'username': 'finchina',
    'password': 'finchina',
    'host': '10.6.60.118:1521',
    'service': 'orcl'
}


def get_date_range(end_date, years_back=5):
    """
    计算从结束日期往前推指定年数的开始日期
    
    参数:
        end_date: 结束日期，格式为'YYYYMMDD'
        years_back: 往前推的年数
        
    返回:
        开始日期，格式为'YYYYMMDD'
    """
    end_dt = datetime.strptime(end_date, '%Y%m%d')
    start_dt = end_dt - relativedelta(years=years_back)
    return start_dt.strftime('%Y%m%d')


def filter_and_clean_dataframe(df):
    """
    对DataFrame进行基本的清洗和过滤
    
    参数:
        df: 输入的DataFrame
        
    返回:
        清洗后的DataFrame
    """
    # 去重
    df = df.drop_duplicates()
    # 删除包含NaN值的行
    df = df.dropna()
    return df


def get_stock_listing_data():
    """
    获取股票上市日期数据
    
    返回:
        包含股票代码和上市日期的DataFrame
    """
    sql = "select S_INFO_WINDCODE,S_INFO_LISTDATE from ASHAREDESCRIPTION"
    return execute_query(WIND_DB, sql)


def filter_stocks_by_listing_age(df_date, current_date, listing_threshold=3):
    """
    筛选上市时间超过阈值的股票
    
    参数:
        df_date: 包含股票上市日期的DataFrame
        current_date: 当前日期，格式为'YYYYMMDD'
        listing_threshold: 最小上市年限(默认三年)
        
    返回:
        符合条件的股票代码列表
    """
    # 日期格式转换与筛选
    current_date = pd.to_datetime(current_date, format='%Y%m%d')
    df_date['LISTDATE'] = pd.to_datetime(df_date['S_INFO_LISTDATE'], format='%Y%m%d')

    mask = ((df_date['LISTDATE'] <= current_date) & 
            ((current_date - df_date['LISTDATE']).dt.days >= listing_threshold * 365))

    filtered_date = df_date.loc[mask, ['S_INFO_WINDCODE', 'S_INFO_LISTDATE']]
    return list(filtered_date['S_INFO_WINDCODE'])

def calculate_revenue_cagr(group):
    """
    计算营业收入3年CAGR

    参数：
        group：按股票分组的DataFrame

    返回：
        CAGR值或NaN
    """
    if len(group) < 3:  # 至少需要3年数据
        return np.nan
    # 取最近3年的营收（按报告期排序）
    latest_rev = group.iloc[-1]['OPER_REV']
    oldest_rev = group.iloc[-3]['OPER_REV']
    cagr = (latest_rev / oldest_rev) ** (1 / 3) - 1
    return cagr


def calculate_year_cagr(group):
    """
    按股票分组使用年报计算CAGR

    参数：
        group：按股票分组的DataFrame

    返回：
        CAGR值或NaN
    """
    if len(group) < 3:  # 至少需要3年数据
        return np.nan
    # 取最近3年的数据（按报告期排序）
    latest_value = group.iloc[-1]['NET_PROFIT_EXCL_MIN_INT_INC']
    oldest_value = group.iloc[-3]['NET_PROFIT_EXCL_MIN_INT_INC']
    cagr = (latest_value / oldest_value) ** (1 / 3) - 1
    return cagr

def select_recent_5years(group):
    """
    选择最近5年的数据

    参数：
        group：包含年份列的DataFrame分组

    返回：
        筛选后的DataFrame
    """
    if len(group) < 5:  # 至少需要5年数据
        return None
    valid_years=sorted([y for y in group['year'].unique()],reverse=True)
    recent_5years=valid_years[:5]
    return group[group['year'].isin(recent_5years)]


def filter_double_low(df,quantile=0.5):
    """
    筛选双低股票(PB和PE均较低)

    参数：
        df：输入的DataFrame

    返回：
        筛选后的DataFrame
    """
    #按行业分组计算分位数
    industry_groups=df.groupby('NAME')
    df['PB_rank']=industry_groups['S_VAL_PB_NEW'].rank(pct=True)
    df['PE_rank'] = industry_groups['S_VAL_PE_TTM'].rank(pct=True)

    #筛选PB和PE分位数均小于50%的股票
    filtered=df[(df['PB_rank']<=quantile)&(df['PE_rank']<=quantile)]
    return filtered.reset_index(drop=True)


def calculate_financial_ratios(df,strategy_type='buffett'):
    """
    计算财务比率

    参数：
        df：输入的DataFrame
        strategy_type：策略类型，'buffett'

    返回：
        添加了财务比率的DataFrame
    """
    result_df=df.copy()

    if strategy_type=='buffett':
        #财务比率
        result_df['NCFOA_NP']=result_df['NET_CASH_FLOWS_OPER_ACT']/result_df['NET_PROFIT']
        result_df['RE_TOR']=result_df['RD_EXPENSE']/result_df['TOT_OPER_REV']
        result_df['SFI_SFE']=result_df['S_FA_INTERESTDEBT']/result_df['S_FA_EBITDA']
        result_df['CCEEP_SVM']=result_df['CASH_CASH_EQU_END_PERIOD']/(result_df['S_VAL_MV']*10000)  #S_VAL_MV为总股本*收盘价，总股本单位为万股

        #标准化百分比指标
        for col in ['S_FA_ROE','S_FA_GROSSPROFITMARGIN','S_FA_DEBTTOASSETS','S_FA_ROIC','LYDY']:
            result_df[col]=result_df[col]/100

    return result_df


def rank_indicators(df, indicator_direction):
    """
    对指标进行排名

    参数：
        df：包含指标的DataFrame
        indicator_direction： 指标方向字典，True表示升序(值越大越好)

    返回：
        添加排名列的DataFrame
    """
    ranked_df = df.copy()
    for indicator,ascending in indicator_direction.items():
        ranked_df[f'{indicator}_rank']=ranked_df[indicator].rank(ascending=ascending,method='min',pct=True)
    return ranked_df


def get_a_calendar_data():
    """
    获取中国A股交易日历数据

    返回:
        交易日历数据DataFrame
    """
    sql = "SELECT * FROM ASHARECALENDAR order by TRADE_DAYS"
    return execute_query(WIND_DB, sql)

def rebalancing_day(start_date, end_date, freq='M', n_business_days=1):
    """
    获取调仓日期列表

    参数:
        start_date: 开始日期
        end_date: 结束日期
        freq: 调仓频率（默认每月初）,支持'W'(周),'M'(月),'Q'(季度),'Y'(年度)
        n_business_days: 取每月第N个交易日

    返回:
        调仓日期列表
    """
    # 将日期字符串转换为日期对象
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    # 获取交易日历数据
    df = get_a_calendar_data()

    # 删除交易日中包含NaN的行
    df_no = df.dropna(subset=['TRADE_DAYS'])
    # 删除除交易日中重复项
    df_no = df_no.drop_duplicates(subset=['TRADE_DAYS']).reset_index(drop=True)
    # 将交易日列转换为日期类型
    df_no['TRADE_DAYS'] = pd.to_datetime(df_no['TRADE_DAYS'])

    # 筛选时间范围内的交易日
    mask = (df_no['TRADE_DAYS'] >= start_dt) & (df_no['TRADE_DAYS'] <= end_dt)
    filtered_days = df_no['TRADE_DAYS'][mask]

    # 生成调仓日
    rebalance_dates = (
        filtered_days.to_frame().groupby(pd.Grouper(key='TRADE_DAYS', freq=freq)).nth(n_business_days - 1))
    # 将结果转换为列表并返回
    rebalance_dates = rebalance_dates['TRADE_DAYS'].dt.strftime('%Y-%m-%d').tolist()

    return rebalance_dates


def rebalancing_by_period(start_date, end_date, period=20):
    """
    根据交易日周期获取调仓日期列表

    参数:
        start_date: 开始日期
        end_date: 结束日期
        period: 调仓周期（交易日数量）

    返回:
        调仓日期列表
    """
    # 将日期字符串转换为日期对象
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    # 获取交易日历数据
    df = get_a_calendar_data()

    # 删除交易日中包含NaN的行
    df_no = df.dropna(subset=['TRADE_DAYS'])
    # 删除除交易日中重复项
    df_no = df_no.drop_duplicates(subset=['TRADE_DAYS']).reset_index(drop=True)
    # 将交易日列转换为日期类型
    df_no['TRADE_DAYS'] = pd.to_datetime(df_no['TRADE_DAYS'])

    # 筛选时间范围内的交易日
    mask = (df_no['TRADE_DAYS'] >= start_dt) & (df_no['TRADE_DAYS'] <= end_dt)
    filtered_days = df_no['TRADE_DAYS'][mask]

    # 按照指定的交易日周期生成调仓日
    rebalance_indices = list(range(0, len(filtered_days), period))
    rebalance_dates = filtered_days.iloc[rebalance_indices].dt.strftime('%Y-%m-%d').tolist()

    return rebalance_dates




















