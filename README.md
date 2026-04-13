# QuantStockPicker - 量化选股系统

## 项目概述

QuantStockPicker是一个基于Python的量化选股框架，用于实现各种选股策略。系统采用模块化、组件化设计，支持可配置的策略执行流程，便于快速开发和测试各种量化投资策略。系统通过数据库连接获取股票市场数据，处理财务指标，然后根据策略逻辑筛选股票并生成调仓计划表。
QuantStockPicker只支持基于配置的选股，必须需要配置文件才能进行选股
## 系统架构

系统采用分层架构设计，主要包括以下几个核心模块：
### 配置层 (`config/`)
- 配置文件模板: 如`premium_value_strategy.json`,配置文件书写可参考例子或者strategy_config.py中StrategyFactory类中的方法
- 因子信息文件: 如`factor.csv`,使用`write_factorinfo.ipynb`写入因子信息文件

### 框架层 (`framework/`)
- `strategy_framework.py`: 定义策略框架的基础接口和类
- `stock_logic_framework.py`: 实现股票筛选和排序的逻辑框架
- `strategy_config.py`: 处理策略配置的加载和解析
- `configurable_strategy.py`: 提供基于配置的可配置策略实现
- `factor_loader.py`: 基于司棋因子生成接口的实现

### 工具层 (`utils/`)
- `helpers.py`: 提供各种辅助函数和工具方法

### 策略实现层
- `premium_value_strategy_old.py`: 实现优质价值策略的具体逻辑，不基于司棋因子生成接口的实现（旧）
- `premium_value_strategy_new.py`: 实现优质价值策略的具体逻辑，基于司棋因子生成接口的实现（新）

## 主要功能

### 1. 模块化策略框架
系统定义了完整的策略实现流程，将策略拆分为数据读取、数据处理、股票筛选、特征计算和股票选择这五个步骤，每个步骤都有清晰的接口定义。

### 2. 可配置的策略执行
通过JSON或YAML配置文件定义策略，无需修改代码即可调整策略参数或逻辑。

### 3. 灵活的调仓机制
支持基于周期（按交易日数量）或固定频率（每月、每季度等）的调仓机制。

### 4. 丰富的筛选条件和排名条件
1. 提供简单条件、区间范围条件、排名条件（绝对排名和百分位排名）等多种筛选方式，支持行业内和全市场筛选与排名。
2. 筛选条件：大于，小于，等于，区间，排名最大，排名最小，排名区间，排名%最大，排名%最小，排名%区间
3. 排名条件：从小到大，从大到小
### 5. 多种权重分配方法
支持等权重持仓权重分配方法。其它权重分配方法实现可能存在问题，需要手动测试验证

## 使用指南

### 环境准备
1. 57服务器上的zcenv
2. 可能遇到的问题
如果遇到cx_Oracle.DatabaseError:DPI-1047错误，运行时环境变量需要加上
```
LD_LIBRARY_PATH=/oracle/client:/home/quant/oracle ORACLE_HOME=/oracle/client
```

### 数据库配置
系统默认连接Oracle数据库，配置连接信息：
当前三个数据库全部配置完成
```python
WIND_DB = {
    'username': 'wind',
    'password': 'wind',
    'host': '10.6.60.114:1521',
    'service': 'wind'
}
```

### 使用配置文件创建策略
1. 在config文件夹创建JSON格式的策略配置文件，在使用`write_factorinfo.ipynb`写入因子信息文件，生成`factor.csv`
2. 继承strategy_framework.py中的`BaseStrategy`类并实现所需组件：
```
data_reader：写sql从数据框表中读取数据，最后返回dict
data_processor：对数据dict进行去重去空，并计算出所有指标，返回dict
stock_filter ：对dict中股票进行简单过滤，例如筛选上市时间符合条件的股票，返回符合条件的股票列表
feature_calculator：在dict和符合条件的股票列表基础上，根据数据特点合并数据为一个dataframe，最后返回包含所有指标信息的dataframe
stock_selector：基于dataframe和配置文件进行选股
```
3. 使用`ConfigurableStockSelector`配置选股器，加载配置进行选股


### 运行策略
1. premium_value_strategy_new.py
2. 运行必须设置的参数：策略选股的开始日期和结束日期;config配置路径
3. 默认参数：调仓周期(交易日天数)，默认为60天;等权重分配;结果文件路径：当前类名小写+_result.csv

## 示例策略
项目中包含一个完整的优质价值策略实现(`premium_value_strategy_new.py`)，可以作为开发新策略的参考。
1. 使用`write_factorinfo.ipynb`写入因子信息文件，生成`factor.csv`
2. 写`premium_value_strategy.json`，json中`name`和`description`可不写
3. 策略py文件中的main函数上需要`factor_filename`和`config_filename`这两个文件名

### 注意点
1. 生成的因子计算文件，在调仓日运行时如果没有值，说明生成的文件有问题，就需要重新生成
2. 重新生成因子计算文件，需要先在`result/prem_value`文件夹删除对应的因子计算文件，然后重新运行程序即可

### 配置文件书写


