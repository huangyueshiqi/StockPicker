# 策略配置文件编写指南

## 概述

策略配置文件是用于定义量化选股策略的JSON格式文件，它包含了策略的基本信息、全局参数、筛选条件、排序方法和权重分配方式等组件。通过编写配置文件，无需修改代码即可定义和调整不同的选股策略。

## 文件结构

策略配置文件使用JSON格式，主要包含以下几个部分：

```json
{
  "name": "策略名称",
  "description": "策略描述",
  "global_params": {
    // 全局参数配置
  },
  "filters": [
    // 筛选条件列表
  ],
  "ranking": {
    // 排序方法配置
  },
  "weight_allocation": {
    // 权重分配方法配置
  }
}
```

## 各部分详细说明

### 1. 基本信息(可以省略不写)

- `name`: 策略名称
- `description`: 策略描述，简要说明策略的投资逻辑

### 2. 全局参数 (global_params)

全局参数定义了策略的基本设置，常见参数包括：

```json
"global_params": {
  "top_K": 20,               // 每个调仓日选取的股票数量
  "start_date": "20200427",  // 回测开始日期
  "end_date": "20210425",    // 回测结束日期
  "rebalance_period": 60,    // 调仓周期（以交易日为单位）
  "folder_name": "strategy_name" // 因子计算文件保存的文件夹名
}
```

### 3. 筛选条件 (filters)

筛选条件定义了选股的各项标准，系统支持多种类型的筛选条件：

#### 3.1 简单筛选条件 (simple)

基于单一指标的比较筛选：

```json
{
  "type": "simple",
  "name": "流动性良好",
  "column": "S_FA_CURRENT",
  "operator": ">",
  "threshold": 1.5,
  "description": "流动比率>1.5"
}
```

- `type`: 条件类型，值为"simple"
- `name`: 条件名称
- `column`: 要筛选的指标列名（需要与factor.csv中的英文名保持一致）
- `operator`: 比较运算符，支持">", "<", ">=", "<=", "==", "!="
- `threshold`: 阈值
- `description`: 条件描述

#### 3.2 区间筛选条件 (range)

筛选指定指标在特定区间内的股票：

```json
{
  "type": "range",
  "name": "市值",
  "column": "S_VAL_MV",
  "min_value": 1000000000,
  "max_value": 10000000000,
  "include_min": true,
  "include_max": true,
  "description": "市值在10亿到100亿之间"
}
```

- `type`: 条件类型，值为"range"
- `min_value`: 区间最小值
- `max_value`: 区间最大值
- `include_min`: 是否包含区间最小值
- `include_max`: 是否包含区间最大值

#### 3.3 排名筛选条件 (rank)

基于指标在全市场或行业内的排名进行筛选：

```json
{
  "type": "rank",
  "name": "行业低估值",
  "column": "S_VAL_PB_NEW",
  "operator": "<=",
  "threshold": 0.3,
  "rank_type": "percentile",
  "scope": "industry",
  "industry_column": "NAME",
  "ascending": true,
  "description": "筛选行业内PB在前30%的股票"
}
```

- `type`: 条件类型，值为"rank"
- `rank_type`: 排名类型，"absolute"为绝对排名，"percentile"为百分位排名，是配套出现的，后面类似
- `scope`: 排名范围，"market"为全市场，"industry"为行业内，是配套出现的，后面类似
- `industry_column`: 行业列名，scope为"industry"时必填，统一为"NAME"，是配套出现的，后面类似
- `ascending`: 排序方向，true表示从小到大排序(值越小排名越靠前,对应排名值越小)

#### 3.4 排名区间筛选条件 (rank_range)

筛选指标排名在特定区间内的股票：

```json
{
  "type": "rank_range",
  "name": "中等市值",
  "column": "S_VAL_MV",
  "min_value": 0.3,
  "max_value": 0.7,
  "rank_type": "percentile",
  "scope": "market",
  "ascending": true,
  "description": "筛选市值在市场30%到70%之间的股票"
}
```
值含义与上面类似

### 4. 排序方法 (ranking)

定义如何对通过筛选的股票进行排序：

#### 4.1 简单排序方法 (simple)

基于单一指标进行排序：

```json
"ranking": {
  "method": "simple",
  "name": "ROE排序",
  "column": "S_FA_ROE",
  "ascending": false,
  "scope": "market",
  "weight": 1.0,
  "description": "按ROE从高到低排序"
}
```
- `weight`: 权重，值需要在0-1之间。排序结果最后乘权重


#### 4.2 多因子简单排序方法 (multi_simple)

基于多个指标的加权排序：

```json
"ranking": {
  "method": "multi_simple",
  "name": "多因子综合排序",
  "description": "结合盈利和成长性的多重简单排序",
  "components": [
    {
      "name": "市净率排序",
      "column": "S_VAL_PB_NEW",
      "ascending": true,
      "scope": "industry",
      "industry_column": "NAME",
      "weight": 1,
      "description": "行业内市净率越低越好"
    },
    {
      "name": "ROE排序",
      "column": "S_FA_ROE",
      "ascending": false,
      "scope": "market",
      "weight": 1,
      "description": "ROE越高越好"
    }
  ]
}
```

- `method`: 排序方法类型，值为"multi_simple"
- `components`: 组成多因子排序的各个单因子排序方法列表

### 5. 权重分配 (weight_allocation)

定义如何为选出的股票分配权重：

#### 5.1 等权重分配方法 (equal)

为所有股票分配相同权重：

```json
"weight_allocation": {
  "type": "equal",
  "name": "等权重分配",
  "description": "为所有股票分配相等权重"
}
```


## 使用方法与内部逻辑

1. 在`config`目录下创建你的策略配置文件，扩展名为`.json`
2. 使用`StrategyConfigLoader`加载配置文件
3. 使用`StrategyFactory`创建策略组件
4. 运行策略回测

