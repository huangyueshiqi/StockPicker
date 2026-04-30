from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from typing import Dict, List, Optional


def parse_targets(v: str) -> Optional[List[str]]:
    s = v.strip()
    if s.lower() == "all":
        return None
    if s.startswith("["):
        return [str(x) for x in json.loads(s)]
    return [x.strip() for x in s.split(",") if x.strip() != ""]


def parse_args():
    p = argparse.ArgumentParser(description="扫描 trade.csv 批量调用 run_llm.py 回测")
    p.add_argument("--root", default="fund/batch_backtests", help="包含 cluster_*/fund_*/trade.csv 的根目录")
    p.add_argument("--targets", default="all", help="all / fund_code 列表，如 000452.OF,399011.OF / 或 JSON 数组")
    p.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--project-root", default="/home/quant/zc/backtrader/QuantBacktester_57")
    p.add_argument("--python", default=sys.executable)
    return p.parse_args()


def find_trade_files(root: str) -> List[str]:
    out = []
    for dirpath, _, filenames in os.walk(root):
        if "trade.csv" in filenames:
            out.append(os.path.join(dirpath, "trade.csv"))
    return sorted(out)


def extract_fund_code_from_dir(trade_path: str) -> str:
    fund_dir = os.path.basename(os.path.dirname(trade_path))
    if fund_dir.startswith("fund_"):
        return fund_dir[len("fund_") :]
    return fund_dir


def build_run_llm_cmd(python: str, script_dir: str, trade_file: str, plot_output: str, output_log: str, project_root: str) -> List[str]:
    run_llm_path = os.path.join(script_dir, "run_llm.py")
    return [
        python,
        run_llm_path,
        "--mode",
        "llm",
        "--trade_file",
        trade_file,
        "--plot_output",
        plot_output,
        "--output",
        output_log,
        "--project_root",
        project_root,
    ]


def main():
    args = parse_args()
    args.root = os.path.abspath(args.root)
    failures_path = os.path.join(args.root, "backtest_failures.jsonl")
    summary_path = os.path.join(args.root, "backtest_summary.json")

    targets = parse_targets(args.targets)
    target_set = set(targets) if targets is not None else None

    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    trade_files = find_trade_files(args.root)
    results: List[Dict] = []

    for trade_path in trade_files:
        fund_dir = os.path.dirname(trade_path)
        fund_code = extract_fund_code_from_dir(trade_path)
        if target_set is not None and fund_code not in target_set:
            continue

        plot_output = os.path.join(fund_dir, "plot.png")
        output_log = os.path.join(fund_dir, "backtest.log")

        if args.resume and os.path.exists(output_log) and os.path.getsize(output_log) > 0 and os.path.exists(plot_output):
            res = {"fund_code": fund_code, "trade_file": trade_path, "skipped": True}
            results.append(res)
            print(res)
            continue

        try:
            cmd = build_run_llm_cmd(args.python, script_dir, trade_path, plot_output, output_log, args.project_root)
            strategy_log = os.path.join(fund_dir, "backtest_subprocess.log")
            with open(strategy_log, "w", encoding="utf-8") as f:
                p = subprocess.run(cmd, stdout=f, stderr=f)
            res = {"fund_code": fund_code, "trade_file": trade_path, "skipped": False, "returncode": int(p.returncode)}
            results.append(res)
            print(res)
            if p.returncode != 0:
                failure = {"fund_code": fund_code, "trade_file": trade_path, "returncode": int(p.returncode)}
                with open(failures_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(failure, ensure_ascii=False) + "\n")
        except Exception as e:
            failure = {"fund_code": fund_code, "trade_file": trade_path, "error": str(e), "traceback": traceback.format_exc()}
            with open(failures_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(failure, ensure_ascii=False) + "\n")
            results.append(failure)
            print(failure)

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
