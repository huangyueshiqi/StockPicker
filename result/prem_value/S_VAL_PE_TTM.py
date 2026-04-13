# [Retry 1]
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime, timedelta
from typing import Optional

class CalculateFactor:
    def __init__(self):
        """初始化数据库连接"""
        self.engine_wind = create_engine('oracle+cx_oracle://wind:wind@10.6.60.114:1521/wind')
        
    def get_trading_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        从AShareEODDerivativeIndicator表获取PE数据
        
        参数:
            start_date: 开始日期(YYYYMMDD)
            end_date: 结束日期(YYYYMMDD)
            
        返回:
            包含PE数据的DataFrame
        """
        sql = f"""
        SELECT 
            S_INFO_WINDCODE as stock_code,      -- Wind代码
            TRADE_DT as trade_date,             -- 交易日期(YYYYMMDD格式)
            S_VAL_PE as pe,                     -- 市盈率(PE)
            S_VAL_PE_TTM as pe_ttm,             -- 市盈率(PE,TTM)
            S_VAL_PB_NEW as pb,                 -- 市净率(PB)
            S_DQ_CLOSE_TODAY as close_price     -- 当日收盘价
        FROM 
            AShareEODDerivativeIndicator
        WHERE 
            TRADE_DT BETWEEN '{start_date}' AND '{end_date}'  -- 日期范围参数
            AND S_VAL_PE IS NOT NULL                      -- 排除PE为空的记录
        ORDER BY 
            S_INFO_WINDCODE, 
            TRADE_DT DESC
        """
        # 移除SQL末尾可能存在的分号
        sql = sql.replace(';', '')
        
        try:
            df = pd.read_sql(sql, self.engine_wind)
            # 确保列名统一为小写
            df.columns = df.columns.str.lower()
            return df
        except Exception as e:
            print(f"获取PE数据失败: {e}")
            return pd.DataFrame()
    
    def get_latest_data(self, date: str) -> pd.DataFrame:
        """
        获取指定日期的最新PE数据
        
        参数:
            date: 查询日期(YYYYMMDD)
            
        返回:
            包含最新PE数据的DataFrame
        """
        # 获取前5个交易日的数据以确保能获取到最新数据
        start_date = self.get_previous_trading_date(date, days=5)
        df = self.get_trading_data(start_date, date)
        
        if not df.empty:
            # 获取每个股票的最新记录
            df_latest = df.groupby('stock_code').first().reset_index()
            return df_latest
        return pd.DataFrame()
    
    def get_previous_trading_date(self, date: str, days: int = 1) -> str:
        """
        获取指定日期前days个交易日的日期
        
        参数:
            date: 基准日期(YYYYMMDD)
            days: 向前追溯的天数
            
        返回:
            前days个交易日的日期(YYYYMMDD)
        """
        # 简单实现: 实际应用中应该查询交易日历表
        # 这里简化处理，直接减去天数
        dt = datetime.strptime(date, '%Y%m%d')
        prev_dt = dt - timedelta(days=days)
        return prev_dt.strftime('%Y%m%d')
    
    def main(self, date: str) -> pd.DataFrame:
        """
        主函数: 计算指定日期的PE因子值
        
        参数:
            date: 计算日期(YYYYMMDD)
            
        返回:
            包含因子值的DataFrame, 列: S_INFO_WINDCODE, TRADE_DT, S_VAL_PE_TTM
        """
        # 获取最新PE数据
        df = self.get_latest_data(date)
        
        if df.empty:
            print(f"未获取到{date}的PE数据")
            return pd.DataFrame(columns=['S_INFO_WINDCODE', 'TRADE_DT', 'S_VAL_PE_TTM'])
        
        # 选择需要的列并重命名为要求的输出格式
        result = df[['stock_code', 'trade_date', 'pe_ttm']].copy()
        result.columns = ['S_INFO_WINDCODE', 'TRADE_DT', 'S_VAL_PE_TTM']
        
        # 确保日期格式正确
        result['TRADE_DT'] = date
        
        return result

# 使用示例
if __name__ == "__main__":
    factor_calculator = CalculateFactor()
    # 计算2023年12月29日的PE因子
    result = factor_calculator.main('20231229')
    print(result.head())