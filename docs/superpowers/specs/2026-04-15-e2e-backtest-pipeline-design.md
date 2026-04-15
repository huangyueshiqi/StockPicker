# Qlib Premium Value Strategy End-to-End Integration Design

## Overview
This design details the integration of the natural language prompt input, LLM strategy generation, Qlib data pipeline stock selection, and the automated backtest execution into a single, cohesive end-to-end pipeline. The primary entry point will be `qlib_premium_value_strategy.py`.

## Requirements
1. Allow the user to input a strategy prompt via command-line arguments (`--prompt`) or interactive input.
2. Generate the JSON strategy config and `mapping_result.json` via `LLMStrategyGenerator`.
3. Execute the strategy using `QlibPremiumValueStrategy` to generate the rebalance table CSV (`qlib_premium_value_strategy_result.csv`).
4. Append the provided backtesting script logic to the end of the pipeline.
5. The backtest script should read the generated CSV, infer the `start_date` and `end_date`, configure the `BacktestManager`, and run the backtest, ultimately generating a performance plot.

## Architecture & Data Flow
1. **CLI Argument Parsing**: 
   - `argparse` will be introduced in `qlib_premium_value_strategy.py`.
   - Supported arguments: `--prompt`, `--trade_file`, `--output`, `--plot_output`, `--plot_trades`, `--verbose`, `--project_root`.
2. **Phase A: LLM Strategy Generation**:
   - If `--prompt` is provided (or gathered interactively), it will be passed to `generator.generate_strategy(prompt)`.
3. **Phase B: Stock Selection**:
   - The strategy is initialized and `strategy.run()` is executed.
   - The result is saved using `strategy.save_results()` to the path specified by `--trade_file`.
4. **Phase C: Backtesting**:
   - A new function `run_backtest(args)` will be defined, containing the user's provided backtest logic.
   - The function will read the `--trade_file` CSV, infer `start_date` and `end_date` by finding the min/max dates and adding a 30-day buffer to `end_date`.
   - The `config.update_strategy_params()` will be called with the inferred dates and static params (`deal_dividend=False`, `save_state=False`, `adjust_freq='D'`, `is_predict=False`).
   - `BacktestManager().run_llm_backtest()` will be invoked to generate the plot at `--plot_output`.

## Error Handling
- If the `trade_file` does not exist after Phase B, Phase C will log an error and exit.
- If the `trade_file` lacks a `date` or `datetime` column, the script will log an error and exit.
- Exceptions during reading the trade list or executing the backtest will be caught and logged via the `logging` module.

## Dependencies
- Standard library: `os`, `json`, `pandas`, `logging`, `sys`, `argparse`, `time`.
- External modules: `main.BacktestManager`, `utils.config.config` (assumed to be available in the provided `project_root`).