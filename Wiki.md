# QuantStockPicker 项目 Code Wiki

## 1. 项目概述与整体架构

**QuantStockPicker** 是一个基于 Python 的量化选股系统。该系统采用高度模块化、组件化和数据驱动的设计，主要支持基于 JSON/YAML 配置文件的策略回测与选股。

### 1.1 核心执行流程
系统的核心基于流水线（Pipeline）模式，单次调仓周期的完整执行流程被抽象为 5 个标准化步骤：
1. **数据读取 (Data Reader)**：连接 Oracle 数据库、加载动态因子数据，返回原始数据字典。
2. **数据预处理 (Data Processor)**：清洗数据，如去重、处理 NaN 值等。
3. **股票初步筛选 (Stock Filter)**：基于基础属性（如上市时间等）进行初步股票池过滤。
4. **特征计算 (Feature Calculator)**：合并行情、行业分类以及各类因子数据，生成完整的特征宽表 (DataFrame)。
5. **股票选择与权重分配 (Stock Selector)**：基于配置文件定义的逻辑（简单筛选、区间筛选、各种排名、权重分配）选出最终股票并分配仓位权重。

### 1.2 架构特点
- **配置驱动**：策略逻辑（如阈值、排序方式、权重分配）从代码中解耦，通过 JSON 配置文件定义。
- **动态因子加载**：通过调用外部大模型或规则生成系统（司棋因子生成接口），动态生成并执行因子计算的 Python 脚本。
- **可扩展性**：所有的核心组件均定义了抽象基类（`abc.ABC`），新增策略只需继承并实现对应的组件方法即可。

---

## 2. 主要模块职责

### 2.1 配置层 (`config/`)
- **`*.json` / `*.yaml`**: 策略配置文件（如 `premium_value_strategy.json`），定义选股过滤条件、排序逻辑、持仓权重及调仓参数等。
- **`factor.csv`**: 因子信息表，定义了策略需要使用的所有因子及其计算公式/含义。

### 2.2 框架层 (`framework/`)
- **`strategy_framework.py`**: 定义了系统的骨架，包括 5 大核心组件基类（`BaseDataReader`, `BaseDataProcessor`, `BaseStockFilter`, `BaseFeatureCalculator`, `BaseStockSelector`）以及策略统筹基类 `BaseStrategy`。
- **`stock_logic_framework.py`**: 实现了核心的选股逻辑引擎，包含各种类型的筛选条件（如 `SimpleFilterCondition`, `RankFilterCondition`）、排序方法（如 `SimpleRankMethod`, `MultiSimpleRankMethod`）和权重分配器（如 `EqualWeightAllocator`），以及将它们串联起来的 `StockFilterPipeline`。
- **`strategy_config.py`**: 配置解析与工厂模块。包含 `StrategyConfigLoader`（加载 JSON/YAML）和 `StrategyFactory`（根据配置实例化对应的 Filter、Rank、Weight 对象）。
- **`configurable_strategy.py`**: 提供了 `ConfigurableStockSelector`，作为 `BaseStockSelector` 的具体实现，它内部调用配置工厂来完成动态选股逻辑。
- **`factor_loader.py`**: 负责因子的动态生成与加载计算。调用外部 `FactorCodeGenerator` 动态生成因子脚本，执行计算并合并为特征宽表。

### 2.3 工具层 (`utils/`)
- **`helpers.py`**: 提供通用的数据库查询执行函数（`execute_query`）、交易日计算逻辑（`rebalancing_day`, `rebalancing_by_period`）、数据清洗以及股票基础属性获取的辅助函数。

### 2.4 结果层 (`result/`)
- 存放动态生成的因子计算 Python 脚本（如 `result/prem_value/S_VAL_PE_TTM.py`）以及最终的策略调仓计划输出文件。

### 2.5 策略实现层 (根目录)
- **`premium_value_strategy_new.py`**: 官方提供的一个基于新框架实现的“优质价值策略”实例，演示了如何组装上述框架组件。
- **`write_factorinfo.ipynb`**: 用于编写和生成 `factor.csv` 的 Jupyter 辅助脚本。

---

## 3. 关键类与函数说明

### 3.1 `framework.strategy_framework.BaseStrategy`
- **职责**：策略流程的总控制器。
- **核心方法 `run()`**：
  - 根据指定的开始、结束日期和调仓周期计算所有调仓日。
  - 遍历每个调仓日，依次调用注入的 Reader -> Processor -> Filter -> FeatureCalculator -> Selector。
  - 将每个调仓日的选股结果汇总，最终通过 `_generate_rebalance_table` 返回完整的调仓计划 DataFrame。

### 3.2 `framework.stock_logic_framework.StockFilterPipeline`
- **职责**：执行配置中定义的股票筛选与排序逻辑。
- **核心方法 `run(data, top_k)`**：
  - 遍历所有的 `FilterCondition` 求交集，剔除不符合条件的股票。
  - 应用 `RankMethod` 对剩余股票打分排序，并截取前 `top_k`。
  - 交由 `WeightAllocator` 给选出的股票分配仓位权重。

### 3.3 `framework.strategy_config.StrategyFactory`
- **职责**：基于配置的反射工厂。
- **核心方法 `create_filter_pipeline()`**：
  - 读取解析好的配置字典，根据 `type` 字段（如 `simple`, `rank`, `range`）实例化对应的 FilterCondition 和 RankMethod。
  - 组装并返回一个可执行的 `StockFilterPipeline` 对象。

### 3.4 `framework.factor_loader.FactorLoader`
- **职责**：自动化管理因子的生成与加载。
- **核心方法 `load_and_calculate(date)`**：
  - 加载 `factor.csv` 列表。
  - 若因子脚本不存在，则调用大模型代码生成器（`FactorCodeGenerator`）生成计算代码。
  - 动态导入生成的 Python 模块并计算特定日期的因子数据。
  - 最终合并所有因子为一张带有 `S_INFO_WINDCODE` 和 `TRADE_DT` 的宽表 DataFrame。

### 3.5 `PremiumValueStrategy` (位于 `premium_value_strategy_new.py`)
- **职责**：具体的策略实现入口。
- **工作机制**：实例化具体的 Reader/Processor 等类，并在 Selector 中传入 `ConfigurableStockSelector`（挂载 `premium_value_strategy.json` 配置），最后调用 `BaseStrategy.run()` 启动回测。

---

## 4. 依赖关系

### 4.1 内部依赖
- `ConfigurableStockSelector` 强依赖 `StrategyFactory` 和 `StockFilterPipeline`。
- `PremiumValueDataReader` 强依赖 `FactorLoader` 提供因子数据。

### 4.2 外部库依赖
- **核心数据处理**：`pandas`, `numpy`
- **配置与系统工具**：`json`, `yaml`, `os`, `sys`, `importlib`
- **数据库连接**：`cx_Oracle` (需系统环境变量支持)
- **特定外部接口**：系统高度依赖位于外部路径（如 `/home/quant/wsq/wsq/langchain_test/refactor`）的 `FactorCodeGenerator` 来实现因子的动态生成。

---

## 5. 项目运行方式

### 5.1 环境准备
1. 确保在 57 服务器的 `zcenv` 环境下运行。
2. 配置 Oracle 客户端环境变量以避免数据库连接错误：
   ```bash
   export LD_LIBRARY_PATH=/oracle/client:/home/quant/oracle
   export ORACLE_HOME=/oracle/client
   ```
3. 在 `utils/helpers.py` 中确认 Oracle 数据库（WIND, JYLH, FINCHINA）连接配置已正确填写。

### 5.2 编写新策略
1. **生成因子文件**：使用 `write_factorinfo.ipynb` 定义因子，并生成 `config/factor.csv`。
2. **编写策略配置**：在 `config/` 下创建策略配置文件（如 `my_strategy.json`），定义 `global_params`、`filters`、`ranking` 及 `weight_allocation`。
3. **编写策略入口**：参考 `premium_value_strategy_new.py`，实现一个主文件，实例化 `BaseStrategy` 并传入 `ConfigurableStockSelector`（指向你的 JSON 文件）。

### 5.3 运行与调试
1. **启动回测**：直接运行策略入口脚本。
   ```bash
   python premium_value_strategy_new.py
   ```
2. **重算因子**：由于 `FactorLoader` 会缓存生成的因子 Python 文件。如果因子计算逻辑变更或数据报错，需要手动前往 `result/[folder_name]/` 目录下删除对应的 `.py` 文件，下次运行时系统将自动重新生成。
3. **输出**：运行结束后，策略将在当前目录输出 CSV 格式的调仓记录表（如 `premiumvaluestrategy_result.csv`）。