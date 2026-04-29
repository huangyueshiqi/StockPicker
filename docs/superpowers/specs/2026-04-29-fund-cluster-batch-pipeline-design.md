# Fund Cluster 批量特征与 SHAP 产物设计

**Goal**

基于本地 CSV 输入，按 `cluster_result0427.csv` 的 `cluster_id` 分组批量跑完特征构建与 SHAP 选特征流程，为每个 cluster 输出：
- `fund/batch_outputs/cluster_{id}/df_value.csv`
- `fund/batch_outputs/cluster_{id}/selected_features_80pct.csv`

可选输出：
- `feature_shap_importance.csv`
- `shap_summary_plot.png`

---

## 现状与痛点

当前流程分散在三个脚本里，且带有硬编码路径与手工操作：
- 数据准备（DB 或 CSV）与清洗：[process_fund_holdings.py](file:///workspace/fund/process_fund_holdings.py)
- Qlib 拉数、合并并构建训练样本：[qlib_reader.py](file:///workspace/fund/qlib_reader.py)
- XGBoost 训练与 SHAP 特征筛选：[xgb_shap.py](file:///workspace/fund/xgb_shap.py)

目标是做一个“编排脚本”，复用现有函数能力，做到“一键批量跑所有 cluster”。

---

## 输入与输出

### 输入（相对仓库根目录）
- `cluster_result0427.csv`
  - 必须列：`fund_code`, `cluster_id`
- `processed_fund_holdings.csv`
  - 必须列：`S_INFO_WINDCODE`（基金代码）, `S_INFO_STOCKWINDCODE`（股票代码）, `F_PRT_ENDDATE`（报告期/持仓期末日）, `ANN_DATE`
- Qlib 数据与字段对照 CSV
  - Qlib：
    - 价格数据目录（默认沿用 [qlib_reader.py](file:///workspace/fund/qlib_reader.py#L37-L40) 的路径，但改为 CLI 参数覆盖）
    - 财务数据目录（同上）
  - 字段对照：
    - `documents/财务字段中英文对照表.csv`
    - `documents/量价字段中英文对照表.csv`
    - 位置由 `--docs-dir` 指定

### 输出目录结构
- `fund/batch_outputs/cluster_{cluster_id}/df_value.csv`
- `fund/batch_outputs/cluster_{cluster_id}/selected_features_80pct.csv`
- `fund/batch_outputs/cluster_{cluster_id}/run_meta.json`（建议：记录参数/样本量/时间范围/失败原因等）

---

## Pipeline（每个 cluster 的执行逻辑）

对每个 `cluster_id`：

1) **过滤 cluster 对应基金**
- 从 `cluster_result0427.csv` 中取出该 cluster 的 `fund_code` 列表
- 在 `processed_fund_holdings.csv` 里按 `S_INFO_WINDCODE` 过滤得到 `fund_holding_cluster`

2) **计算区间与股票池**
- 区间：
  - `start_date = fund_holding_cluster['F_PRT_ENDDATE'].min()`
  - `end_date = fund_holding_cluster['F_PRT_ENDDATE'].max()`
- 股票池：
  - `instruments = unique(fund_holding_cluster['S_INFO_STOCKWINDCODE'])`
- 注意：日期格式以 `YYYY-MM-DD` 传给 Qlib（保持和现有 [qlib_reader.py](file:///workspace/fund/qlib_reader.py#L162-L198) 行为一致）

3) **Qlib 拉数与合并 factor_data**
- 复用 [qlib_reader.py](file:///workspace/fund/qlib_reader.py)：
  - `read_csv_fields` / `build_qlib_fields`
  - `read_qlibdata`
  - `get_all_csv_data`
- 取得 `financial_data` + `price_data` 后，按 `datetime` + `instrument` 用 `merge_asof` 合并成 `factor_data`

4) **构建训练集 df_value**
- 复用 [qlib_reader.py](file:///workspace/fund/qlib_reader.py#L251-L297) 的 `build_df_for_xgb`
  - 正样本：基金真实持仓
  - 负样本：按 `neg_ratio` 从股票池里随机采样（同基金同报告期）
  - `merge_asof` 对齐特征
  - 丢弃缺失率过高的列（阈值默认 0.6，可参数化）
- 输出 `df_value.csv`

5) **训练与 SHAP 特征筛选**
- 复用 [xgb_shap.py](file:///workspace/fund/xgb_shap.py#L25-L115) 的 `train_and_explain`
  - `train_full` 默认 True（沿用你现在的 main）
  - `shap_coverage` 默认 0.8
- 产物至少包含 `selected_features_80pct.csv`

---

## 新增入口脚本

新增文件：`fund/run_cluster_batch.py`

### CLI 参数
- `--cluster-map cluster_result0427.csv`
- `--holdings processed_fund_holdings.csv`
- `--outdir fund/batch_outputs`
- `--clusters all|0,1,2`（默认 all）
- `--neg-ratio 1`
- `--nan-threshold 0.6`
- `--train-full true|false`（默认 true）
- `--shap-coverage 0.8`
- `--n-estimators 100` / `--max-depth 5` / `--learning-rate 0.05`（先与现有默认一致）
- `--qlib-price-path ...`
- `--qlib-fin-path ...`
- `--docs-dir documents`
- `--resume`（默认 true：若该 cluster 输出文件已存在则跳过）

### 日志与失败处理
- 每个 cluster 处理包裹 `try/except`，失败写入 `fund/batch_outputs/failures.jsonl`
  - 记录：`cluster_id`, `error`, `traceback`, `start_date/end_date`, `n_records`

---

## 最小验收标准
- 能在“仅依赖本地 CSV”的情况下循环所有 cluster 并在对应目录落地 `df_value.csv` 与 `selected_features_80pct.csv`
- 支持 `--clusters 0,1` 只跑部分 cluster
- 支持 `--resume` 跳过已完成 cluster
- 对单个 cluster 的异常不会中断全局跑批

