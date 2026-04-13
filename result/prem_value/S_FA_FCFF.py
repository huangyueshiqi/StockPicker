# [Retry 3]
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

class CalculateFactor:
    def __init__(self):
        # 初始化数据库连接
        self.wind_engine = create_engine('oracle+cx_oracle://wind:wind@10.6.60.114:1521/wind')
        self.jy_engine = create_engine('oracle+cx_oracle://jylh:jylh@10.6.60.114:1521/wind')
    
    def get_sql_data(self, sql, date):
        """执行SQL查询获取数据"""
        # 将输入日期转换为YYYY-MM-DD格式
        formatted_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
        
        # 替换SQL中的参数
        sql = sql.replace('&End_Date', formatted_date)
        # 移除SQL末尾可能存在的分号
        sql = sql.rstrip(';')
        
        # 根据表名选择数据源
        if "AShareFinancialIndicator".upper() in sql.upper():
            engine = self.wind_engine
        else:
            engine = self.jy_engine
            
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn)
        return df
    
    def process_financial_data(self, df, end_date):
        """处理财务数据，获取最新一期财报数据"""
        if df.empty:
            return pd.DataFrame(columns=['WIND_CODE', 'REPORT_PERIOD', 'S_FA_FCFE'])
        
        # 确保列名大小写正确
        df.columns = [col.upper() for col in df.columns]
        
        # 检查必需的列是否存在
        required_columns = ['WIND_CODE', 'REPORT_PERIOD', 'S_FA_FCFE']
        for col in required_columns:
            if col not in df.columns:
                raise ValueError(f"缺少必需的列: {col}")
        
        # 将字符串日期转换为datetime
        end_date_dt = datetime.strptime(end_date, '%Y%m%d')
        df['REPORT_PERIOD_DT'] = pd.to_datetime(df['REPORT_PERIOD'], format='%Y%m%d')
        
        # 筛选最新一期财报数据
        result = []
        for wind_code, group in df.groupby('WIND_CODE'):
            # 对每个公司单独处理
            group = group.sort_values('REPORT_PERIOD_DT', ascending=False)
            
            # 检查最新报告类型
            latest_report = group.iloc[0]
            report_month = latest_report['REPORT_PERIOD_DT'].month
            
            # 根据报告类型确定时间窗口
            if report_month == 12:  # 年度报告
                start_date = end_date_dt - relativedelta(months=18)
            else:  # 季度报告 (3/6/9月)
                start_date = end_date_dt - relativedelta(months=6)
            
            # 筛选在时间窗口内的最新报告
            mask = (group['REPORT_PERIOD_DT'] >= start_date) & (group['REPORT_PERIOD_DT'] <= end_date_dt)
            valid_reports = group[mask]
            
            if not valid_reports.empty:
                latest_valid = valid_reports.iloc[0]
                result.append(latest_valid)
        
        if result:
            result_df = pd.DataFrame(result)
            return result_df[['WIND_CODE', 'REPORT_PERIOD', 'S_FA_FCFE']]
        else:
            return pd.DataFrame(columns=['WIND_CODE', 'REPORT_PERIOD', 'S_FA_FCFE'])
    
    def calculate_factor(self, date):
        """计算因子主函数"""
        # SQL查询语句
        sql_query = """
        SELECT 
            WIND_CODE,                -- Wind代码
            S_INFO_COMPCODE,          -- 公司ID
            ANN_DT,                   -- 公告日期
            REPORT_PERIOD,            -- 报告期(YYYYMMDD格式)
            CRNCY_CODE,               -- 货币代码
            S_FA_FCFE                 -- 股权自由现金流量(FCFE)
        FROM 
            AShareFinancialIndicator
        WHERE 
            -- 筛选季报数据(报告期月份为3月、6月、9月、12月)
            SUBSTR(REPORT_PERIOD, 5, 2) IN ('03', '06', '09', '12')
            -- 确保财报公告日期在截止日期前
            AND ANN_DT <= TO_CHAR(TO_DATE('&End_Date', 'YYYY-MM-DD'), 'YYYYMMDD')
            -- 限制报告期在截止日期前5年内
            AND TO_DATE(REPORT_PERIOD, 'YYYYMMDD') BETWEEN 
                ADD_MONTHS(TO_DATE('&End_Date', 'YYYY-MM-DD'), -60) AND 
                TO_DATE('&End_Date', 'YYYY-MM-DD')
            -- 确保FCFE字段不为空
            AND S_FA_FCFE IS NOT NULL
        ORDER BY 
            WIND_CODE, 
            TO_DATE(REPORT_PERIOD, 'YYYYMMDD') DESC
        """
        
        # 获取原始数据
        raw_data = self.get_sql_data(sql_query, date)
        
        # 处理财务数据，获取最新一期财报
        processed_data = self.process_financial_data(raw_data, date)
        
        # 准备输出结果
        if not processed_data.empty:
            # 重命名列以符合输出要求
            result = processed_data.rename(columns={
                'WIND_CODE': 'S_INFO_WINDCODE',
                'S_FA_FCFE': 'S_FA_FCFF'
            })
            result['TRADE_DT'] = date
        else:
            result = pd.DataFrame(columns=['S_INFO_WINDCODE', 'TRADE_DT', 'S_FA_FCFF'])
        
        # 确保输出列顺序正确
        result = result[['S_INFO_WINDCODE', 'TRADE_DT', 'S_FA_FCFF']]
        
        return result
    
    def main(self, date):
        """主函数"""
        # 验证日期格式
        if len(date) != 8 or not date.isdigit():
            raise ValueError("日期格式应为YYYYMMDD")
        
        try:
            datetime.strptime(date, '%Y%m%d')
        except ValueError:
            raise ValueError("无效的日期")
        
        return self.calculate_factor(date)

# 使用示例
if __name__ == "__main__":
    factor_calculator = CalculateFactor()
    # 测试计算2023年12月31日的因子值
    result = factor_calculator.main('20231231')
    print(result.head())