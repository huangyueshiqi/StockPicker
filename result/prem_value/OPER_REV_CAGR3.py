# [Retry 2]
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from datetime import datetime, timedelta

class CalculateFactor:
    def __init__(self):
        # 初始化数据库连接
        self.wind_engine = create_engine('oracle+cx_oracle://wind:wind@10.6.60.114:1521/wind')
        self.jylh_engine = create_engine('oracle+cx_oracle://jylh:jylh@10.6.60.114:1521/wind')
    
    def get_financial_data(self, end_date):
        """
        从AShareFinancialIndicator表中获取S_QFA_CGRSALES字段的最新年报数据
        """
        # 将YYYYMMDD格式转换为YYYY-MM-DD格式用于SQL查询
        sql_end_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"
        
        # 构建SQL查询（注意移除了末尾的分号）
        sql = f"""
        SELECT 
            WIND_CODE,                -- Wind代码
            REPORT_PERIOD,            -- 报告期(YYYYMMDD格式)
            ANN_DT,                   -- 公告日期
            S_QFA_CGRSALES            -- 单季度.营业收入环比增长率(%)
        FROM (
            SELECT 
                a.WIND_CODE,
                a.REPORT_PERIOD,
                a.ANN_DT,
                a.S_QFA_CGRSALES,
                -- 按公司和报告期分组，取每个报告期最新的公告数据
                ROW_NUMBER() OVER (PARTITION BY a.WIND_CODE, a.REPORT_PERIOD ORDER BY a.ANN_DT DESC) AS rn
            FROM 
                AShareFinancialIndicator a
            WHERE 
                -- 限制为年报数据(报告期月份为12)
                SUBSTR(a.REPORT_PERIOD, 5, 2) = '12'
                -- 确保报告发布日期在指定日期之前
                AND a.ANN_DT <= TO_CHAR(TO_DATE('{sql_end_date}', 'YYYY-MM-DD'), 'YYYYMMDD')
                -- 确保报告期在[End_Date - 5年, End_Date]之间
                AND a.REPORT_PERIOD BETWEEN 
                    TO_CHAR(ADD_MONTHS(TO_DATE('{sql_end_date}', 'YYYY-MM-DD'), -60), 'YYYYMMDD') 
                    AND TO_CHAR(TO_DATE('{sql_end_date}', 'YYYY-MM-DD'), 'YYYYMMDD')
        ) tmp_LatestReport
        WHERE 
            rn = 1  -- 只取每个报告期最新的公告数据
        ORDER BY 
            WIND_CODE, 
            REPORT_PERIOD
        """
        
        # 执行查询
        df = pd.read_sql(sql, self.wind_engine)
        
        # 统一列名为大写，以匹配后续处理
        df.columns = [col.upper() for col in df.columns]
        
        # 检查必要的列是否存在
        required_columns = ['WIND_CODE', 'REPORT_PERIOD', 'S_QFA_CGRSALES']
        for col in required_columns:
            if col not in df.columns:
                raise ValueError(f"Required column '{col}' not found in query results. Actual columns: {df.columns.tolist()}")
        
        return df
    
    def process_data(self, df, end_date):
        """
        处理财务数据，获取每只股票最新一期的数据
        """
        # 将REPORT_PERIOD转换为datetime格式
        df['REPORT_PERIOD'] = pd.to_datetime(df['REPORT_PERIOD'], format='%Y%m%d')
        
        # 计算18个月前的日期
        end_date_dt = datetime.strptime(end_date, '%Y%m%d')
        start_date_dt = end_date_dt - timedelta(days=540)  # 18个月约540天
        
        # 筛选在[End_Date - 18个月, End_Date]范围内的数据
        df = df[df['REPORT_PERIOD'].between(start_date_dt, end_date_dt)]
        
        # 对每只股票取最新一期的数据
        df = df.sort_values(['WIND_CODE', 'REPORT_PERIOD'], ascending=[True, False])
        df = df.groupby('WIND_CODE').first().reset_index()
        
        return df
    
    def main(self, date):
        """
        主函数，计算因子值
        参数:
            date: 计算日期，格式为YYYYMMDD
        返回:
            包含因子值的DataFrame
        """
        # 1. 从数据库获取原始数据
        df = self.get_financial_data(date)
        
        # 2. 处理数据，获取每只股票最新一期的数据
        processed_df = self.process_data(df, date)
        
        # 3. 准备输出结果
        result = pd.DataFrame({
            'S_INFO_WINDCODE': processed_df['WIND_CODE'],
            'TRADE_DT': date,
            'OPER_REV_CAGR3': processed_df['S_QFA_CGRSALES']  # 直接使用数据库中的值
        })
        
        # 4. 处理空值
        result['OPER_REV_CAGR3'] = result['OPER_REV_CAGR3'].replace([np.inf, -np.inf], np.nan)
        
        return result

# 使用示例
if __name__ == "__main__":
    calculator = CalculateFactor()
    # 示例：计算2023年12月31日的因子值
    factor_values = calculator.main('20231231')
    print(factor_values.head())