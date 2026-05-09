from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from typing import Any, Dict, List, Optional


def parse_clusters(v: str) -> Optional[List[int]]:
    s = v.strip()
    if s.lower() == "all":
        return None
    if s.startswith("["):
        return [int(x) for x in json.loads(s)]
    return [int(x.strip()) for x in s.split(",") if x.strip() != ""]

def parse_variants(v: str) -> List[Dict[str, int | str]]:
    s = (v or "").strip()
    if s == "":
        return [{"variant_id": "rb60_top20", "rebalance_period": 60, "top_k": 20}]
    parts = [x.strip() for x in s.split(",") if x.strip() != ""]
    out: List[Dict[str, int | str]] = []
    for p in parts:
        m = re.fullmatch(r"rb(\d+)_top(\d+)", p)
        if not m:
            raise ValueError(f"invalid variant: {p}")
        out.append(
            {
                "variant_id": p,
                "rebalance_period": int(m.group(1)),
                "top_k": int(m.group(2)),
            }
        )
    return out


def apply_variant_to_strategy_config(base_config: Dict[str, Any], rebalance_period: int, top_k: int) -> Dict[str, Any]:
    cfg = json.loads(json.dumps(base_config))
    gp = cfg.get("global_params")
    if not isinstance(gp, dict):
        gp = {}
        cfg["global_params"] = gp
    gp["rebalance_period"] = int(rebalance_period)
    gp["top_K"] = int(top_k)
    if "top_k" in gp:
        gp["top_k"] = int(top_k)
    return cfg


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_args():
    p = argparse.ArgumentParser(description="按 cluster 范围逐基金提规则并跑 qlib_premium_value_strategy 回测")
    p.add_argument("--clusters", default="all", help="all / 0 / 0,1,2 / [0,1,2]")
    p.add_argument("--batch-outdir", default="fund/batch_outputs")
    p.add_argument("--outdir", default="fund/batch_backtests")
    p.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--variants", default="rb60_top20,rb20_top20,rb20_top10")
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

def should_skip_fund_rule(rule: str) -> bool:
    return not bool((rule or "").strip())

def build_qlib_strategy_command(
    python: str,
    script: str,
    fund_rule_file: str,
    trade_file: str,
    cache_id: str,
    project_root: str,
    *,
    no_llm: bool = False,
    strategy_config: str = "",
    mapping_file: str = "",
) -> List[str]:
    cmd: List[str] = [
        python,
        script,
        "--trade_file",
        trade_file,
        "--cache_id",
        cache_id,
        "--project_root",
        project_root,
        "--interactive",
        "--skip_backtest",
    ]
    if no_llm:
        cmd.extend(
            [
                "--no_llm",
                "--strategy_config",
                strategy_config,
                "--mapping_file",
                mapping_file,
            ]
        )
    else:
        cmd.extend(["--fund_rule_file", fund_rule_file])
    return cmd


def _copy_base_cache_from_llm_cache(cache_id: str, base_cache_dir: str) -> None:
    cache_dir = os.path.join("config", "llm_cache", cache_id)
    src_config = os.path.join(cache_dir, "generated_strategy.json")
    src_mapping = os.path.join(cache_dir, "mapping_result.json")
    if not os.path.exists(src_config) or not os.path.exists(src_mapping):
        raise FileNotFoundError(f"missing llm cache outputs: {cache_dir}")
    ensure_dir(base_cache_dir)
    shutil.copyfile(src_config, os.path.join(base_cache_dir, "strategy_config.json"))
    shutil.copyfile(src_mapping, os.path.join(base_cache_dir, "mapping_result.json"))


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
    variants = parse_variants(getattr(args, "variants", ""))
    base_variant = variants[0]
    base_variant_id = str(base_variant["variant_id"])

    variants_root = os.path.join(fund_dir, "variants")
    base_cache_dir = os.path.join(fund_dir, "base_cache")
    base_cache_config = os.path.join(base_cache_dir, "strategy_config.json")
    base_cache_mapping = os.path.join(base_cache_dir, "mapping_result.json")

    if not os.path.exists(df_value_path):
        df_fund.to_csv(df_value_path, index=False)

    if not (args.resume and os.path.exists(rule_path)):
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

        if should_skip_fund_rule(rule):
            meta_path = os.path.join(fund_dir, "run_meta.json")
            meta = {
                "cluster_id": int(cluster_id),
                "fund_code": str(fund_code),
                "variant_id": None,
                "cache_id": None,
                "cmd": None,
                "returncode": 0,
                "error": "no_rule_extracted",
                "traceback": None,
                "df_rows": int(getattr(df_fund, "shape", [0])[0]),
            }
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            return {
                "cluster_id": cluster_id,
                "fund_code": fund_code,
                "skipped": True,
                "fund_dir": fund_dir,
                "reason": "no_rule_extracted",
            }

    ensure_dir(variants_root)

    results: List[Dict[str, Any]] = []
    base_cache_id = f"cluster{cluster_id}_{fund_code}_{base_variant_id}"

    for idx, v in enumerate(variants):
        variant_id = str(v["variant_id"])
        variant_dir = os.path.join(variants_root, variant_id)
        ensure_dir(variant_dir)
        trade_path = os.path.join(variant_dir, "trade.csv")
        meta_path = os.path.join(variant_dir, "run_meta.json")
        strategy_log = os.path.join(variant_dir, "strategy.log")

        if args.resume and os.path.exists(trade_path):
            results.append(
                {
                    "cluster_id": cluster_id,
                    "fund_code": fund_code,
                    "variant_id": variant_id,
                    "skipped": True,
                    "fund_dir": fund_dir,
                    "variant_dir": variant_dir,
                }
            )
            continue

        cache_id = f"cluster{cluster_id}_{fund_code}_{variant_id}"

        try:
            if idx == 0 and not (os.path.exists(base_cache_config) and os.path.exists(base_cache_mapping)):
                cmd = build_qlib_strategy_command(
                    python=args.python,
                    script="/workspace/qlib_premium_value_strategy.py",
                    fund_rule_file=rule_path,
                    trade_file=trade_path,
                    cache_id=base_cache_id,
                    project_root=args.project_root,
                )
                with open(strategy_log, "w", encoding="utf-8") as f:
                    p = subprocess.run(cmd, stdout=f, stderr=f)
                returncode = int(p.returncode)
                if returncode == 0:
                    _copy_base_cache_from_llm_cache(base_cache_id, base_cache_dir)
                    base_cfg = _read_json(base_cache_config)
                    new_cfg = apply_variant_to_strategy_config(
                        base_cfg,
                        rebalance_period=int(v["rebalance_period"]),
                        top_k=int(v["top_k"]),
                    )
                    _write_json(os.path.join(variant_dir, "strategy_config.json"), new_cfg)
                error = None
                tb = None
            else:
                if not (os.path.exists(base_cache_config) and os.path.exists(base_cache_mapping)):
                    raise FileNotFoundError("base_cache_missing")
                base_cfg = _read_json(base_cache_config)
                new_cfg = apply_variant_to_strategy_config(
                    base_cfg,
                    rebalance_period=int(v["rebalance_period"]),
                    top_k=int(v["top_k"]),
                )
                variant_cfg_path = os.path.join(variant_dir, "strategy_config.json")
                _write_json(variant_cfg_path, new_cfg)
                cmd = build_qlib_strategy_command(
                    python=args.python,
                    script="/workspace/qlib_premium_value_strategy.py",
                    fund_rule_file=rule_path,
                    trade_file=trade_path,
                    cache_id=cache_id,
                    project_root=args.project_root,
                    no_llm=True,
                    strategy_config=variant_cfg_path,
                    mapping_file=base_cache_mapping,
                )
                with open(strategy_log, "w", encoding="utf-8") as f:
                    p = subprocess.run(cmd, stdout=f, stderr=f)
                returncode = int(p.returncode)
                error = None
                tb = None
        except Exception as e:
            returncode = 1
            error = str(e)
            tb = traceback.format_exc()

        meta = {
            "cluster_id": int(cluster_id),
            "fund_code": str(fund_code),
            "variant_id": variant_id,
            "cache_id": base_cache_id if idx == 0 else cache_id,
            "cmd": None,
            "returncode": returncode,
            "error": error,
            "traceback": tb,
            "df_rows": int(getattr(df_fund, "shape", [0])[0]),
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        if returncode != 0:
            failure = {
                "cluster_id": int(cluster_id),
                "fund_code": str(fund_code),
                "variant_id": variant_id,
                "returncode": returncode,
                "error": error,
            }
            with open(failures_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(failure, ensure_ascii=False) + "\n")
            results.append(
                {
                    "cluster_id": cluster_id,
                    "fund_code": fund_code,
                    "variant_id": variant_id,
                    "skipped": False,
                    "failed": True,
                    "fund_dir": fund_dir,
                    "variant_dir": variant_dir,
                }
            )
        else:
            results.append(
                {
                    "cluster_id": cluster_id,
                    "fund_code": fund_code,
                    "variant_id": variant_id,
                    "skipped": False,
                    "failed": False,
                    "fund_dir": fund_dir,
                    "variant_dir": variant_dir,
                }
            )

    if len(results) == 1:
        return results[0]
    return {"cluster_id": cluster_id, "fund_code": fund_code, "variants": results, "fund_dir": fund_dir}


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
