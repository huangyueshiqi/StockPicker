import os
import csv
import pandas as pd
import numpy as np
import qlib
from qlib.data import D

import re
import jieba
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from scipy.sparse import hstack, csr_matrix
from sklearn.preprocessing import normalize
from dataclasses import dataclass
from typing import Tuple, Optional

# 定义支持的表名
fin_tables = [
    "ASHARECASHFLOW", "ASHARECASHFLOWHIS", "ASHAREBALANCESHEET",
    "ASHAREBALANCESHEETHIS", "ASHAREINCOME", "ASHAREINCOMEHIS",
    "ASHARETTMHIS", "ASHARECONSENSUSINDEXHIS", "ASHAREPROFITEXPRESSHIS",
    "ASHAREFINANCIALINDICATOR"
]
price_tables = [
    "ASHAREEODPRICES", "AShareAuction", "AShareEODDerivativeIndicator",
    "AShareEODPricesMKT", "AShareEVIndicator", "AShareEnergyindex",
    "AShareEnergyindexADJ", "AShareL2Indicators", "AShareMoneyFlow",
    "AShareTechIndicators", "AShareValuationIndicator", "AShareYield",
    "AShareswingReversetrend", "AShareswingReversetrendADJ",
    "Ashareintensitytrend", "AshareintensitytrendADJ",
    "AsharesFndfactor_ConFcst", "DailyValuationFactor",
    "PITFinancialFactor", "RevenueTechnicalFactor"
]

# 将表名转小写
fin_tables_lower = {name.lower() for name in fin_tables}
price_tables_lower = {name.lower() for name in price_tables}

# 数据路径配置
price_data_path = "/home/quant/zc/finance_deal/qlib_data/price_data0821"
fin_data_path = "/home/quant/zc/finance_deal/qlib_data/pit_data"

@dataclass
class QlibReaderParams:
    docs_dir: str = "documents"
    price_data_path: str = price_data_path
    fin_data_path: str = fin_data_path
    field_csv_files: Tuple[str, str] = ("财务字段中英文对照表.csv", "量价字段中英文对照表.csv")


def clean_fund_name(name):
    name = str(name)
    name = re.sub(r'[A-Z]+$', '', name)
    name = re.sub(r'(ETF|LOF|FOF|混合|灵活配置|配置|股票|债券|增强|指数|发起式|证券|投资|基金|回报|精选|优选)', '',
                  name)
    return name


def tokenize_text(text):
    return " ".join(jieba.lcut(text))


def cluster_funds(fund_holding):
    """
    根据基金名称进行 NLP 清洗和 K-Means 聚类，并将结果保存在本地
    """
    print("正在进行基金名称 NLP 聚类 (K-Means)...")
    # 提取需要聚类的基金基础信息
    df_fund = fund_holding[['S_INFO_WINDCODE', 'F_INFO_FULLNAME', 'F_INFO_NAME', 'F_INFO_FIRSTINVESTTYPE',
                            'F_INFO_FIRSTINVESTSTYLE']].copy()
    df_fund = df_fund.drop_duplicates()

    # 1. 文本清洗与分词
    df_fund['CLEAN_NAME'] = df_fund['F_INFO_NAME'].apply(clean_fund_name)
    df_fund['TOKEN_NAME'] = df_fund['CLEAN_NAME'].apply(tokenize_text)

    # 2. 提取文本特征：使用词级别的 TF-IDF
    vectorizer = TfidfVectorizer(max_df=0.9, min_df=2, max_features=300)
    text_sparse = vectorizer.fit_transform(df_fund['TOKEN_NAME'])

    # 3. 提取类别特征：One-Hot 编码
    cat_features = pd.get_dummies(df_fund[['F_INFO_FIRSTINVESTSTYLE']])
    cat_sparse = csr_matrix(cat_features.values)

    # 4. 特征合并与归一化
    X_combined = hstack([cat_sparse * 1, text_sparse])
    X_normalized = normalize(X_combined)

    # 5. 重新执行 K-Means 聚类
    kmeans = KMeans(n_clusters=40, random_state=42, n_init='auto')
    df_fund['Cluster_Opt'] = kmeans.fit_predict(X_normalized)

    print("【聚类完成】各个类别的基金数量分布前 5：\n", df_fund['Cluster_Opt'].value_counts().head(5))

    os.makedirs('fund', exist_ok=True)
    df_fund.to_csv("fund/fund_cluster.csv", encoding='utf-8-sig', index=False)
    return df_fund


def drop_high_nan_columns(df, threshold=0.6, exclude_cols=None):
    if exclude_cols is None:
        exclude_cols = []
    cols = [c for c in df.columns if c not in set(exclude_cols)]
    nan_ratio = df[cols].isna().mean()
    drop_cols = nan_ratio[nan_ratio > threshold].index.tolist()
    if drop_cols:
        df = df.drop(columns=drop_cols)
    return df, drop_cols

def read_csv_fields(file_paths):
    """
    读取 CSV 字段文件，生成候选字段集合
    """
    all_fields = []
    for file_path in file_paths:
        if not os.path.exists(file_path):
            print(f"警告: 文件 {file_path} 不存在，跳过")
            continue
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    desc = row.get('中文名') or row.get('注释') or ''
                    field_info = {
                        'table_name': row.get('table_name', ''),
                        'field_name': row.get('field_name', ''),
                        'description': desc
                    }
                    all_fields.append(field_info)
        except Exception as e:
            print(f"读取文件 {file_path} 时出错: {e}")
            continue
    return all_fields


def build_qlib_fields(all_fields):
    """
    根据CSV字段构建QLib可用的字段列表
    """
    fin_fields = set()
    price_fields = set()

    for field_info in all_fields:
        table_name = field_info['table_name']
        mapped_field = field_info['field_name']

        if not table_name or not mapped_field:
            continue

        # 转换为小写进行匹配
        table_name_lower = table_name.lower()

        if table_name_lower in fin_tables_lower:
            # 财务字段通常有cor和adj两种形式
            mapped_field1 = f'$cor_{mapped_field}_{table_name}'
            mapped_field2 = f'$adj_{mapped_field}_{table_name}'
            fin_fields.add(mapped_field1)
            fin_fields.add(mapped_field2)
        elif table_name_lower in price_tables_lower:
            # 量价字段处理
            if mapped_field in ['close']:
                # 特殊处理close字段
                mapped_field1 = f'${mapped_field}'
            else:
                mapped_field1 = f'${mapped_field}_{table_name}'
            price_fields.add(mapped_field1)

    return list(fin_fields), list(price_fields)


def read_qlibdata(instruments: list, fields: list, data_type: str, start_time: str,
                  end_time: str, price_uri: Optional[str] = None, fin_uri: Optional[str] = None) -> pd.DataFrame:
    """
    从QLib读取数据
    """
    if data_type == 'price':
        qlib.init(provider_uri=price_uri or price_data_path, skip_if_exists=True)
        # 在指定时间范围内获取数据
        data = D.features(
            instruments=instruments,
            fields=fields,
            start_time=start_time,
            end_time=end_time,
            freq='day',
        )
        data = data.reset_index()
    elif data_type == 'fin':
        qlib.init(provider_uri=fin_uri or fin_data_path, skip_if_exists=True)
        data = D.features(
            instruments=instruments,
            fields=fields,
            start_time=start_time,
            end_time=end_time,
            freq='day',
        )
        data = data.reset_index()

    if data is None or data.empty:
        return data

    # 清洗列名
    original_columns = data.columns
    cleaned_columns = original_columns.str.replace(r'^P\(\$\$', '', regex=True) \
        .str.replace(r'_q\)', '', regex=True) \
        .str.replace(r'\$', '', regex=True)
    data = data.set_axis(cleaned_columns, axis=1)
    return data


def get_all_csv_data(instruments: list, start_time: str, end_time: str, params: Optional[QlibReaderParams] = None):
    """
    主函数：读取所有CSV字段并获取对应的QLib数据
    """
    if params is None:
        params = QlibReaderParams()
    docs_dir = params.docs_dir
    csv_files = [os.path.join(docs_dir, f) for f in params.field_csv_files]

    # 1. 读取CSV字段定义
    print("正在读取CSV字段文件...")
    all_fields = read_csv_fields(csv_files)

    if not all_fields:
        print("未找到有效的字段定义")
        return None, None

    print(f"成功读取 {len(all_fields)} 个字段定义")

    # 2. 构建QLib字段列表
    print("正在构建QLib字段列表...")
    fin_fields, price_fields = build_qlib_fields(all_fields)

    print(f"财务字段数量: {len(fin_fields)}")
    print(f"量价字段数量: {len(price_fields)}")

    # 3. 获取数据
    fin_data = None
    price_data = None

    if fin_fields:
        print("正在获取财务数据...")
        try:
            fin_data = read_qlibdata(instruments, fin_fields, 'fin', start_time, end_time, price_uri=params.price_data_path, fin_uri=params.fin_data_path)
            print(f"财务数据形状: {fin_data.shape if fin_data is not None else 'None'}")
        except Exception as e:
            print(f"获取财务数据失败: {e}")

    if price_fields:
        print("正在获取量价数据...")
        try:
            price_data = read_qlibdata(instruments, price_fields, 'price', start_time, end_time, price_uri=params.price_data_path, fin_uri=params.fin_data_path)
            print(f"量价数据形状: {price_data.shape if price_data is not None else 'None'}")
        except Exception as e:
            print(f"获取量价数据失败: {e}")

    return fin_data, price_data


def build_df_for_xgb(fund_holding4, factor_data, neg_ratio=1, random_state=42, nan_threshold: float = 0.6):
    rng = np.random.default_rng(random_state)


    pos = fund_holding4[['S_INFO_WINDCODE', 'S_INFO_STOCKWINDCODE', 'F_PRT_ENDDATE']].drop_duplicates().copy()
    pos = pos.rename(columns={
        'S_INFO_WINDCODE': 'fund',
        'S_INFO_STOCKWINDCODE': 'stock',
        'F_PRT_ENDDATE': 'date',
    })
    pos['label'] = 1

    universe = pd.Index(pd.Series(factor_data['instrument'].unique()).dropna().unique())
    neg_rows = []
    for (fund, date), g in pos.groupby(['fund', 'date'], sort=False):
        held = pd.Index(g['stock'].unique())
        candidates = universe.difference(held)
        if candidates.empty:
            continue
        n = int(min(len(candidates), max(1, len(held) * neg_ratio)))
        sampled = rng.choice(candidates.to_numpy(), size=n, replace=False)
        neg_rows.append(pd.DataFrame({'fund': fund, 'stock': sampled, 'date': date, 'label': 0}))

    neg = pd.concat(neg_rows, ignore_index=True) if neg_rows else pd.DataFrame(columns=['fund', 'stock', 'date', 'label'])
    base = pd.concat([pos, neg], ignore_index=True)

    base = base.rename(columns={'stock': 'instrument', 'date': 'datetime'})
    base['datetime'] = pd.to_datetime(base['datetime'])
    base = base.sort_values(by='datetime').reset_index(drop=True)

    factor_data = factor_data.copy()
    factor_data['datetime'] = pd.to_datetime(factor_data['datetime'])
    factor_data = factor_data.sort_values(by='datetime').reset_index(drop=True)

    df = pd.merge_asof(
        left=base,
        right=factor_data,
        on='datetime',
        by='instrument',
        direction='backward'
    )

    exclude_cols = ['fund', 'instrument', 'datetime', 'label']
    df, _ = drop_high_nan_columns(df, threshold=nan_threshold, exclude_cols=exclude_cols)

    feature_cols = [c for c in df.columns if c not in set(exclude_cols)]
    return df, feature_cols

def build_factor_data(fund_holding4: pd.DataFrame, params: Optional[QlibReaderParams] = None) -> pd.DataFrame:
    if params is None:
        params = QlibReaderParams()
    start_date = fund_holding4['F_PRT_ENDDATE'].min()
    end_date = fund_holding4['F_PRT_ENDDATE'].max()
    instruments = fund_holding4['S_INFO_STOCKWINDCODE'].dropna().unique().tolist()
    target_dates = pd.to_datetime(pd.Series(fund_holding4['F_PRT_ENDDATE'].dropna().unique()))
    financial_data, price_data = get_all_csv_data(instruments, start_date, end_date, params=params)
    if financial_data is None or price_data is None:
        return pd.DataFrame()
    financial_data['datetime'] = pd.to_datetime(financial_data['datetime'])
    price_data['datetime'] = pd.to_datetime(price_data['datetime'])
    price_data = price_data[price_data['datetime'].isin(target_dates)]
    fin_data = financial_data.sort_values(by='datetime').reset_index(drop=True)
    price_data = price_data.sort_values(by='datetime').reset_index(drop=True)
    factor_data = pd.merge_asof(
        left=price_data,
        right=fin_data,
        on='datetime',
        by='instrument',
        direction='backward'
    )
    factor_data = factor_data.sort_values(by='datetime').reset_index(drop=True)
    return factor_data



# 使用示例

def create_feature_matrix_x():
    # 配置参数
    print("1. 读取并过滤基金持仓数据...")
    # fund_cluster = pd.read_csv("fund_cluster.csv")
    fund_cluster = pd.read_csv("cluster_result0427.csv")
    fund_holding = pd.read_csv("processed_fund_holdings.csv")

    # fund_cluster3 = fund_cluster[fund_cluster['Cluster_Opt'] == 34]
    fund_cluster3 = fund_cluster[fund_cluster['cluster_id'] == 0]
    fund_cluster3=fund_cluster3.iloc[[1]]
    print(fund_cluster3)
    # fund_holding3 = fund_holding[fund_holding['S_INFO_WINDCODE'].isin(list(fund_cluster3['S_INFO_WINDCODE']))]
    fund_holding3 = fund_holding[fund_holding['S_INFO_WINDCODE'].isin(list(fund_cluster3['fund_code']))]
    fund_holding4 = fund_holding3[fund_holding3['ANN_DATE'] >= '2015-01-01']

    start_date = fund_holding4['F_PRT_ENDDATE'].min()
    end_date = fund_holding4['F_PRT_ENDDATE'].max()
    instruments = fund_holding4['S_INFO_STOCKWINDCODE'].unique()
    target_dates=fund_holding4['F_PRT_ENDDATE'].dropna().unique()
    target_dates=pd.to_datetime(pd.Series(target_dates))
    print(f"   提取了 {len(fund_holding4)} 条持仓记录，涉及 {len(instruments)} 只股票，报告期: {start_date} 至 {end_date}")


    # 获取所有数据
    financial_data, price_data = get_all_csv_data(instruments, start_date , end_date)

    financial_data['datetime'] = pd.to_datetime(financial_data['datetime'])
    price_data['datetime'] = pd.to_datetime(price_data['datetime'])
    price_data=price_data[price_data['datetime'].isin(target_dates)]

    fin_data = financial_data.sort_values(by='datetime').reset_index(drop=True)
    price_data = price_data.sort_values(by='datetime').reset_index(drop=True)


    # 2. 合并高低频数据
    factor_data = pd.merge_asof(
        left=price_data,
        right=fin_data,
        on='datetime',
        by='instrument',
        direction='backward'
    )

    # 合并后的形状应为 (484, 2192+667+2) = (484, 2861)
    print("合并后的数据形状:", factor_data.shape)

    # 因为 factor_data 之前合并后可能乱序了，再次确保它是按时间排序的
    factor_data = factor_data.sort_values(by='datetime').reset_index(drop=True)


    return fund_holding4,factor_data






if __name__ == "__main__":
    # fund_holding=pd.read_csv("processed_fund_holdings.csv")
    # fund_cluster=cluster_funds(fund_holding)
    fund_holding4, factor_data = create_feature_matrix_x()
    df, feature_cols = build_df_for_xgb(fund_holding4, factor_data, neg_ratio=1)
    df.to_csv("df_value.csv", index=False)
    print(f"\n5. 生成用于训练的 df 完成，形状: {df.shape}，特征列数: {len(feature_cols)}")
    print(df['datetime'].unique())
