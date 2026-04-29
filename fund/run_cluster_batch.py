from __future__ import annotations

import argparse
import json
import os
import traceback
from typing import Dict, List, Optional


def parse_clusters_arg(v: str) -> Optional[List[int]]:
    s = v.strip()
    if s.lower() == "all":
        return None
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1].strip()
    return [int(x.strip()) for x in s.split(",") if x.strip() != ""]


def parse_args():
    p = argparse.ArgumentParser(description="批量生成各 cluster 的 df_value 与 SHAP 特征选择文件")
    p.add_argument("--cluster-map", default="cluster_result0427.csv")
    p.add_argument("--holdings", default="processed_fund_holdings.csv")
    p.add_argument("--outdir", default="fund/batch_outputs")
    p.add_argument("--clusters", default="all", help="all 或逗号分隔的 cluster_id 列表，如 0,1,2")
    p.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--neg-ratio", type=float, default=1.0)
    p.add_argument("--nan-threshold", type=float, default=0.6)
    p.add_argument("--train-full", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--shap-coverage", type=float, default=0.8)
    p.add_argument("--docs-dir", default="documents")
    p.add_argument("--qlib-price-path", default="/home/quant/zc/finance_deal/qlib_data/price_data0821")
    p.add_argument("--qlib-fin-path", default="/home/quant/zc/finance_deal/qlib_data/pit_data")
    return p.parse_args()


def load_cluster_map(path: str) -> Dict[int, List[str]]:
    import pandas as pd

    df = pd.read_csv(path)
    required = {"fund_code", "cluster_id"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"cluster map 缺少列: {sorted(missing)}")
    df["cluster_id"] = df["cluster_id"].astype(int)
    mapping: Dict[int, List[str]] = {}
    for cluster_id, g in df.groupby("cluster_id", sort=True):
        mapping[int(cluster_id)] = g["fund_code"].dropna().astype(str).unique().tolist()
    return mapping


def load_holdings(path: str) -> pd.DataFrame:
    import pandas as pd

    df = pd.read_csv(path)
    required = {"S_INFO_WINDCODE", "S_INFO_STOCKWINDCODE", "F_PRT_ENDDATE", "ANN_DATE"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"holdings 缺少列: {sorted(missing)}")
    return df


def run_one_cluster(cluster_id: int, fund_codes: List[str], holdings: pd.DataFrame, args) -> Dict:
    import pandas as pd

    from fund.qlib_reader import QlibReaderParams, build_factor_data, build_df_for_xgb
    from fund.xgb_shap import train_and_explain

    out_dir = os.path.join(args.outdir, f"cluster_{cluster_id}")
    os.makedirs(out_dir, exist_ok=True)
    df_path = os.path.join(out_dir, "df_value.csv")
    selected_path = os.path.join(out_dir, "selected_features_80pct.csv")
    meta_path = os.path.join(out_dir, "run_meta.json")

    if args.resume and os.path.exists(df_path) and os.path.exists(selected_path):
        return {"cluster_id": cluster_id, "skipped": True, "out_dir": out_dir}

    sub = holdings[holdings["S_INFO_WINDCODE"].isin(fund_codes)].copy()
    if sub.empty:
        return {"cluster_id": cluster_id, "skipped": True, "reason": "no holdings", "out_dir": out_dir}

    params = QlibReaderParams(
        docs_dir=args.docs_dir,
        price_data_path=args.qlib_price_path,
        fin_data_path=args.qlib_fin_path,
    )

    factor_data = build_factor_data(sub, params=params)
    if factor_data is None or factor_data.empty:
        return {"cluster_id": cluster_id, "skipped": True, "reason": "empty factor_data", "out_dir": out_dir}

    df_value, feature_cols = build_df_for_xgb(
        sub,
        factor_data,
        neg_ratio=args.neg_ratio,
        nan_threshold=args.nan_threshold,
    )
    df_value.to_csv(df_path, index=False)

    train_and_explain(
        df_value,
        feature_cols,
        target_col="label",
        train_full=args.train_full,
        shap_coverage=args.shap_coverage,
        output_dir=out_dir,
    )

    dt = pd.to_datetime(sub["F_PRT_ENDDATE"], errors="coerce")
    start_date = dt.min()
    end_date = dt.max()

    meta = {
        "cluster_id": int(cluster_id),
        "fund_count": int(len(fund_codes)),
        "holdings_rows": int(sub.shape[0]),
        "df_rows": int(df_value.shape[0]),
        "feature_cols": int(len(feature_cols)),
        "start_date": start_date.strftime("%Y-%m-%d") if pd.notna(start_date) else None,
        "end_date": end_date.strftime("%Y-%m-%d") if pd.notna(end_date) else None,
        "neg_ratio": float(args.neg_ratio),
        "nan_threshold": float(args.nan_threshold),
        "train_full": bool(args.train_full),
        "shap_coverage": float(args.shap_coverage),
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return {"cluster_id": cluster_id, "skipped": False, "out_dir": out_dir}


def main():
    args = parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    failures_path = os.path.join(args.outdir, "failures.jsonl")

    cluster_map = load_cluster_map(args.cluster_map)
    holdings = load_holdings(args.holdings)
    targets = parse_clusters_arg(args.clusters)

    cluster_ids = sorted(cluster_map.keys())
    if targets is not None:
        target_set = set(targets)
        cluster_ids = [cid for cid in cluster_ids if cid in target_set]

    results = []
    for cluster_id in cluster_ids:
        try:
            res = run_one_cluster(cluster_id, cluster_map[cluster_id], holdings, args)
            results.append(res)
            print(res)
        except Exception as e:
            failure = {
                "cluster_id": int(cluster_id),
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
            with open(failures_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(failure, ensure_ascii=False) + "\n")
            print(failure)

    summary_path = os.path.join(args.outdir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
