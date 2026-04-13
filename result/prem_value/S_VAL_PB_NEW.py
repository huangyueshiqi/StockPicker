# [Retry 1]
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime, timedelta

class CalculateFactor:
    def __init__(self):
        # 初始化数据库连接
        self.wind_engine = create_engine('oracle+cx_oracle://wind:wind@10.6.60.114:1521/wind')
        self.jylh_engine = create_engine('oracle+cx_oracle://jylh:jylh@10.6.60.114:1521/wind')
    
    def get_calendar_date(self, end_date, delta_months):
        """
        根据结束日期和月份差计算开始日期
        :param end_date: 结束日期，格式YYYYMMDD
        :param delta_months: 需要回溯的月份数
        :return: 开始日期，格式YYYYMMDD
        """
        end_date_dt = datetime.strptime(end_date, '%Y%m%d')
        start_date_dt = end_date_dt - timedelta(days=delta_months*30)
        return start_date_dt.strftime('%Y%m%d')
    
    def get_pb_data(self, start_date, end_date):
        """
        从数据库获取市净率数据
        :param start_date: 开始日期，格式YYYYMMDD
        :param end_date: 结束日期，格式YYYYMMDD
        :return: 包含市净率数据的DataFrame
        """
        # 原始SQL语句
        sql = """
        SELECT 
            S_INFO_WINDCODE,
            TRADE_DT,
            S_VAL_PB_NEW
        FROM 
            AShareEODDerivativeIndicator
        WHERE 
            TRADE_DT BETWEEN '{start_date}' AND '{end_date}'  -- 日期范围参数
            AND S_VAL_PB_NEW IS NOT NULL  -- 排除PB为NULL的数据(根据表描述，负值已被置空)
        ORDER BY 
            S_INFO_WINDCODE,
            TRADE_DT
        """.format(start_date=start_date, end_date=end_date).replace(';', '')
        
        # 执行查询并标准化列名（确保列名大写）
        df = pd.read_sql(sql, self.wind_engine)
        df.columns = df.columns.str.upper()  # 确保列名全部大写
        return df
    
    def process_pb_data(self, df, date):
        """
        处理市净率数据，获取指定日期的数据
        :param df: 原始市净率数据
        :param date: 计算日期，格式YYYYMMDD
        :return: 处理后的因子数据
        """
        # 筛选指定日期的数据，确保使用大写的列名
        result = df[df['TRADE_DT'] == date].copy()
        
        # 确保包含所有需要的列
        if 'S_VAL_PB_NEW' not in result.columns:
            result['S_VAL_PB_NEW'] = None
            
        # 只保留需要的列（使用大写列名）
        result = result[['S_INFO_WINDCODE', 'TRADE_DT', 'S_VAL_PB_NEW']]
        
        return result
    
    def main(self, date):
        """
        主函数，计算指定日期的市净率因子
        :param date: 计算日期，格式YYYYMMDD
        :return: 包含因子值的DataFrame
        """
        try:
            # 验证日期格式
            datetime.strptime(date, '%Y%m%d')
        except ValueError:
            raise ValueError("日期格式错误，应为YYYYMMDD格式")
            
        # 获取最近一个月的PB数据
        start_date = self.get_calendar_date(date, 1)
        
        # 从数据库获取数据
        pb_df = self.get_pb_data(start_date, date)
        
        if pb_df.empty:
            print(f"警告：在{date}附近未找到市净率数据")
            # 返回空DataFrame，但保持结构一致
            return pd.DataFrame(columns=['S_INFO_WINDCODE', 'TRADE_DT', 'S_VAL_PB_NEW'])
        
        # 处理数据，获取指定日期的PB值
        factor_df = self.process_pb_data(pb_df, date)
        
        # 如果指定日期没有数据，尝试获取最近有数据的日期
        if factor_df.empty:
            # 获取每个股票在指定日期前最近的数据
            pb_df['TRADE_DT'] = pd.to_datetime(pb_df['TRADE_DT'], format='%Y%m%d')
            date_dt = datetime.strptime(date, '%Y%m%d')
            
            # 筛选日期小于等于指定日期的数据
            pb_df = pb_df[pb_df['TRADE_DT'] <= date_dt]
            
            # 获取每个股票的最新数据
            factor_df = pb_df.sort_values(['S_INFO_WINDCODE', 'TRADE_DT'])\
                            .groupby('S_INFO_WINDCODE').last().reset_index()
            
            # 转换回字符串格式
            factor_df['TRADE_DT'] = factor_df['TRADE_DT'].dt.strftime('%Y%m%d')
            
            # 只保留需要的列
            factor_df = factor_df[['S_INFO_WINDCODE', 'TRADE_DT', 'S_VAL_PB_NEW']]
            
            print(f"警告：{date}当日无PB数据，使用最近可用数据替代")
        
        # 设置计算日期为输入日期（即使使用的是之前的数据）
        factor_df['TRADE_DT'] = date
        
        return factor_df


if __name__ == "__main__":
    # 示例用法
    calculator = CalculateFactor()
    result = calculator.main('20230101')
    print(result.head())