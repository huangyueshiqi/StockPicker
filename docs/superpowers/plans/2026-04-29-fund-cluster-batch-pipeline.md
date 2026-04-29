# Fund Cluster 批量特征与 SHAP 产物 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个离线入口脚本，基于本地 `cluster_result0427.csv` + `processed_fund_holdings.csv`，按 cluster 批量生成每个 cluster 的 `df_value.csv` 与 `selected_features_80pct.csv`，输出到 `fund/batch_outputs/cluster_{id}/`。

**Architecture:** 一个编排脚本循环 cluster：过滤持仓 → 计算区间/股票池 → 复用 fund/qlib_reader.py 拉数与构建训练样本 → 复用 fund/xgb_shap.py 训练并输出 SHAP 特征选择；对每个 cluster 独立输出并支持 resume/失败不中断。

**Tech Stack:** Python, pandas, qlib, xgboost, shap

---

## Files Overview

- Create: `fund/run_cluster_batch.py`
- Modify (light refactor): `fund/qlib_reader.py`（支持参数化路径与输出文件名）
- Modify (light refactor): `fund/xgb_shap.py`（支持指定输出目录与文件名）

---

### Task 1: 为 qlib_reader 提供可复用的“按参数拉数与构建样本”接口

**Files:**
- Modify: [/workspace/fund/qlib_reader.py](file:///workspace/fund/qlib_reader.py)

- [ ] **Step 1: 新增一个参数对象与默认值函数**

在文件底部（`if __name__ == "__main__":` 之前）新增：

```python
from dataclasses import dataclass
from typing import Sequence, Tuple

@dataclass
class QlibReaderParams:
    docs_dir: str = "documents"
    price_data_path: str = "/home/quant/zc/finance_deal/qlib_data/price_data0821"
    fin_data_path: str = "/home/quant/zc/finance_deal/qlib_data/pit_data"
    field_csv_files: Tuple[str, str] = ("财务字段中英文对照表.csv", "量价字段中英文对照表.csv")
```

- [ ] **Step 2: 改造 get_all_csv_data 支持 params 覆盖 docs_dir / qlib 路径**

将 `get_all_csv_data(instruments, start_time, end_time)` 改为：

```python
def get_all_csv_data(instruments: list, start_time: str, end_time: str, params: QlibReaderParams):
    docs_dir = params.docs_dir
    csv_files = [os.path.join(docs_dir, f) for f in params.field_csv_files]
    ...
```

并将 `read_qlibdata` 内部的 `price_data_path/fin_data_path` 改为由 params 传入（可在 `read_qlibdata` 增加参数，或直接使用模块级变量并在入口处赋值；推荐显式参数）。

- [ ] **Step 3: 抽出“构建 factor_data”的函数**

新增函数：

```python
def build_factor_data(
    fund_holding4: pd.DataFrame,
    params: QlibReaderParams,
):
    start_date = fund_holding4["F_PRT_ENDDATE"].min()
    end_date = fund_holding4["F_PRT_ENDDATE"].max()
    instruments = fund_holding4["S_INFO_STOCKWINDCODE"].dropna().unique().tolist()
    target_dates = pd.to_datetime(pd.Series(fund_holding4["F_PRT_ENDDATE"].dropna().unique()))
    financial_data, price_data = get_all_csv_data(instruments, start_date, end_date, params=params)
    financial_data["datetime"] = pd.to_datetime(financial_data["datetime"])
    price_data["datetime"] = pd.to_datetime(price_data["datetime"])
    price_data = price_data[price_data["datetime"].isin(target_dates)]
    fin_data = financial_data.sort_values(by="datetime").reset_index(drop=True)
    price_data = price_data.sort_values(by="datetime").reset_index(drop=True)
    factor_data = pd.merge_asof(
        left=price_data,
        right=fin_data,
        on="datetime",
        by="instrument",
        direction="backward",
    )
    factor_data = factor_data.sort_values(by="datetime").reset_index(drop=True)
    return factor_data
```

- [ ] **Step 4: 语法检查**

Run: `python -m py_compile /workspace/fund/qlib_reader.py`  
Expected: exit code 0

---

### Task 2: 为 xgb_shap 提供“指定输出目录”的可复用接口

**Files:**
- Modify: [/workspace/fund/xgb_shap.py](file:///workspace/fund/xgb_shap.py)

- [ ] **Step 1: 将 train_and_explain 增加 output_dir 参数**

将函数签名改为：

```python
def train_and_explain(df, feature_cols, target_col="label", train_full=False, shap_coverage=0.8, output_dir: str = "."):
```

- [ ] **Step 2: 输出文件写入 output_dir**

把下面这些写死输出：
- `feature_shap_importance.csv`
- `selected_features_80pct.csv`
- `shap_summary_plot.png`

改为：

```python
os.makedirs(output_dir, exist_ok=True)
output_csv = os.path.join(output_dir, "feature_shap_importance.csv")
selected_path = os.path.join(output_dir, "selected_features_80pct.csv")
plt.savefig(os.path.join(output_dir, "shap_summary_plot.png"), dpi=300)
```

- [ ] **Step 3: 语法检查**

Run: `python -m py_compile /workspace/fund/xgb_shap.py`  
Expected: exit code 0

---

### Task 3: 新增批量编排脚本 run_cluster_batch.py

**Files:**
- Create: `fund/run_cluster_batch.py`

- [ ] **Step 1: 写入 CLI 与参数解析**

```python
import argparse

def parse_args():
    p = argparse.ArgumentParser(description="批量生成各 cluster 的 df_value 与 SHAP 特征选择文件")
    p.add_argument("--cluster-map", default="cluster_result0427.csv")
    p.add_argument("--holdings", default="processed_fund_holdings.csv")
    p.add_argument("--outdir", default="fund/batch_outputs")
    p.add_argument("--clusters", default="all", help="all 或逗号分隔的 cluster_id 列表，如 0,1,2")
    p.add_argument("--resume", action="store_true", default=True)
    p.add_argument("--neg-ratio", type=float, default=1.0)
    p.add_argument("--nan-threshold", type=float, default=0.6)
    p.add_argument("--train-full", action="store_true", default=True)
    p.add_argument("--shap-coverage", type=float, default=0.8)
    p.add_argument("--docs-dir", default="documents")
    p.add_argument("--qlib-price-path", default="/home/quant/zc/finance_deal/qlib_data/price_data0821")
    p.add_argument("--qlib-fin-path", default="/home/quant/zc/finance_deal/qlib_data/pit_data")
    return p.parse_args()
```

- [ ] **Step 2: 加载输入并枚举 cluster**

```python
import os, json, traceback
import pandas as pd

def parse_clusters_arg(v: str):
    if v.strip().lower() == "all":
        return None
    return [int(x) for x in v.split(",") if x.strip() != ""]
```

加载 `cluster_result0427.csv`（必须含 `fund_code`, `cluster_id`），构造 `cluster_id -> fund_code[]`；加载 `processed_fund_holdings.csv`（必须含 `S_INFO_WINDCODE` 等）。

- [ ] **Step 3: 对每个 cluster 执行：构建 df_value 与 SHAP**

核心循环伪码（写成真实代码）：

```python
from fund.qlib_reader import QlibReaderParams, build_factor_data, build_df_for_xgb
from fund.xgb_shap import train_and_explain

def run_one_cluster(cluster_id: int, fund_codes: list, holdings: pd.DataFrame, args):
    out_dir = os.path.join(args.outdir, f"cluster_{cluster_id}")
    os.makedirs(out_dir, exist_ok=True)
    df_path = os.path.join(out_dir, "df_value.csv")
    selected_path = os.path.join(out_dir, "selected_features_80pct.csv")
    if args.resume and os.path.exists(df_path) and os.path.exists(selected_path):
        return {"cluster_id": cluster_id, "skipped": True, "out_dir": out_dir}

    sub = holdings[holdings["S_INFO_WINDCODE"].isin(fund_codes)].copy()
    if sub.empty:
        return {"cluster_id": cluster_id, "skipped": True, "reason": "no holdings"}

    params = QlibReaderParams(docs_dir=args.docs_dir, price_data_path=args.qlib_price_path, fin_data_path=args.qlib_fin_path)
    factor_data = build_factor_data(sub, params=params)
    df_value, feature_cols = build_df_for_xgb(sub, factor_data, neg_ratio=args.neg_ratio)
    df_value.to_csv(df_path, index=False)

    train_and_explain(df_value, feature_cols, target_col="label", train_full=args.train_full, shap_coverage=args.shap_coverage, output_dir=out_dir)
    with open(os.path.join(out_dir, "run_meta.json"), "w", encoding="utf-8") as f:
        json.dump({"cluster_id": cluster_id, "fund_count": len(fund_codes), "rows": int(df_value.shape[0])}, f, ensure_ascii=False, indent=2)
    return {"cluster_id": cluster_id, "skipped": False, "out_dir": out_dir}
```

失败处理：捕获异常并写入 `fund/batch_outputs/failures.jsonl`，不中断全局。

- [ ] **Step 4: 语法检查**

Run: `python -m py_compile /workspace/fund/run_cluster_batch.py`  
Expected: exit code 0

---

### Task 4: 最小可运行验证（不依赖真实数据正确性）

**Files:**
- None

- [ ] **Step 1: 编译所有相关脚本**

Run:

```bash
python -m py_compile /workspace/fund/run_cluster_batch.py /workspace/fund/qlib_reader.py /workspace/fund/xgb_shap.py
```

Expected: exit code 0

- [ ] **Step 2: 查看 CLI help**

Run: `python /workspace/fund/run_cluster_batch.py -h | head -n 40`  
Expected: 打印参数说明并正常退出（exit code 0）

