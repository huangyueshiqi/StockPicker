import json
import yaml
import os
from typing import Dict, List, Any, Optional, Union, Callable

import pandas as pd

from framework.stock_logic_framework import (
    SimpleFilterCondition, RangeFilterCondition, RankFilterCondition,RankRangeFilterCondition, CustomFilterCondition,
    SimpleRankMethod,MultiSimpleRankMethod,
    StockFilterPipeline, EqualWeightAllocator, WeightAllocator
)


class StrategyConfigLoader:
    """
    策略配置加载器，负责从配置文件加载和解析策略配置
    """

    def __init__(self, config_path: str):
        """
        初始化配置加载器

        参数：
            config_path:配置文件路径（JSON或YAMl格式）
        """
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """
        加载配置文件

        返回：
            配置字典
        """
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f'配置文件不存在：{self.config_path}')

        file_ext = os.path.splitext(self.config_path)[1].lower()

        try:
            if file_ext == '.json':
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            elif file_ext in ['.yaml', '.yml']:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            else:
                raise ValueError(f'不支持的配置文件格式：{file_ext}')
        except Exception as e:
            raise Exception(f'加载配置文件失败：{str(e)}')

    def get_strategy_name(self) -> str:
        """
        获取策略名称

        返回：
            策略名称
        """
        return self.config.get('name', '未命名策略')

    def get_strategy_description(self) -> str:
        """
        获取策略描述

        返回：
            策略描述
        """
        return self.config.get('description', '')

    def get_global_params(self) -> Dict:
        """
        获取全局参数

        返回：
            全局参数字典
        """
        return self.config.get('global_params', {})

    def get_data_source_config(self) -> Dict:
        """
        获取数据源配置 (例如 Qlib 映射文件、股票池等)

        返回：
            数据源配置字典
        """
        return self.config.get('data_source', {})

    def get_filters(self) -> List[Dict]:
        """
        获取筛选条件配置

        返回：
            筛选条件配置列表
        """
        return self.config.get('filters', [])

    def get_ranking_method(self) -> Dict:
        """
        获取排序方法配置

        返回：
            排序方法配置
        """
        return self.config.get('ranking', [])

    def get_weight_allocating(self) -> Dict:
        """
        获取权重分配配置

        返回：
            权重分配配置
        """
        return self.config.get('weight_allocation', {})


class StrategyFactory:
    """
    策略工厂，根据配置创建策略组件
    """

    def __init__(self, config_loader: StrategyConfigLoader):
        """
        初始化策略工厂

        参数：
            config_loader: 配置加载器实例
        """
        self.config = config_loader
        # 用于存储自定义过滤函数的映射
        self.custom_filter_funcs = {}

    def register_custom_filter(self, name: str, func: Callable):
        """
        注册自定义过滤函数

        参数：
            name: 函数名称
            func: 函数对象
        """
        self.custom_filter_funcs[name] = func

    def _create_filter_conditions(self, filter_config: Dict) -> Union[
        SimpleFilterCondition, RangeFilterCondition, RankFilterCondition, RankRangeFilterCondition, CustomFilterCondition]:
        """
         创建筛选条件

         参数：
             filter_config: 筛选条件配置

         返回：
             筛选条件对象
         """
        filter_type = filter_config['type']
        name = filter_config['name']
        description = filter_config.get('description', '')

        if filter_type == 'simple':
            return SimpleFilterCondition(
                name=name,
                column=filter_config['column'],
                operator=filter_config['operator'],
                threshold=filter_config['threshold'],
                description=description
            )
        elif filter_type == 'range':
            return RangeFilterCondition(
                name=name,
                column=filter_config['column'],
                min_value=filter_config['min_value'],
                max_value=filter_config['operator'],
                include_min=filter_config.get('include_min', True),
                include_max=filter_config.get('include_max', True),
                description=description
            )
        elif filter_type == 'rank':
            return RankFilterCondition(
                name=name,
                column=filter_config['column'],
                operator=filter_config['operator'],
                threshold=filter_config['threshold'],
                rank_type=filter_config.get('rank_type', 'absolute'),
                scope=filter_config.get('scope', 'market'),
                industry_column=filter_config.get('industry_column'),
                ascending=filter_config.get('ascending', False),
                description=description
            )
        elif filter_type == 'rank_range':
            return RankRangeFilterCondition(
                name=name,
                column=filter_config['column'],
                min_value=filter_config['min_value'],
                max_value=filter_config['max_value'],
                rank_type=filter_config.get('rank_type', 'absolute'),
                scope=filter_config.get('scope', 'market'),
                industry_column=filter_config.get('industry_column'),
                ascending=filter_config.get('ascending', False),
                description=description
            )
        elif filter_type == 'custom':
            func_name = filter_config['function']
            if func_name in self.custom_filter_funcs:
                filter_func = self.custom_filter_funcs[func_name]
            else:
                raise ValueError(f'未注册的自定义过滤函数：{func_name}')

            return CustomFilterCondition(
                name=name,
                filter_func=filter_func,
                description=description
            )
        else:
            raise ValueError(f'不支持的筛选条件类型：{filter_type}')


    def create_rank_method(self) -> Optional[Union[SimpleRankMethod,MultiSimpleRankMethod]]:
        """
         创建排序方法

         返回：
             排序方法对象
         """
        ranking_config = self.config.get_ranking_method()
        if not ranking_config:
            return None

        method_type = ranking_config.get('method')
        name = ranking_config.get('name', '排序方法')
        description = ranking_config.get('description', '')

        if method_type == 'simple':
            return SimpleRankMethod(
                name=name,
                column=ranking_config['column'],
                ascending=ranking_config.get('ascending', True),
                scope=ranking_config.get('scope', 'market'),
                industry_column=ranking_config.get('industry_column'),
                weight=ranking_config.get('weight', 1.0),
                description=description
            )
        elif method_type == 'multi_simple':
            # 创建多个SimpleRankMethod对象
            components =[]
            for component_config in ranking_config.get('components', []):
                simple_method = SimpleRankMethod(
                    name=component_config.get('name', f"{component_config['column']}排序"),
                    column=component_config['column'],
                    ascending=component_config.get('ascending', True),
                    scope=component_config.get('scope', 'market'),
                    industry_column=component_config.get('industry_column'),
                    weight=component_config.get('weight', 1.0),
                    description=component_config.get('description', 1.0)
                )
                components.append(simple_method)

            return MultiSimpleRankMethod(
                name=name,
                rank_methods=components,
                description=description
            )
        else:
            raise ValueError(f'不支持的排序方法类型：{method_type}')


    def create_weight_allocator(self) -> Optional[WeightAllocator]:
        """
         创建权重分配器

         返回：
             权重分配器对象
         """
        weight_config = self.config.get_weight_allocating()
        if not weight_config:
            return EqualWeightAllocator()  # 默认使用等权重

        allocator_type = weight_config.get('type', 'equal')
        name = weight_config.get('name', '权重分配')
        description = weight_config.get('description', '')

        if allocator_type == 'equal':
            return EqualWeightAllocator(
                name=name,
                description=description
            )
        else:
            raise ValueError(f'不支持的权重分配器类型：{allocator_type}')

    def create_filter_pipeline(self) -> StockFilterPipeline:
        """
         创建筛选流水线

         返回：
             筛选流水线对象
         """
        name = self.config.get_strategy_name()
        description = self.config.get_strategy_description()
        pipeline = StockFilterPipeline(
            name=f'{name}流水线',
            description=description
        )

        # 添加筛选条件
        for filter_config in self.config.get_filters():
            filter_condition = self._create_filter_conditions(filter_config)
            pipeline.add_filter_condition(filter_condition)

        # 设置排序方法
        rank_method = self.create_rank_method()
        if rank_method:
            pipeline.set_rank_method(rank_method)

        # 设置权重分配器
        weight_allocator = self.create_weight_allocator()
        if weight_allocator:
            pipeline.set_weight_allocator(weight_allocator)

        return pipeline
