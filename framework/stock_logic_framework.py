import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any, Optional, Union, Callable

class FilterCondition:
    """
    筛选条件基类
    """
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
    
    def apply(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        应用筛选条件
        
        参数:
            data: 输入数据
            
        返回:
            筛选后的数据
        """
        raise NotImplementedError("子类必须实现apply方法")


class SimpleFilterCondition(FilterCondition):
    """
    简单筛选条件，基于单列比较
    """
    def __init__(self, name: str, column: str, operator: str, threshold: float, description: str = ""):
        """
        初始化简单筛选条件
        
        参数:
            name: 条件名称
            column: 列名
            operator: 比较运算符 ('>', '<', '>=', '<=', '==', '!=')
            threshold: 阈值
            description: 条件描述
        """
        super().__init__(name, description)
        self.column = column
        self.operator = operator
        self.threshold = threshold
        
    def apply(self, data: pd.DataFrame) -> pd.DataFrame:
        """应用筛选条件"""
        if self.column not in data.columns:
            print(f"警告: 列 '{self.column}' 不存在于数据中")
            return data
        
        if self.operator == '>':
            return data[data[self.column] > self.threshold]
        elif self.operator == '<':
            return data[data[self.column] < self.threshold]
        elif self.operator == '>=':
            return data[data[self.column] >= self.threshold]
        elif self.operator == '<=':
            return data[data[self.column] <= self.threshold]
        elif self.operator == '==':
            return data[data[self.column] == self.threshold]
        elif self.operator == '!=':
            return data[data[self.column] != self.threshold]
        else:
            raise ValueError(f"不支持的运算符: {self.operator}")


class RangeFilterCondition(FilterCondition):
    """
    区间筛选条件，筛选指定区间内的数值
    """
    def __init__(self, name: str, column: str, min_value: float, max_value: float,
                 include_min: bool = True, include_max: bool = True, description: str = ""):
        """
        初始化区间筛选条件

        参数:
            name: 条件名称
            column: 列名
            min_value: 最大值
            max_value: 最小值
            include_min: 是否包含最小值,True为>=,False为>
            include_max: 是否包含最大值,True为<=,False为<
            description: 条件描述
        """
        super().__init__(name, description)
        self.column = column
        self.min_value = min_value
        self.max_value = max_value
        self.include_min = include_min
        self.include_max = include_max

    def apply(self, data: pd.DataFrame) -> pd.DataFrame:
        """应用筛选条件"""
        if self.column not in data.columns:
            print(f"警告: 列 '{self.column}' 不存在于数据中")
            return data

        # 根据是否包含边界选择比较运算符
        min_op='>=' if self.include_min else '>'
        max_op = '<=' if self.include_max else '<'

        #筛选指定区间内的数据
        if min_op == '>=':
            min_filter=data[self.column]>=self.min_value
        else:
            min_filter=data[self.column]>self.min_value

        if max_op == '<=':
            max_filter=data[self.column]<=self.max_value
        else:
            max_filter=data[self.column]<self.max_value

        return data[min_filter&max_filter]


class RankFilterCondition(FilterCondition):
    """
    排名筛选条件，可以在全市场或行业内按指标排名筛选
    支持绝对排名和百分位排名两种模式
    """

    def __init__(self, name: str, column: str, operator: str, threshold: Union[int, float],
                 rank_type: str = "absolute", scope: str = "market", industry_column: str = None,
                 ascending: bool = False, description: str = ""):
        """
        初始化行业内排名筛选条件

        参数:
            name: 条件名称
            column: 目标列名
            operator: 比较运算符('>','<','>=','<=','==','!=')
            threshold: 阈值(排名数值或百分位值)
            rank_type: 排名类型，"absolute"为绝对排名，"percentile"为百分位排名
            scope: 排名范围,"market"为全市场,"industry"为行业内
            industry_column: 行业列名(scope为"industry"时必须提供)
            ascending: 排序方向，True表示从小到大排序(值越小排名越靠前,对应排名值越小)，False表示从大到小排序(值越大排名越高)
            description: 条件描述
        """
        super().__init__(name, description)
        self.column = column
        self.operator = operator
        self.threshold = threshold
        self.rank_type = rank_type
        self.scope = scope
        self.industry_column = industry_column
        self.ascending = ascending

        #验证参数
        if self.scope == "industry" and not self.industry_column:
            raise ValueError("当scope为'industry'时, 必须提供industry_column参数")

    def apply(self, data: pd.DataFrame) -> pd.DataFrame:
        """应用筛选条件"""
        if self.column not in data.columns:
            print(f"警告: 列 '{self.column}' 不存在于数据中")
            return data
        if self.scope == "industry" and self.industry_column not in data.columns:
            print(f"警告: 行业列 '{self.industry_column}' 不存在于数据中")
            return data

        # 创建新DataFrame以避免修改原始数据
        result = data.copy()

        # 根据排名范围和类型计算排名
        if self.scope == "market":
            #全市场排名
            if self.rank_type == "absolute":
                rank_column = f"{self.column}_market_rank"
                result[rank_column] = result[self.column].rank(method='min', ascending=self.ascending)
            elif self.rank_type == "percentile":
                rank_column = f"{self.column}_market_percentile"
                result[rank_column] = result[self.column].rank(method='min', pct=True, ascending=self.ascending)
            else:
                raise ValueError(f'不支持的排名类型:{self.rank_type}')
        else:
            #行业内排名
            if self.rank_type == "absolute":
                rank_column = f"{self.column}_industry_rank"
                result[rank_column] = result.groupby(self.industry_column)[self.column].rank(
                    method='min', ascending=self.ascending
                )
            elif self.rank_type == "percentile":
                rank_column = f"{self.column}_industry_percentile"
                result[rank_column] = result.groupby(self.industry_column)[self.column].rank(
                    method='min', pct=True, ascending=self.ascending
                ) #0-1的小数，表示该股票在全部股票中的相对位置，ascending为True时，低值对应低百分位值
            else:
                raise ValueError(f'不支持的排名类型:{self.rank_type}')


        # 应用筛选条件
        if self.operator == '>':
            return result[result[rank_column] > self.threshold]
        elif self.operator == '<':
            return result[result[rank_column] < self.threshold]
        elif self.operator == '>=':
            return result[result[rank_column] >= self.threshold]
        elif self.operator == '<=':
            return result[result[rank_column] <= self.threshold]
        elif self.operator == '==':
            return result[result[rank_column] == self.threshold]
        elif self.operator == '!=':
            return result[result[rank_column] != self.threshold]
        else:
            raise ValueError(f'不支持的运算符: {self.operator}')



class RankRangeFilterCondition(FilterCondition):
    """
    排名区间筛选条件，可以在全市场或行业内筛选指定排名区间的股票
    支持绝对排名和百分位排名两种模式
    """

    def __init__(self, name: str, column: str, min_value: Union[int,float],max_value: Union[int,float],
                 rank_type:str="absolute", scope: str = "market",industry_column: str = None,
                 ascending: bool = False, description: str = ""):
        """
        初始化行业内排名区间筛选条件

        参数:
            name: 条件名称
            column: 目标列名
            min_value: 最小排名或百分位(包含)
            max_value: 最大排名或百分位(包含)
            rank_type: 排名类型，"absolute"为绝对排名，"percentile"为百分位排名
            scope: 排名范围,"market"为全市场,"industry"为行业内
            industry_column: 行业列名(scope为"industry"时必须提供)
            ascending: 排序方向，True表示从小到大排序(值越小排名越高)，False表示从大到小排序(值越大排名越高)
            description: 条件描述
        """
        super().__init__(name, description)
        self.column = column
        self.min_value = min_value
        self.max_value = max_value
        self.rank_type = rank_type
        self.scope = scope
        self.industry_column = industry_column
        self.ascending = ascending

        # 验证参数
        if self.scope == "industry" and not self.industry_column:
            raise ValueError("当scope为'industry'时, 必须提供industry_column参数")

    def apply(self, data: pd.DataFrame) -> pd.DataFrame:
        """应用筛选条件"""
        if self.column not in data.columns:
            print(f"警告: 列 '{self.column}' 不存在于数据中")
            return data
        if self.scope == "industry" and self.industry_column not in data.columns:
            print(f"警告: 行业列 '{self.industry_column}' 不存在于数据中")
            return data

        # 创建新DataFrame以避免修改原始数据
        result=data.copy()

        # 根据排名类型选择计算方法
        if self.scope == "market":
            # 全市场排名
            if self.rank_type == "absolute":
                rank_column=f"{self.column}_market_rank"
                result[rank_column]=result[self.column].rank(method='min',ascending=self.ascending)
            elif self.rank_type == "percentile":
                rank_column=f"{self.column}_market_percentile"
                result[rank_column]=result[self.column].rank(method='min', pct=True, ascending=self.ascending)
            else:
                raise ValueError(f'不支持的排名类型:{self.rank_type}')
        else:
            # 行业内排名
            if self.rank_type == "absolute":
                rank_column=f"{self.column}_industry_rank"
                result[rank_column]=result.groupby(self.industry_column)[self.column].rank(
                    method='min',ascending=self.ascending
                )
            elif self.rank_type == "percentile":
                rank_column=f"{self.column}_industry_percentile"
                result[rank_column]=result.groupby(self.industry_column)[self.column].rank(
                    method='min', pct=True, ascending=self.ascending
                )
            else:
                raise ValueError(f'不支持的排名类型:{self.rank_type}')

        #筛选排名在指定区间内的股票
        return result[(result[rank_column]>=self.min_value)&(result[rank_column]<=self.max_value)]



class CustomFilterCondition(FilterCondition):
    """
    自定义筛选条件，使用自定义函数
    """
    def __init__(self, name: str, filter_func: Callable[[pd.DataFrame], pd.DataFrame], description: str = ""):
        """
        初始化自定义筛选条件
        
        参数:
            name: 条件名称
            filter_func: 自定义筛选函数，接受DataFrame，返回筛选后的DataFrame
            description: 条件描述
        """
        super().__init__(name, description)
        self.filter_func = filter_func
        
    def apply(self, data: pd.DataFrame) -> pd.DataFrame:
        """应用筛选条件"""
        return self.filter_func(data)


class RankMethod:
    """
    排序方法基类
    """
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
    
    def apply(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        应用排序方法
        
        参数:
            data: 输入数据
            
        返回:
            包含排名的数据
        """
        raise NotImplementedError("子类必须实现apply方法")


class SimpleRankMethod(RankMethod):
    """
    简单排序方法，基于单一指标
    """
    def __init__(self, name: str, column: str, ascending: bool = True,
                 scope: str = "market", industry_column: str =None,
                 weight: float = 1.0, description: str = ""):
        """
        初始化简单排序方法
        
        参数:
            name: 方法名称
            column: 用于排序的列
            ascending: 是否升序，True表示值越小排名越高
            scope: 排名范围, "market"为全市场， "industry"为行业内
            industry_column: 行业列名(scope为"industry"时必须提供)
            weight: 排序权重，范围为0-1，默认为1
            description: 方法描述
        """
        super().__init__(name, description)
        self.column = column
        self.ascending = ascending
        self.scope = scope
        self.industry_column = industry_column
        self.weight = max(0,min(1,weight)) #确保权重在0-1之间

        # 验证参数
        if self.scope == "industry" and not self.industry_column:
            raise ValueError("当scope为'industry'时, 必须提供industry_column参数")
        
    def apply(self, data: pd.DataFrame) -> pd.DataFrame:
        """应用排序方法"""
        if self.column not in data.columns:
            print(f"警告: 列 '{self.column}' 不存在于数据中")
            return data
        if self.scope == "industry" and self.industry_column not in data.columns:
            print(f"警告: 行业列 '{self.industry_column}' 不存在于数据中")
            return data

        # 创建排名列名
        if self.scope == "market":
            rank_column = f"{self.column}_rank"
            # 计算全市场排名
            data[rank_column] = data[self.column].rank(method='min', ascending=self.ascending)*self.weight
        else:
            # 行业内排名
            rank_column = f"{self.column}_industry_rank"
            data[rank_column] = data.groupby(self.industry_column)[self.column].rank(
                method='min', ascending=self.ascending
            ) * self.weight
        
        return data


class MultiSimpleRankMethod(RankMethod):
    """
    多重简单排序方法，组合多个SimpleRankMethod
    """
    def __init__(self, name: str, rank_methods: List[SimpleRankMethod], description: str = ""):
        """
        初始化多重简单排序方法
        
        参数:
            name: 方法名称
            rank_methods: SimpleRankMethod对象列表
            description: 方法描述
        """
        super().__init__(name, description)
        self.rank_methods = rank_methods
        
    def apply(self, data: pd.DataFrame) -> pd.DataFrame:
        """应用排序方法"""
        result=data.copy()

        # 应用每个简单排序方法
        for method in self.rank_methods:
            result = method.apply(result)
        
        # 计算综合排名
        rank_columns = []
        for method in self.rank_methods:
            if method.scope == "market":
                rank_col = f"{method.column}_rank"
            else:
                rank_col = f"{method.column}_industry_rank"

            if rank_col in result.columns:
                rank_columns.append(rank_col)

        if not rank_columns:
            return result

        result['composite_rank'] = result[rank_columns].sum(axis=1)

        #对综合排名再次排序，获得最终排名(升序：值越小排名越高)
        result['final_rank'] = result['composite_rank'].rank(method='min', ascending=True)
        
        return result





class DimensionalRankMethod(RankMethod):
    """
    该方法被弃用
    多维度排序方法，先对各维度指标排序，再对维度进行加权
    """
    def __init__(self, name: str, dimension_weights: Dict[str, float], indicator_groups: Dict[str, List[str]], 
                 indicator_directions: Dict[str, bool], description: str = ""):
        """
        初始化多维度排序方法
        
        参数:
            name: 方法名称
            dimension_weights: 各维度的权重，如 {'盈利能力': 0.3, '成长能力': 0.2}
            indicator_groups: 各维度下的指标，如 {'盈利能力': ['ROE', 'ROA']}
            indicator_directions: 各指标的排序方向，True表示升序（值越大排名越低）
            description: 方法描述
        """
        super().__init__(name, description)
        self.dimension_weights = dimension_weights
        self.indicator_groups = indicator_groups
        self.indicator_directions = indicator_directions
        
    def apply(self, data: pd.DataFrame) -> pd.DataFrame:
        """应用排序方法"""
        result = data.copy()
        
        # 检查所有指标是否存在
        all_indicators = []
        for group in self.indicator_groups.values():
            all_indicators.extend(group)
        
        for indicator in all_indicators:
            if indicator not in data.columns:
                print(f"警告: 列 '{indicator}' 不存在于数据中")
                return data
            if indicator not in self.indicator_directions:
                print(f"警告: 指标 '{indicator}' 的排序方向未定义")
                return data
        
        # 计算各指标排名
        for indicator in all_indicators:
            ascending =  self.indicator_directions[indicator]
            result[f"{indicator}_rank"] = result[indicator].rank(method='min', ascending=ascending,pct=True)

        # 按股票代码分组，计算各指标排名的均值(代表长期表现)
        stock_ranks = result.groupby('S_INFO_WINDCODE')[[f'{ind}_rank' for ind in self.indicator_directions.keys()]].mean().reset_index()

        # 计算各维度得分
        for dimension, indicators in self.indicator_groups.items():
            rank_columns = [f"{indicator}_rank" for indicator in indicators]
            stock_ranks[f"{dimension}_score"] = stock_ranks[rank_columns].mean(axis=1)
        
        # 加权综合得分
        stock_ranks['composite_score'] = 0
        for dimension, weight in self.dimension_weights.items():
            stock_ranks['composite_score'] += stock_ranks[f"{dimension}_score"] * weight
        
        return stock_ranks


class WeightAllocator:
    """
    权重分配器基类
    """
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
    
    def allocate(self, data: pd.DataFrame, stock_column: str) -> pd.DataFrame:
        """
        分配权重
        
        参数:
            data: 输入数据
            stock_column: 股票代码列名
            
        返回:
            包含权重的DataFrame
        """
        raise NotImplementedError("子类必须实现allocate方法")


class EqualWeightAllocator(WeightAllocator):
    """
    等权重分配器
    """
    def __init__(self, name: str = "等权重分配", description: str = "为所有股票分配相同权重"):
        super().__init__(name, description)
    
    def allocate(self, data: pd.DataFrame, stock_column: str) -> pd.DataFrame:
        """分配等权重"""
        result = data.copy()
        n_stocks = len(result)
        
        if n_stocks == 0:
            return result
        
        result['weight'] = 1.0 / n_stocks
        return result


class MarketCapWeightAllocator(WeightAllocator):
    """
    待修改，当前实现可能存在问题，需要手动测试验证
    市值加权分配器
    """
    def __init__(self, market_cap_column: str, name: str = "市值加权分配", 
                 description: str = "按市值比例分配权重", cap_weight: bool = True):
        """
        初始化市值加权分配器
        
        参数:
            market_cap_column: 市值列名
            name: 方法名称
            description: 方法描述
            cap_weight: 是否限制权重上限
        """
        super().__init__(name, description)
        self.market_cap_column = market_cap_column
        self.cap_weight = cap_weight
    
    def allocate(self, data: pd.DataFrame, stock_column: str) -> pd.DataFrame:
        """按市值分配权重"""
        result = data.copy()
        
        if len(result) == 0 or self.market_cap_column not in result.columns:
            print(f"警告: 列 '{self.market_cap_column}' 不存在于数据中或数据为空")
            return result
        
        # 计算总市值
        total_market_cap = result[self.market_cap_column].sum()
        
        if total_market_cap == 0:
            print("警告: 总市值为0，无法进行市值加权")
            result['weight'] = 1.0 / len(result)
            return result
        
        # 计算初始权重
        result['weight'] = result[self.market_cap_column] / total_market_cap
        
        # 如果需要限制权重上限（通常为10%）
        if self.cap_weight:
            max_weight = 0.1  # 10%上限
            
            # 迭代处理，直到所有权重都不超过上限
            while result['weight'].max() > max_weight:
                # 找出超过上限的股票
                over_limit = result[result['weight'] > max_weight]
                
                # 将超过上限的权重设为上限
                excess_weight = over_limit['weight'].sum() - (len(over_limit) * max_weight)
                result.loc[result['weight'] > max_weight, 'weight'] = max_weight
                
                # 将超出的权重按比例分配给其他股票
                under_limit = result[result['weight'] < max_weight]
                if len(under_limit) == 0:
                    break
                    
                total_under_weight = under_limit['weight'].sum()
                for idx in under_limit.index:
                    result.loc[idx, 'weight'] += (result.loc[idx, 'weight'] / total_under_weight) * excess_weight
        
        return result


class IndustryEqualWeightAllocator(WeightAllocator):
    """
    待修改，当前实现可能存在问题，需要手动测试验证
    行业等权分配器
    """
    def __init__(self, industry_column: str, name: str = "行业等权分配", 
                 description: str = "先对行业等权，再在行业内等权"):
        """
        初始化行业等权分配器
        
        参数:
            industry_column: 行业列名
            name: 方法名称
            description: 方法描述
        """
        super().__init__(name, description)
        self.industry_column = industry_column
    
    def allocate(self, data: pd.DataFrame, stock_column: str) -> pd.DataFrame:
        """按行业等权分配"""
        result = data.copy()
        
        if len(result) == 0 or self.industry_column not in result.columns:
            print(f"警告: 列 '{self.industry_column}' 不存在于数据中或数据为空")
            return result
        
        # 计算每个行业的股票数量
        industry_counts = result.groupby(self.industry_column).size()
        n_industries = len(industry_counts)
        
        if n_industries == 0:
            return result
        
        # 每个行业的权重等分
        industry_weight = 1.0 / n_industries
        
        # 在每个行业内部，股票权重等分
        for industry, count in industry_counts.items():
            stock_weight_in_industry = industry_weight / count
            result.loc[result[self.industry_column] == industry, 'weight'] = stock_weight_in_industry
        
        return result


class CustomWeightAllocator(WeightAllocator):
    """
    待修改，当前实现可能存在问题，需要手动测试验证
    自定义权重分配器
    """
    def __init__(self, weight_func: Callable[[pd.DataFrame, str], pd.DataFrame], 
                 name: str = "自定义权重分配", description: str = "使用自定义函数分配权重"):
        """
        初始化自定义权重分配器
        
        参数:
            weight_func: 自定义权重分配函数，接受DataFrame和股票列名，返回带权重列的DataFrame
            name: 方法名称
            description: 方法描述
        """
        super().__init__(name, description)
        self.weight_func = weight_func
    
    def allocate(self, data: pd.DataFrame, stock_column: str) -> pd.DataFrame:
        """使用自定义函数分配权重"""
        return self.weight_func(data, stock_column)


class FactorWeightAllocator(WeightAllocator):
    """
    待修改，当前实现可能存在问题，需要手动测试验证
    因子加权分配器
    """
    def __init__(self, factor_column: str, is_ascending: bool = False, power: float = 1.0,
                 name: str = "因子加权分配", description: str = "按因子值比例分配权重"):
        """
        初始化因子加权分配器
        
        参数:
            factor_column: 因子列名
            is_ascending: 是否因子值越小权重越大
            power: 因子值的幂，用于调整权重差异
            name: 方法名称
            description: 方法描述
        """
        super().__init__(name, description)
        self.factor_column = factor_column
        self.is_ascending = is_ascending
        self.power = power
    
    def allocate(self, data: pd.DataFrame, stock_column: str) -> pd.DataFrame:
        """按因子值分配权重"""
        result = data.copy()
        
        if len(result) == 0 or self.factor_column not in result.columns:
            print(f"警告: 列 '{self.factor_column}' 不存在于数据中或数据为空")
            return result
        
        # 确保因子值全为正数，必要时进行调整
        min_val = result[self.factor_column].min()
        if min_val <= 0:
            offset = abs(min_val) + 1  # 加1是为了避免0值
            result[self.factor_column] = result[self.factor_column] + offset
        
        # 应用幂次
        factor_values = result[self.factor_column] ** self.power
        
        if self.is_ascending:
            # 如果因子值越小权重越大，则取倒数
            factor_values = 1 / factor_values
        
        # 计算权重
        total_factor = factor_values.sum()
        if total_factor == 0:
            result['weight'] = 1.0 / len(result)
        else:
            result['weight'] = factor_values / total_factor
        
        return result


class StockFilterPipeline:
    """
    股票筛选排序流水线，将多个筛选条件和排序方法组合在一起
    """
    def __init__(self, name: str = '股票筛选流水线', description: str = ""):
        """
        初始化筛选排序流水线
        
        参数:
            name: 流水线名称
            description: 流水线描述
        """
        self.name = name
        self.description = description
        self.filter_conditions = []
        self.rank_method = None
        self.weight_allocator = EqualWeightAllocator()  # 默认使用等权重分配
        
    def add_filter_condition(self, condition: FilterCondition) -> None:
        """
        添加筛选条件
        
        参数:
            condition: 筛选条件对象
        """
        self.filter_conditions.append(condition)
        
    def set_rank_method(self, method: RankMethod) -> None:
        """
        设置排序方法
        
        参数:
            method: 排序方法对象
        """
        self.rank_method = method
    
    def set_weight_allocator(self, allocator: WeightAllocator) -> None:
        """
        设置权重分配器
        
        参数:
            allocator: 权重分配器对象
        """
        self.weight_allocator = allocator
        
    def run(self, data: pd.DataFrame, top_k: int = None) -> Tuple[pd.DataFrame, List[str], List[float]]:
        """
        运行流水线
        
        参数:
            data: 输入数据
            top_k: 返回的股票数量
            
        返回:
            (处理后的DataFrame, 选择的股票列表, 对应的权重列表)
        """
        original_data = data.copy()
        original_count = len(original_data)

        # 提取股票列表
        stock_column = next((col for col in ['S_INFO_WINDCODE', 'STOCKCODE', 'stock_code']
                             if col in original_data.columns), None)
        if not stock_column:
            print("警告: 未找到股票代码列")
            return original_data, [], []
        
        # 并列应用所有筛选条件
        if self.filter_conditions:
            #保存每个筛选条件通过的股票代码集合
            passed_stocks_sets = []

            for condition in self.filter_conditions:
                #每个条件基于原始数据进行筛选
                filtered_result = condition.apply(original_data.copy())
                #提取通过筛选的股票代码
                passed_stocks = set(filtered_result[stock_column])
                passed_stocks_sets.append(passed_stocks)
                print(f"应用筛选条件 '{condition.name}' 后，股票数量: {len(passed_stocks)}/{original_count}")

            #取所有筛选结果的交集
            if passed_stocks_sets:
                common_stocks = set.intersection(*passed_stocks_sets)
                print(f"所有条件交集后的股票数量:{len(common_stocks)}/{original_count}")
                # 只保留通过所有筛选的股票
                result = original_data[original_data[stock_column].isin(common_stocks)]
            else:
                result = original_data
                print(f"筛选条件无交集，未保留任何股票")
        else:
            result = original_data

        
        # 应用排序方法
        if self.rank_method:
            result = self.rank_method.apply(result)
            print(f"应用排序条件方法 '{self.rank_method.name}'")
            # 如果指定了top_k，则只保留得分最高的前k只股票
            if top_k and 'composite_score' in result.columns:
                result = result.sort_values('composite_score', ascending=False).head(top_k)
            elif top_k and 'final_rank' in result.columns:
                result = result.sort_values('final_rank').head(top_k)


        if result.empty:
            print("警告：无股票通过筛选或股票代码列不存在")
            return result, [], []
        
        # 应用权重分配
        result = self.weight_allocator.allocate(result, stock_column)
        
        # 获取股票列表和权重列表
        stock_list = list(result[stock_column])

        weight_list = list(result['weight'])
        
        return result, stock_list, weight_list 
