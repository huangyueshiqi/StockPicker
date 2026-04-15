# QuantBacktester - 量化回测系统代码 Wiki

## 1. 项目简介
**QuantBacktester** 是一个基于 Python 和 `backtrader` 框架开发的完整量化投资回测系统。它不仅支持传统的选股策略回测，还提供了丰富的高级功能，如：多资产配置与 CVXPY 凸优化、增量回测、分红/拆股/送股处理、ST股票过滤、调仓计划执行以及详细的收益与风险分析。

## 2. 整体架构
项目按照功能模块化设计，主要分为核心逻辑层、数据处理层、工具类层和主入口层：

```text
QuantBacktester/
├── core/                 # 核心业务逻辑（策略、交易执行、资产组合管理等）
├── data/                 # 数据处理与加载（Oracle数据库对接、数据清洗）
├── utils/                # 工具函数与全局配置（CVXPY优化、图表绘制、辅助函数）
├── llm/                  # 基于大模型策略的相关模块
├── main.py               # 项目主入口，解析命令行参数并启动回测
├── input/                # 调仓表、股票池、预测数据等输入目录
├── result/               # 收益与指标分析结果目录
├── state/                # 增量回测的状态保存目录
└── plot/                 # 策略净值图表输出目录
```

## 3. 主要模块职责

### 3.1 `core/` 核心模块
*   **`strategy.py` / `topk_strategy.py` / `index_strategy.py` / `buy_strategy.py` / `llm_strategy.py`**：各类交易策略的实现。继承自 `bt.Strategy`，定义了每个 Bar 的具体交易逻辑、风控逻辑及调仓逻辑。
*   **`trade_executor.py`**：交易执行器，封装了具体的买入（`to_buy`）、卖出（`to_sell`）、ST股票清仓和根据目标权重进行再平衡（`rebalance_portfolio`）的底层 API。
*   **`portfolio.py`**：投资组合优化器模块。定义了抽象基类 `PortfolioOptimizer`，并实现了 `CvxPortfolioOptimizer`（基于 CVXPY 的凸优化求解最优权重）、`EqualWeightOptimizer`（等权重分配）等。
*   **`position.py`**：仓位管理器（`Position`, `Portfolio`），采用 FIFO（先进先出）原则管理每只股票的买入批次和规模，用于准确计算持仓天数与收益。
*   **`constraint_manager.py`**：约束管理器。包含多种交易约束条件的实现（如：ST股票限制、连续涨跌停限制、最小持有期、市值阈值过滤等）。
*   **`dividend_handler.py`**：除权除息处理器。在每个交易日自动处理现金分红（是否填权）、送股和拆股，并计算相应的红利税。
*   **`state_manager.py`**：增量回测状态管理器。负责保存当前的资金、持仓、分红税等状态（序列化为 pickle 和 json），以及在下一次增量回测时恢复这些状态。
*   **`analyzer.py` & `benchmark_calculator.py`**：自定义回测指标分析器，计算年化收益、夏普比率、最大回撤、胜率等，并与基准指数（如沪深300）对齐对比。

### 3.2 `data/` 数据模块
*   **`loader.py`**：包含 `BaseDataLoader`（抽象加载器）、`OracleDataLoader`（从 cx_Oracle 读取数据）、`StockDataService`（整合基础数据服务）和 `DataPreprocessor`（数据预处理与特征清洗）。

### 3.3 `utils/` 工具模块
*   **`config.py`**：基于 Python `dataclass` 实现的全局配置管理类 `Config`，整合了数据库连接、回测参数、优化器参数、路径设置等。
*   **`helpers.py`**：核心工具集，包含了基于 `cvxpy` 的资产权重计算函数（`cvxopt`）、交易日历计算、回测指标计算（`empyrical` 封装）、Matplotlib 绘图（`plot_strategy_data`）等重要辅助功能。

## 4. 关键类与函数说明

*   **`BacktestManager` ([main.py](file:///workspace/QuantBacktester/main.py#L104-L109))**
    *   **职责**：系统核心调度器。负责初始化环境、加载数据、配置 `backtrader` 的 `Cerebro` 引擎，并启动对应模式的回测。
    *   **核心方法**：`run_full_backtest()`, `run_incremental_backtest()`, `run_topk_backtest()`, `run_rebalanceTable_backtest()`。

*   **`AlphaStrategy` ([core/strategy.py](file:///workspace/QuantBacktester/core/strategy.py#L17-L430))**
    *   **职责**：基于打分（Score/Alpha）的选股策略。支持与 CVXPY 优化器结合。
    *   **核心方法**：
        *   `next()`：主循环，处理 ST 股卖出、分红逻辑、并在调仓日触发 `cvxopt` 优化和 `trade_executor.rebalance_portfolio`。
        *   `notify_order()`：记录订单状态、建仓/平仓细节及红利扣税处理。

*   **`CvxPortfolioOptimizer` ([core/portfolio.py](file:///workspace/QuantBacktester/core/portfolio.py#L42-L200))**
    *   **职责**：利用 `cvxpy` 解决带有约束条件的凸优化问题，求出最大化预期收益的个股权重。
    *   **约束条件**：单票权重上限、市值暴露偏离限制、换手率约束、行业偏离等。

*   **`TradeExecutor` ([core/trade_executor.py](file:///workspace/QuantBacktester/core/trade_executor.py#L4-L200))**
    *   **职责**：分离策略与交易执行。
    *   **核心方法**：`rebalance_portfolio(cur_date, weights, dict_weights_raw)`。根据当前历史权重与目标权重的差值，按优先卖出释放资金、再买入的顺序执行调仓。

*   **`StateManager` ([core/state_manager.py](file:///workspace/QuantBacktester/core/state_manager.py#L13))**
    *   **职责**：实现系统的**增量回测**功能。解决长周期回测内存不足或需接续昨日状态的问题。
    *   **核心方法**：`save_state()`（持久化当前资产、持仓到磁盘），`restore_state()`（从磁盘加载并还原 `Portfolio`）。

## 5. 依赖关系

系统核心依赖以下 Python 库：
*   **`backtrader`**：量化回测基础框架。
*   **`pandas` / `numpy`**：时间序列数据处理与向量化计算。
*   **`cvxpy`**：凸优化求解器（用于计算最优调仓权重）。
*   **`matplotlib`**：回测净值曲线、收益柱状图绘制。
*   **`empyrical`**：计算各种风险收益指标（夏普比率、回撤等）。
*   **`cx_Oracle`**：连接 Oracle 数据库，提取股票量价和基础数据。

## 6. 项目运行方式

通过 `main.py` 作为统一入口，通过命令行参数指定回测模式：

### 基础命令格式
```bash
python main.py --mode <回测模式> [其他参数]
```

### 回测模式 (`--mode`) 支持选项
1.  `full`：全量 Alpha 分数回测（默认优化器调仓）。
2.  `topk`：基于预测分数的 Top-K 选股回测。
3.  `incremental`：增量回测模式（按月或分段执行并保存状态）。
4.  `rebalanceTable`：根据外部传入的 CSV 调仓表文件执行等权回测。
5.  `index_rebalanceTable`：基于指数成分股的外部调仓表回测。
6.  `buy`：根据固定买入列表文件进行回测。
7.  `llm`：基于大模型生成的交易信号进行回测。

### 常用参数说明
*   `--predict`：预测分数（Alpha score）文件路径（如 `input/prediction_results.csv`）。
*   `--pool`：股票池文件路径（限制交易的标的范围）。
*   `--rebalance_file` / `--index_rebalance_file`：调仓计划表文件路径。
*   `--plot_output`：指定策略净值和回撤图表的输出路径（默认 `plot/strategy_plot.png`）。
*   `--verbose`：开启详细日志输出，打印每个订单和调仓细节。

**示例**：运行基于调仓表的等权回测并输出详细日志
```bash
python main.py --mode rebalanceTable --rebalance_file ./input/25071501trade_log.csv --verbose
```
