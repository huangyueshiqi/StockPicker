# Fund 日期区间透传到策略配置生成器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从 fund 特征数据的 datetime 列自动计算回测开始/结束日期，并在生成策略配置 JSON 时作为强约束透传给 LLMStrategyGenerator，避免模型自行猜测区间。

**Architecture:** 主流程读取 fund_df 后提取最优规则，同时计算 start_date/end_date（YYYYMMDD）；调用 LLMStrategyGenerator.generate 时传入 start_date/end_date；Prompt 显式提供“已知回测区间”，要求模型优先写入 global_params。

**Tech Stack:** Python, pandas, langchain_openai, pydantic

---

### Task 1: 为策略配置生成器增加显式回测区间输入

**Files:**
- Modify: [/workspace/framework/llm_strategy_generator.py](file:///workspace/framework/llm_strategy_generator.py)

- [ ] **Step 1: 扩展 LLM_STRATEGY_PROMPT 支持 start_date/end_date 变量**

在 Prompt 中新增 “已知回测信息” 段落，并要求：若变量不为空，必须写入 `global_params.start_date/end_date`。

- [ ] **Step 2: 修改 LLMStrategyGenerator.generate() 签名并透传变量到 chain.invoke**

```python
def generate(self, user_input: str, output_file: str, start_date: str = None, end_date: str = None):
    ...
    strategy_config = chain.invoke({"user_input": user_input, "start_date": start_date, "end_date": end_date})
```

- [ ] **Step 3: 运行语法检查**

Run: `python -m py_compile /workspace/framework/llm_strategy_generator.py`  
Expected: exit code 0

- [ ] **Step 4: Commit（仅在用户明确要求时）**

```bash
git add /workspace/framework/llm_strategy_generator.py
git commit -m "feat: pass date range into strategy generator"
```

### Task 2: 主流程从 fund_df 自动计算日期并传入生成器

**Files:**
- Modify: [/workspace/qlib_premium_value_strategy.py](file:///workspace/qlib_premium_value_strategy.py)

- [ ] **Step 1: 从 df_fund['datetime'] 计算 YYYYMMDD 的 start_date/end_date**

```python
dt = pd.to_datetime(df_fund["datetime"], errors="coerce")
start_date = dt.min().strftime("%Y%m%d")
end_date = dt.max().strftime("%Y%m%d")
```

- [ ] **Step 2: 在 generator.generate 调用处传入 start_date/end_date（仅 fund 模式下）**

```python
strategy_config = generator.generate(prompt, config_path, start_date=fund_start_date, end_date=fund_end_date)
```

- [ ] **Step 3: 清理未使用 import（如果存在）并做语法检查**

Run: `python -m py_compile /workspace/qlib_premium_value_strategy.py`  
Expected: exit code 0

- [ ] **Step 4: Commit（仅在用户明确要求时）**

```bash
git add /workspace/qlib_premium_value_strategy.py
git commit -m "feat: derive date range from fund df and pass to generator"
```

### Task 3: 端到端最小验证（不触发真实 LLM/回测）

**Files:**
- None

- [ ] **Step 1: 编译关键文件确保无语法错误**

Run:

```bash
python -m py_compile /workspace/qlib_premium_value_strategy.py /workspace/framework/llm_strategy_generator.py /workspace/fund/extract_rules.py
```

Expected: exit code 0

