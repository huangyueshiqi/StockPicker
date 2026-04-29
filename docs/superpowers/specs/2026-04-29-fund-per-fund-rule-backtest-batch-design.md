# 单基金规则提取与回测批处理设计

**Goal**

基于 cluster 级产物（`fund/batch_outputs/cluster_{id}/df_value.csv` 与 `selected_features_80pct.csv`），对指定 cluster 范围内的每只基金：
1) 从该基金样本子集提取最优决策树规则
2) 用规则驱动主流程生成策略配置、字段映射与调仓表
3) 调用外部回测框架（`run_llm.py`）完成回测

批处理输出组织为：
`fund/batch_backtests/cluster_{id}/fund_{fund_code}/...`

---

## 输入与范围控制

### 输入
- `fund/batch_outputs/cluster_{id}/df_value.csv`
- `fund/batch_outputs/cluster_{id}/selected_features_80pct.csv`

### cluster 选择参数
支持以下形式解析为 `List[int]`：
- `--clusters 0`
- `--clusters 0,1,2`
- `--clusters [0,1,2]`

---

## 关键数据流

对每个 `cluster_id`：
1) 加载 `df_value.csv`，按 `fund` 列枚举该 cluster 内基金集合
2) 对每只基金：
   - 过滤得到单基金子集 `df_fund = df_value[df_value['fund'] == fund_code]`
   - 写入 `fund/batch_backtests/cluster_{id}/fund_{fund_code}/df_value.csv`（仅作中间产物与可复现输入）
   - 使用 cluster 级 `selected_features_80pct.csv` 作为 top_features_file，调用规则提取函数输出“最优规则”
   - 调用 `qlib_premium_value_strategy.py` 的 fund 模式：
     - `--fund_df_path` 指向该基金的 `df_value.csv`
     - `--fund_features_file` 指向 cluster 的 `selected_features_80pct.csv`
     - `--trade_file` 输出到 `.../trade.csv`
     - `--plot_output` 输出到 `.../plot.png`
     - `--output` 将回测输出重定向到 `.../backtest.log`（避免刷屏）
     - `--cache_id` 使用稳定命名（例如 `fund_{fund_code}_cluster_{id}_<timestamp>`）避免互相覆盖
     - `--project_root` 可由批处理脚本透传
   - 每个基金失败不影响整体，写入 `failures.jsonl`

---

## 对现有模块的最小改造

### 1) 规则提取去硬编码字段注释路径

当前 [extract_rules.py](file:///workspace/fund/extract_rules.py) 在 `analyze_leaf_nodes` 中读取字段注释使用绝对路径：
`/home/quant/zc/backtrader/QuantStockPicker/documents/财务量价字段表.csv`

改造为：
- `extract_rules_from_top_features(..., desc_df_path: Optional[str] = None)` 增加可选参数
- `desc_df_path` 为空时，按以下顺序尝试：
  1) `documents/财务量价字段表.csv`
  2) `财务量价字段表.csv`
  3) 不存在则使用空 DataFrame（字段注释默认“未知”，不阻断执行）

保持与当前 [qlib_premium_value_strategy.py](file:///workspace/qlib_premium_value_strategy.py) 的调用兼容（不传参也可用）。

---

## 新增批处理入口

新增脚本：`fund/run_fund_backtest_batch.py`

### CLI 参数（建议）
- `--clusters 0 | 0,1,2 | [0,1,2]`
- `--batch-outdir fund/batch_outputs`
- `--outdir fund/batch_backtests`
- `--resume / --no-resume`（默认 resume：若 trade/log 等存在则跳过）
- `--project-root`（透传到回测）
- `--python`（可选，默认 `sys.executable`）

### 产物
每只基金目录下建议包含：
- `df_value.csv`
- `rule.txt`（最优规则字符串）
- `trade.csv`（调仓表）
- `plot.png`
- `backtest.log`（回测输出）
- `run_meta.json`（参数、日期区间、行数、是否跳过等）

---

## 最小验收标准

- 在不修改输入数据的情况下，脚本能对指定 cluster 范围内基金逐个执行并产出上述目录结构
- `--clusters` 参数支持 `0` 与 `[0,1,2]` 两种风格
- 单基金失败不中断整体，失败可追溯（failures.jsonl）

