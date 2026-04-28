import pandas as pd
import cx_Oracle
import warnings
import re

warnings.filterwarnings('ignore')


"""
剔除被动指数基金、ETF基金和LOF基金，剔除历史总收益<50%的基金，剔除历史持股<50只的基金，存在A类和C类相同基金时，保留A类基金。
负样本采用随机采样方法构建，正负样本1：1
与特征数据合并后，剔除缺失值超过60%的特征列
"""

def get_db_connection(db_name='wind'):
    """获取数据库连接"""
    return cx_Oracle.connect(db_name, db_name, '10.6.60.114:1521/wind')


def fetch_fund_description():
    """获取基金描述信息，过滤出混合型和股票型基金"""
    connection = get_db_connection()
    sql = """
    select F_INFO_WINDCODE, F_INFO_FULLNAME, F_INFO_NAME, 
           F_INFO_FIRSTINVESTTYPE, F_INFO_SETUPDATE, 
           F_INFO_MATURITYDATE, F_INFO_FIRSTINVESTSTYLE 
    from ChinaMutualFundDescription 
    where F_INFO_FIRSTINVESTTYPE in ('混合型','股票型')
    """
    print('正在拉取基金基础信息...')
    df_desc = pd.read_sql(sql, con=connection)
    connection.close()
    return df_desc


def fetch_fund_nav():
    """获取基金复权单位净值数据"""
    connection = get_db_connection()
    sql = """
        select F_INFO_WINDCODE, ANN_DATE, F_NAV_ADJUSTED 
        from CHINAMUTUALFUNDNAV order by ANN_DATE 
    """
    print('正在拉取基金复权单位净值信息(可能耗时较长)...')
    df_nav = pd.read_sql(sql, con=connection)
    connection.close()
    return df_nav


def fetch_fund_portfolio():
    """获取基金持仓明细（建议只取中报/年报以保证全样本，或包含季报但需知晓其只含前十大重仓）"""
    connection = get_db_connection()
    # 为了演示，这里我们先拉取所有中/年报数据，如果需要季报可以去掉条件
    sql = """
    select S_INFO_WINDCODE, F_PRT_ENDDATE, S_INFO_STOCKWINDCODE, 
           ANN_DATE, REPORT_TYPE 
    from ChinaMutualFundStockPortfolio 
    where REPORT_TYPE = '中/年报'
    """
    print('正在拉取基金持仓明细(中/年报)...')
    df_portfolio = pd.read_sql(sql, con=connection)
    connection.close()
    return df_portfolio


def filter_profitable_funds(df_nav=None):
    """
    根据复权单位净值计算基金成立以来的总收益率，
    过滤出历史总收益率为正（盈利）的基金代码。
    """
    print("正在计算基金历史总收益并剔除亏损基金...")
    # 1. 确保日期格式正确并排序（必须先排序，才能正确取到期初和期末）
    df_nav['ANN_DATE'] = pd.to_datetime(df_nav['ANN_DATE'], format='%Y%m%d', errors='coerce')
    df_nav = df_nav.dropna(subset=['ANN_DATE', 'F_NAV_ADJUSTED'])
    df_nav = df_nav.sort_values(by=['F_INFO_WINDCODE', 'ANN_DATE'])
    # 2. 按基金代码分组，获取期初(first)和期末(last)的复权单位净值
    nav_summary = df_nav.groupby('F_INFO_WINDCODE').agg(
        Initial_NAV=('F_NAV_ADJUSTED', 'first'),
        Final_NAV=('F_NAV_ADJUSTED', 'last')
    )
    # 3. 计算总收益率 (期末净值 - 期初净值) / 期初净值
    nav_summary['Total_Return'] = (nav_summary['Final_NAV'] - nav_summary['Initial_NAV']) / nav_summary['Initial_NAV']
    nav_summary=nav_summary.reset_index()
    nav_summary.to_csv("fund_return.csv",index=False)
    # 4. 筛选出总收益率 > 0 的基金
    nav_summary=pd.read_csv("fund_return.csv")
    profitable_funds = nav_summary[nav_summary['Total_Return'] > 0.5]['F_INFO_WINDCODE'].tolist()
    print(f"总计 {len(nav_summary)} 只基金中，筛选出 {len(profitable_funds)} 只历史总收益为正的基金。")
    return profitable_funds


def clean_fund_classes(df_desc):
    """
    清洗基金基础信息：
    1. 剔除 LOF、ETF、联接基金
    2. 合并多份额基金（A类/C类等），仅保留主份额（优先保留 A 类）
    """
    print("\n开始执行高级筛选：剔除LOF、多份额去重...")
    initial_count = len(df_desc)

    # 1. 剔除包含特定关键字的基金 (LOF, ETF, 联接)
    # 不区分大小写
    exclude_keywords = r'(LOF|ETF|联接)'
    df_desc = df_desc[~df_desc['F_INFO_NAME'].str.contains(exclude_keywords, case=False, na=False)]
    print(f"剔除 LOF/ETF 等关键字后，剩余基金: {len(df_desc)}")

    # 2. 提取基金主名称（去掉末尾的 A/B/C/E 等份额后缀）
    # 例如："易方达消费行业A" -> "易方达消费行业", "广发双擎升级C" -> "广发双擎升级"
    def extract_base_name(name):
        if pd.isna(name):
            return name
        # 匹配以大写字母 A-Z 结尾的名字，并把字母去掉作为主名称
        match = re.match(r'^(.*?)[A-Z]$', str(name))
        if match:
            return match.group(1).strip()
        return str(name).strip()

    df_desc['Base_Name'] = df_desc['F_INFO_NAME'].apply(extract_base_name)

    # 3. 制定保留优先级：A类优先级最高，其次是无后缀的，C/E/其他后缀优先级最低
    # 给每一行打分：名字以 'A' 结尾得分 1，不带单字母后缀的得分 2，其他的得分 3
    def get_class_priority(name):
        name = str(name)
        if name.endswith('A'):
            return 1
        elif not re.search(r'[A-Z]$', name):
            return 2  # 主份额没带字母
        else:
            return 3  # B, C, E 等等

    df_desc['Priority'] = df_desc['F_INFO_NAME'].apply(get_class_priority)

    # 4. 按基础名称分组，按优先级排序，并保留第一条（即最优份额）
    df_desc = df_desc.sort_values(by=['Base_Name', 'Priority'])
    df_desc_unique = df_desc.drop_duplicates(subset=['Base_Name'], keep='first').copy()

    # 删掉辅助列
    df_desc_unique = df_desc_unique.drop(columns=['Base_Name', 'Priority'])

    print(f"合并A/C多份额并优先保留A类后，最终入库的独立基金数: {len(df_desc_unique)} (从初始 {initial_count} 只中提取)")
    return df_desc_unique

def process_and_merge_data(df_portfolio, df_desc,profitable_funds_list):
    """清洗、合并并过滤数据"""

    print("原始持仓数据形状:", df_portfolio.shape)
    print("原始基金描述形状:", df_desc.shape)

    # 1. 剔除被动指数型基金（它们没有主动选股能力，不适合做 Teacher）
    df_desc_active = df_desc[df_desc['F_INFO_FIRSTINVESTSTYLE'] != '被动指数型']
    df_desc_active=clean_fund_classes(df_desc_active)
    # 1.1 如果传入了盈利基金名单，则进一步过滤掉历史不赚钱的基金
    if profitable_funds_list is not None:
        df_desc_active = df_desc_active[df_desc_active['F_INFO_WINDCODE'].isin(profitable_funds_list)]
        print(f"基于历史盈利条件进一步剔除亏损基金后，剩余主动基金数量: {df_desc_active.shape[0]}")
    else:
        print(f"剔除被动指数型后，剩余基金数量: {df_desc_active.shape[0]}")

    # 2. 将持仓表与基金基础信息表合并
    # 注意：持仓表用的是 S_INFO_WINDCODE，描述表用的是 F_INFO_WINDCODE
    df_merged = pd.merge(
        df_portfolio,
        df_desc_active,
        left_on='S_INFO_WINDCODE',
        right_on='F_INFO_WINDCODE',
        how='inner'
    )
    print("合并后的数据形状:", df_merged.shape)

    # 3. 过滤掉在整个生命周期内累计持股数量（去重后）<= 50 的基金
    print("正在过滤整个生命周期内累计持股数 <= 50 的基金(可能较耗时)...")

    # 按基金代码分组，计算其历史上买过的所有去重股票数量
    holdings_count = df_merged.groupby('S_INFO_WINDCODE')['S_INFO_STOCKWINDCODE'].nunique().reset_index(name='lifetime_stock_count')

    # 筛选出累计持股 > 50 的基金代码
    valid_funds = holdings_count[holdings_count['lifetime_stock_count'] > 50]['S_INFO_WINDCODE']

    # 将符合条件的基金保留下来
    df_filtered = df_merged[df_merged['S_INFO_WINDCODE'].isin(valid_funds)]

    print(f"过滤生命周期累计持股数>50后，剩余基金数量: {valid_funds.shape[0]}")
    print("过滤后剩余持仓数据形状:", df_filtered.shape)

    # 4. 时间字段处理与对齐（防范未来函数的核心！）
    # 转换日期格式
    df_filtered['ANN_DATE'] = pd.to_datetime(df_filtered['ANN_DATE'], format='%Y%m%d', errors='coerce')
    df_filtered['F_PRT_ENDDATE'] = pd.to_datetime(df_filtered['F_PRT_ENDDATE'], format='%Y%m%d', errors='coerce')

    # 剔除公告日为空的异常数据
    df_filtered = df_filtered.dropna(subset=['ANN_DATE'])

    # 新增特征生效日(EFFECTIVE_DATE)。
    # 策略在回测时，只能在公告日(或公告日下一交易日)之后使用该期持仓数据
    df_filtered['EFFECTIVE_DATE'] = df_filtered['ANN_DATE']

    # 按生效时间和基金代码排序
    df_final = df_filtered.sort_values(by=['EFFECTIVE_DATE', 'S_INFO_WINDCODE']).reset_index(drop=True)

    return df_final


if __name__ == "__main__":

    # 如果要直接从数据库拉取（注意内存消耗可能较大）
    df_desc = fetch_fund_description()
    df_portfolio = fetch_fund_portfolio()
    df_nav=fetch_fund_nav()
    profitable_funds_list=filter_profitable_funds(df_nav)
    df_final = process_and_merge_data(df_portfolio, df_desc,profitable_funds_list)
    #
    df_final.to_csv('processed_fund_holdings.csv', encoding="utf-8-sig",index=False)
    # print("数据处理完成，已保存至 data/processed_fund_holdings.csv")