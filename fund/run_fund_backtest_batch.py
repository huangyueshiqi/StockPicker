from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
import shutil
from typing import Any, Dict, List, Optional


def parse_clusters(v: str) -> Optional[List[int]]:
    s = v.strip()
    if s.lower() == "all":
        return None
    if s.startswith("["):
        return [int(x) for x in json.loads(s)]
    return [int(x.strip()) for x in s.split(",") if x.strip() != ""]


def parse_args():
    p = argparse.ArgumentParser(description="按 cluster 范围逐基金提规则并跑 qlib_premium_value_strategy 回测")
    p.add_argument("--clusters", default="all", help="all / 0 / 0,1,2 / [0,1,2]")
    p.add_argument("--batch-outdir", default="fund/batch_outputs")
    p.add_argument("--outdir", default="fund/batch_backtests")
    p.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--project-root", default="/home/quant/zc/backtrader/QuantBacktester_57")
    p.add_argument("--python", default=sys.executable)
    return p.parse_args()


def list_clusters(batch_outdir: str) -> List[int]:
    if not os.path.exists(batch_outdir):
        return []
    out = []
    for name in os.listdir(batch_outdir):
        if not name.startswith("cluster_"):
            continue
        try:
            out.append(int(name.split("_", 1)[1]))
        except Exception:
            continue
    return sorted(set(out))


def load_cluster_inputs(batch_outdir: str, cluster_id: int) -> Dict[str, str]:
    cluster_dir = os.path.join(batch_outdir, f"cluster_{cluster_id}")
    df_path = os.path.join(cluster_dir, "df_value.csv")
    feat_path = os.path.join(cluster_dir, "selected_features_80pct.csv")
    return {"cluster_dir": cluster_dir, "df_path": df_path, "feat_path": feat_path}


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def copy_if_exists(src: str, dst: str) -> bool:
    if not src or not os.path.exists(src):
        return False
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    shutil.copyfile(src, dst)
    return True

def build_qlib_strategy_command(
    python: str,
    script: str,
    fund_rule_file: str,
    trade_file: str,
    cache_id: str,
    project_root: str,
) -> List[str]:
    cmd = [
        python,
        script,
        "--fund_rule_file",
        fund_rule_file,
        "--trade_file",
        trade_file,
        "--cache_id",
        cache_id,
        "--project_root",
        project_root,
        "--interactive",
        "--skip_backtest",
    ]
    return cmd


def run_one_fund(
    cluster_id: int,
    fund_code: str,
    df_fund,
    feat_path: str,
    args,
    failures_path: str,
) -> Dict[str, Any]:
    fund_dir = os.path.join(args.outdir, f"cluster_{cluster_id}", f"fund_{fund_code}")
    ensure_dir(fund_dir)

    df_value_path = os.path.join(fund_dir, "df_value.csv")
    rule_path = os.path.join(fund_dir, "rule.txt")
    trade_path = os.path.join(fund_dir, "trade.csv")
    meta_path = os.path.join(fund_dir, "run_meta.json")

    if args.resume and os.path.exists(trade_path):
        return {"cluster_id": cluster_id, "fund_code": fund_code, "skipped": True, "fund_dir": fund_dir}

    df_fund.to_csv(df_value_path, index=False)

    from fund.extract_rules import extract_rules_from_top_features

    rules = extract_rules_from_top_features(
        df_fund,
        top_features_file=feat_path,
        target_col="label",
        max_depth=5,
        desc_df_path=os.path.join("documents", "财务量价字段表.csv"),
        plot_path=os.path.join(fund_dir, "decision_tree_rules.png"),
    )
    rule = rules[0] if rules else ""
    with open(rule_path, "w", encoding="utf-8") as f:
        f.write(rule)

    cache_id = f"cluster{cluster_id}_{fund_code}_{time.strftime('%Y%m%d_%H%M%S')}"
    try:
        cmd = build_qlib_strategy_command(
            python=args.python,
            script="/workspace/qlib_premium_value_strategy.py",
            fund_rule_file=rule_path,
            trade_file=trade_path,
            cache_id=cache_id,
            project_root=args.project_root,
        )
        strategy_log = os.path.join(fund_dir, "strategy.log")
        with open(strategy_log, "w", encoding="utf-8") as f:
            p = subprocess.run(cmd, stdout=f, stderr=f)
        returncode = int(p.returncode)
        error = None
        tb = None
    except Exception as e:
        returncode = 1
        error = str(e)
        tb = traceback.format_exc()

    cache_config_path = os.path.join("config", "llm_cache", cache_id, "generated_strategy.json")
    cache_mapping_path = os.path.join("config", "llm_cache", cache_id, "mapping_result.json")
    copy_if_exists(cache_config_path, os.path.join(fund_dir, "generated_strategy.json"))
    copy_if_exists(cache_mapping_path, os.path.join(fund_dir, "mapping_result.json"))
    meta = {
        "cluster_id": int(cluster_id),
        "fund_code": str(fund_code),
        "cache_id": cache_id,
        "cmd": None,
        "cmd": None,
        "returncode": returncode,
        "error": error,
        "traceback": tb,
        "df_rows": int(getattr(df_fund, "shape", [0])[0]),
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    if returncode != 0:
        failure = {"cluster_id": int(cluster_id), "fund_code": str(fund_code), "returncode": returncode, "error": error}
        with open(failures_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(failure, ensure_ascii=False) + "\n")
        return {"cluster_id": cluster_id, "fund_code": fund_code, "skipped": False, "failed": True, "fund_dir": fund_dir}

    return {"cluster_id": cluster_id, "fund_code": fund_code, "skipped": False, "failed": False, "fund_dir": fund_dir}


def main():
    args = parse_args()
    ensure_dir(args.outdir)
    failures_path = os.path.join(args.outdir, "failures.jsonl")

    target_clusters = parse_clusters(args.clusters)
    cluster_ids = list_clusters(args.batch_outdir)
    if target_clusters is not None:
        target_set = set(target_clusters)
        cluster_ids = [cid for cid in cluster_ids if cid in target_set]

    results: List[Dict[str, Any]] = []

    for cluster_id in cluster_ids:
        inputs = load_cluster_inputs(args.batch_outdir, cluster_id)
        df_path = inputs["df_path"]
        feat_path = inputs["feat_path"]
        if not os.path.exists(df_path) or not os.path.exists(feat_path):
            failure = {
                "cluster_id": int(cluster_id),
                "error": "missing_inputs",
                "df_path": df_path,
                "feat_path": feat_path,
            }
            with open(failures_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(failure, ensure_ascii=False) + "\n")
            results.append(failure)
            continue

        import pandas as pd

        df = pd.read_csv(df_path)
        if "fund" not in df.columns:
            failure = {"cluster_id": int(cluster_id), "error": "missing_fund_column", "df_path": df_path}
            with open(failures_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(failure, ensure_ascii=False) + "\n")
            results.append(failure)
            continue

        funds = pd.Series(df["fund"].dropna().astype(str).unique()).tolist()
        for fund_code in funds:
            try:
                df_fund = df[df["fund"].astype(str) == str(fund_code)].copy()
                res = run_one_fund(cluster_id, fund_code, df_fund, feat_path, args, failures_path)
                results.append(res)
                print(res)
            except Exception as e:
                failure = {
                    "cluster_id": int(cluster_id),
                    "fund_code": str(fund_code),
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
                with open(failures_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(failure, ensure_ascii=False) + "\n")
                results.append(failure)
                print(failure)

    summary_path = os.path.join(args.outdir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
