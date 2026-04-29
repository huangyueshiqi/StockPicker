# 单基金规则提取与回测批处理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个批处理入口，按指定 cluster 范围对 cluster 内每只基金从 df_value 子集提取规则并调用主流程生成策略配置、调仓表与回测输出，落地到 `fund/batch_backtests/cluster_{id}/fund_{fund_code}/`。

**Architecture:** 批处理脚本逐 cluster 读取 `fund/batch_outputs/cluster_{id}/df_value.csv` 与 `selected_features_80pct.csv`，逐基金过滤子集并落地 `df_value.csv`，调用规则提取函数生成 `rule.txt`，再通过 subprocess 调用 `qlib_premium_value_strategy.py` 完整跑通到 `run_llm.py`。

**Tech Stack:** Python, pandas, subprocess

---

## Files Overview

- Create: `fund/run_fund_backtest_batch.py`
- Modify: `fund/extract_rules.py`（去除字段注释绝对路径硬编码，保证可在任意环境运行）

---

### Task 1: 改造规则提取支持可配置字段注释文件

**Files:**
- Modify: [/workspace/fund/extract_rules.py](file:///workspace/fund/extract_rules.py)

- [ ] **Step 1: 为 extract_rules_from_top_features 增加 desc_df_path 与 plot_path 可选参数**

把签名改为：

```python
def extract_rules_from_top_features(
    df,
    top_features_file='selected_features_80pct.csv',
    target_col='label',
    max_depth=3,
    desc_df_path: str = None,
    plot_path: str = None,
):
```

- [ ] **Step 2: 将 desc_df_path 透传到 analyze_leaf_nodes，并实现默认路径回退**

把 `analyze_leaf_nodes(...)` 改成：

```python
def analyze_leaf_nodes(tree_clf, feature_names, X, y, desc_df_path: str = None):
```

实现 desc_df 加载策略：
- 若 `desc_df_path` 非空且存在 → 读取
- 否则依次尝试：
  - `documents/财务量价字段表.csv`
  - `财务量价字段表.csv`
- 若都不存在 → 使用空 DataFrame（字段注释统一输出“未知”，不中断）

- [ ] **Step 3: 将决策树可视化输出改为可选**

在 `extract_rules_from_top_features` 里，仅当 `plot_path` 非空时才 `plt.savefig(plot_path, ...)`，否则跳过保存。

- [ ] **Step 4: 语法检查**

Run: `python -m py_compile /workspace/fund/extract_rules.py`  
Expected: exit code 0

---

### Task 2: 新增单基金规则+回测批处理脚本

**Files:**
- Create: `fund/run_fund_backtest_batch.py`

- [ ] **Step 1: CLI 参数与 clusters 解析（支持 0 / 0,1,2 / [0,1,2]）**

```python
def parse_clusters(v: str):
    s = v.strip()
    if s.lower() == "all":
        return None
    if s.startswith("["):
        import json
        return [int(x) for x in json.loads(s)]
    return [int(x.strip()) for x in s.split(",") if x.strip() != ""]
```

参数建议：
- `--clusters`（必填/默认 all）
- `--batch-outdir fund/batch_outputs`
- `--outdir fund/batch_backtests`
- `--resume / --no-resume`
- `--project-root`（透传到 `qlib_premium_value_strategy.py --project_root`）
- `--python`（默认 `sys.executable`）

- [ ] **Step 2: 逐 cluster 加载 df_value 与 selected_features**

对每个 cluster_id：
- `df_path = fund/batch_outputs/cluster_{id}/df_value.csv`
- `feat_path = fund/batch_outputs/cluster_{id}/selected_features_80pct.csv`
- 若缺失则记录 failures 并跳过

- [ ] **Step 3: 逐基金过滤 df_value 子集并写入输出目录**

对 `df['fund'].unique()` 循环：
- `fund_dir = fund/batch_backtests/cluster_{id}/fund_{fund_code}`
- 写 `df_value.csv`

- [ ] **Step 4: 生成 rule.txt（最优规则）**

调用：

```python
from fund.extract_rules import extract_rules_from_top_features
rules = extract_rules_from_top_features(
    df_fund,
    top_features_file=feat_path,
    target_col="label",
    max_depth=5,
    desc_df_path="documents/财务量价字段表.csv",
    plot_path=os.path.join(fund_dir, "decision_tree_rules.png"),
)
rule = rules[0] if rules else ""
```

保存 `rule.txt` 与 `run_meta.json`。

- [ ] **Step 5: 调用 qlib_premium_value_strategy.py 完整回测**

用 subprocess 调用（示例）：

```python
cmd = [
  python,
  "/workspace/qlib_premium_value_strategy.py",
  "--fund_df_path", df_value_path,
  "--fund_features_file", feat_path,
  "--trade_file", os.path.join(fund_dir, "trade.csv"),
  "--plot_output", os.path.join(fund_dir, "plot.png"),
  "--output", os.path.join(fund_dir, "backtest.log"),
  "--cache_id", cache_id,
  "--project_root", project_root,
]
```

要求：单基金失败不影响全局，失败写入 `fund/batch_backtests/failures.jsonl`。

- [ ] **Step 6: 语法检查**

Run: `python -m py_compile /workspace/fund/run_fund_backtest_batch.py`  
Expected: exit code 0

---

### Task 3: 最小验证

**Files:**
- None

- [ ] **Step 1: py_compile**

Run:

```bash
python -m py_compile /workspace/fund/run_fund_backtest_batch.py /workspace/fund/extract_rules.py
```

Expected: exit code 0

- [ ] **Step 2: CLI help（无 pandas 环境也可运行）**

Run: `python /workspace/fund/run_fund_backtest_batch.py -h | head -n 40`  
Expected: 正常输出帮助信息并退出（exit code 0）

