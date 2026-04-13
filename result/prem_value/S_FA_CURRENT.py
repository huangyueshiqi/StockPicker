# [Retry 2]
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime
from dateutil.relativedelta import relativedelta

class CalculateFactor:
    def __init__(self):
        # 初始化数据库连接
        self.engine_wind = create_engine('oracle+cx_oracle://wind:wind@10.6.60.114:1521/wind')
        # 当前因子数据来源表以'A'开头，使用wind数据库
    
    def get_sql_data(self, end_date):
        """从数据库获取原始数据"""
        # 准备SQL查询
        sql = """
        SELECT 
            WIND_CODE,
            S_INFO_COMPCODE,
            REPORT_PERIOD,
            ANN_DT,
            S_FA_CURRENT
        FROM (
            SELECT 
                WIND_CODE,
                S_INFO_COMPCODE,
                REPORT_PERIOD,
                ANN_DT,
                S_FA_CURRENT,
                ROW_NUMBER() OVER (PARTITION BY WIND_CODE, REPORT_PERIOD ORDER BY ANN_DT DESC) AS rn
            FROM 
                AShareFinancialIndicator
            WHERE 
                SUBSTR(REPORT_PERIOD, 5, 2) IN ('03', '06', '09', '12')
                AND ANN_DT <= TO_CHAR(TO_DATE(:end_date, 'YYYY-MM-DD'), 'YYYYMMDD')
                AND REPORT_PERIOD BETWEEN TO_CHAR(ADD_MONTHS(TO_DATE(:end_date, 'YYYY-MM-DD'), -60), 'YYYYMMDD')
                                     AND TO_CHAR(TO_DATE(:end_date, 'YYYY-MM-DD'), 'YYYYMMDD')
        ) tmp_LatestQuarterReport
        WHERE 
            rn = 1
        ORDER BY 
            WIND_CODE, 
            REPORT_PERIOD
        """
        
        # 转换日期格式用于SQL绑定变量
        end_date_str = datetime.strptime(end_date, '%Y%m%d').strftime('%Y-%m-%d')
        
        # 执行查询并返回DataFrame
        df = pd.read_sql(sql, self.engine_wind, params={'end_date': end_date_str})
        
        # 确保列名统一为大写
        df.columns = [col.upper() for col in df.columns]
        return df
    
    def process_data(self, df, end_date):
        """处理数据，获取每只股票在截止日期前的最新财报数据"""
        if df.empty:
            return pd.DataFrame(columns=['S_INFO_WINDCODE', 'TRADE_DT', 'S_FA_CURRENT'])
        
        # 确保关键列存在（处理可能的列名大小写问题）
        required_columns = ['WIND_CODE', 'REPORT_PERIOD', 'S_FA_CURRENT']
        for col in required_columns:
            if col not in df.columns:
                raise KeyError(f"DataFrame中找不到{col}列")
        
        # 转换日期为datetime格式便于计算
        df['REPORT_PERIOD_DT'] = pd.to_datetime(df['REPORT_PERIOD'], format='%Y%m%d')
        end_date_dt = datetime.strptime(end_date, '%Y%m%d')
        
        # 根据报告期类型确定时间范围
        def get_latest_report(group):
            # 筛选在合理时间范围内的报告
            recent_reports = group[
                ((group['REPORT_PERIOD_DT'].dt.month == 12) & 
                 (group['REPORT_PERIOD_DT'] >= (end_date_dt - relativedelta(months=18)))) |
                ((group['REPORT_PERIOD_DT'].dt.month.isin([3, 6, 9])) & 
                 (group['REPORT_PERIOD_DT'] >= (end_date_dt - relativedelta(months=6))))
            ]
            
            if not recent_reports.empty:
                # 返回最新的报告
                return recent_reports.nlargest(1, 'REPORT_PERIOD_DT')
            return pd.DataFrame()  # 如果没有合适报告，返回空DataFrame
        
        # 按股票分组处理
        processed_df = df.groupby('WIND_CODE', group_keys=False).apply(get_latest_report)
        
        if processed_df.empty:
            return pd.DataFrame(columns=['S_INFO_WINDCODE', 'TRADE_DT', 'S_FA_CURRENT'])
        
        # 准备输出格式
        result = processed_df[['WIND_CODE', 'S_FA_CURRENT']].copy()
        result['TRADE_DT'] = end_date
        result.rename(columns={'WIND_CODE': 'S_INFO_WINDCODE'}, inplace=True)
        
        return result[['S_INFO_WINDCODE', 'TRADE_DT', 'S_FA_CURRENT']]
    
    def main(self, date):
        """主函数，计算指定日期的因子值"""
        # 1. 从数据库获取数据
        raw_data = self.get_sql_data(date)
        
        # 2. 处理数据，获取各股票最新财报
        factor_data = self.process_data(raw_data, date)
        
        # 3. 因子值即为S_FA_CURRENT，无需额外计算
        
        # 4. 返回结果DataFrame
        return factor_data


# 使用示例
if __name__ == "__main__":
    calculator = CalculateFactor()
    # 计算2023年12月31日的因子值
    factor_values = calculator.main("20231231")
    print(factor_values.head())