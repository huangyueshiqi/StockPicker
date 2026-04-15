# Qlib Premium Value Strategy End-to-End Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate prompt input, LLM strategy generation, stock selection, and automated backtesting into a single, cohesive command-line pipeline.

**Architecture:** Modify `qlib_premium_value_strategy.py` to use `argparse` for CLI inputs (prompt, backtest configs). The script will sequentially call the `LLMStrategyGenerator`, execute the strategy to produce a rebalance CSV, and finally call a newly appended `run_backtest` function that infers dates and runs the `BacktestManager` to produce a plot.

**Tech Stack:** Python 3, `pandas`, `argparse`, `logging`.

---

### Task 1: Refactor `qlib_premium_value_strategy.py` to accept CLI arguments

**Files:**
- Modify: `/workspace/qlib_premium_value_strategy.py`

- [ ] **Step 1: Import necessary modules**
Add imports for `argparse`, `logging`, `sys`, and `time` at the top of the file if they are missing.
```python
import argparse
import logging
import sys
import time
```

- [ ] **Step 2: Add `parse_args` function**
Create a `parse_args` function to handle CLI inputs.
```python
def parse_args():
    parser = argparse.ArgumentParser(description='LLM 策略量化交易回测系统端到端流水线')
    parser.add_argument('--prompt', type=str, default='', help='自然语言策略描述')
    parser.add_argument('--interactive', action='store_true', help='如果没有提供prompt，是否进入交互模式输入')
    parser.add_argument('--mode', type=str, default='llm', help='回测模式，固定为llm')
    parser.add_argument('--trade_file', type=str, default='qlib_premium_value_strategy_result.csv', help='调仓表文件路径')
    parser.add_argument('--output', type=str, default='', help='输出结果文件路径')
    parser.add_argument('--plot_output', type=str, default='plot/llm_strategy_plot.png', help='策略回测资产变化图保存路径')
    parser.add_argument('--plot_trades', action='store_true', default=False, help='是否绘制每只股票的买卖点图 (默认关闭)')
    parser.add_argument('--verbose', action='store_true', help='是否输出详细信息')
    parser.add_argument('--project_root', type=str, default='/home/quant/zc/backtrader/QuantBacktester_57', help='QuantBacktester项目的根目录路径')
    return parser.parse_args()
```

- [ ] **Step 3: Modify `main` to accept args and handle prompt input**
Change the `main()` function signature to `def main(args):`.
Implement logic to get the prompt from `args.prompt` or `input()`.
```python
def main(args):
    print("\n===== 使用 Qlib 数据源的端到端智能策略回测 =====")
    
    # 确定 prompt
    prompt = args.prompt
    if not prompt:
        if args.interactive:
            prompt = input("请输入你的选股策略描述 (例如: 寻找低市盈率、高ROE的股票，每60天调仓): ")
        else:
            prompt = "寻找低市盈率、高ROE的股票，每60天调仓" # 默认 fallback
            print(f"未提供 prompt 且未开启交互模式，使用默认 prompt: {prompt}")

    # ... existing code for directory setup ...
```

- [ ] **Step 4: Update `LLMStrategyGenerator` invocation in `main`**
Pass the obtained `prompt` to `generator.generate_strategy(prompt)`.
```python
    generator = LLMStrategyGenerator(
        csv_files=csv_files,
        config_dir=config_dir,
        output_filename=config_filename,
        mapping_filename="mapping_result.json"
    )
    generator.generate_strategy(prompt)
```

- [ ] **Step 5: Update `save_results` in `main`**
Save the results to `args.trade_file` instead of a hardcoded string.
```python
    strategy.save_results(rebalance_result, args.trade_file)
    print(f"调仓表已保存至: {args.trade_file}")
```

- [ ] **Step 6: Update the script entry block**
Parse arguments and pass them to `main()`.
```python
if __name__ == "__main__":
    args = parse_args()
    main(args)
```

- [ ] **Step 7: Commit**
```bash
git add qlib_premium_value_strategy.py
git commit -m "feat: refactor qlib strategy script to use argparse for prompt input"
```

### Task 2: Append backtest logic to `qlib_premium_value_strategy.py`

**Files:**
- Modify: `/workspace/qlib_premium_value_strategy.py`

- [ ] **Step 1: Add the `run_backtest` function**
Define the `run_backtest(args)` function containing the user-provided logic. Place this above `main()`.
```python
def run_backtest(args):
    """执行回测流程"""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    if not os.path.exists(args.trade_file):
        logging.error(f"调仓表文件不存在: {args.trade_file}")
        return

    # 动态将项目根目录加入到 sys.path 中
    project_root = os.path.abspath(args.project_root)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    try:
        from main import BacktestManager
        from utils.config import config
    except ImportError as e:
        logging.error(f"导入回测框架失败，请检查 project_root 路径是否正确 ({project_root}): {e}")
        return

    try:
        trade_list = pd.read_csv(args.trade_file)
        if 'datetime' not in trade_list.columns and 'date' in trade_list.columns:
            date_col = 'date'
        elif 'datetime' in trade_list.columns:
            date_col = 'datetime'
        else:
            logging.error("调仓表中没有找到日期列 (date/datetime)")
            return

        trade_list[date_col] = pd.to_datetime(trade_list[date_col])
        min_date = trade_list[date_col].min().strftime('%Y-%m-%d')
        max_date = trade_list[date_col].max().strftime('%Y-%m-%d')

        start_date = min_date
        end_date = (pd.to_datetime(max_date) + pd.Timedelta(days=30)).strftime('%Y-%m-%d')
        logging.info(f"根据调仓表推断回测区间: {start_date} -> {end_date}")
    except Exception as e:
        logging.error(f"读取调仓表出错: {e}")
        return

    param_map = {
        'start_date': start_date,
        'end_date': end_date,
        'deal_dividend': False,
        'save_state': False,
        'adjust_freq': 'D',
        'is_predict': False,
    }

    if param_map:
        print("\n=== 策略配置参数更新 ===")
        config.update_strategy_params(**param_map)
        print("=======================")

    if args.output:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        sys.stdout = open(args.output, 'w', encoding='utf-8')

    start_time = time.time()
    print("执行 LLM 回测...")
    
    backtest_manager = BacktestManager()
    backtest_manager.run_llm_backtest(
        trade_file=args.trade_file,
        plot_output=args.plot_output,
        plot_trades=args.plot_trades,
        verbose=args.verbose
    )

    end_time = time.time()
    print(f'回测总运行时间：{end_time - start_time:.2f}秒')

    if args.output:
        sys.stdout.close()
        sys.stdout = sys.__stdout__
```

- [ ] **Step 2: Invoke `run_backtest` from `main`**
Call `run_backtest(args)` at the end of the `main` function, after `save_results`.
```python
    # === 4. 执行回测 ===
    print("\n===== 开始调用回测框架 =====")
    run_backtest(args)
```

- [ ] **Step 3: Test the CLI help message to verify syntax**
Run: `python /workspace/qlib_premium_value_strategy.py -h`
Expected: Outputs the help message with arguments like `--prompt`, `--trade_file`, `--project_root`, etc.

- [ ] **Step 4: Commit**
```bash
git add qlib_premium_value_strategy.py
git commit -m "feat: append automated backtesting logic to the end of the strategy pipeline"
```