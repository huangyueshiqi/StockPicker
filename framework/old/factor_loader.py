import os
import sys
import json
import importlib
import logging
import chardet  # 用于自动检测文件编码
from typing import Dict, List, Optional, Union, Tuple

import pandas as pd

from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('FactorLoader')

# 有条件地添加路径，防止在不同环境下出错
try:
    sys.path.append("/home/quant/wsq/wsq/langchain_test")
    from refactor import FactorCodeGenerator
except (ImportError, ModuleNotFoundError):
    logger.warning("无法导入FactorCodeGenerator")


class FactorLoader:
    """
    因子加载器类
    用于加载、计算和管理因子数据
    """

    def __init__(self, config_dir: Optional[Union[str, Path]] = None):
        """
        初始化因子加载器

        参数:
            config_dir: 配置文件目录，默认为None（自动查找）
        """
        self.config_dir = self._find_config_dir(config_dir)
        self.factor_df = None
        self.config = None
        self.factor_dir = None

    def _find_config_dir(self, config_dir: Optional[Union[str, Path]]) -> Path:
        """
        查找配置文件目录

        参数:
            config_dir: 配置文件目录，如果为None则自动查找

        返回:
            配置文件目录的Path对象
        """
        if config_dir is not None:
            return Path(config_dir)

        # 尝试多个可能的路径
        possible_paths = [
            Path("config"),
            Path(__file__).parent.parent / "config",
            Path.cwd() / "config",
            Path.home() / "config"
        ]

        for path in possible_paths:
            if path.exists():
                logger.info(f"找到配置目录: {path}")
                return path

        # 未找到配置目录，使用当前目录
        logger.warning("未找到配置目录，将使用当前目录")
        return Path("..")

    def load_factor_config(self, factor_csv: Optional[str] = None) -> pd.DataFrame:
        """
        加载因子配置

        参数:
            factor_csv: 因子配置CSV文件名，默认为'factor.csv'

        返回:
            因子配置DataFrame
        """
        if factor_csv is None:
            factor_csv = "factor.csv"

        factor_file = self.config_dir / factor_csv
        # try:
        #     logger.info(f"正在读取因子配置: {factor_file}")
        #     self.factor_df = pd.read_csv(factor_file)
        #     return self.factor_df
        # except Exception as e:
        #     logger.error(f"读取因子配置失败: {e}")
        #     self.factor_df = pd.DataFrame()
        #     return self.factor_df
        try:
            logger.info(f"正在读取因子配置: {factor_file}")

            # 先尝试 UTF-8，如果失败再尝试其他编码
            try:
                self.factor_df = pd.read_csv(factor_file, encoding="utf-8")
            except UnicodeDecodeError:
                # 检测文件真实编码
                with open(factor_file, "rb") as f:
                    raw_data = f.read(10000)  # 读取前 10000 字节检测编码
                    result = chardet.detect(raw_data)
                    file_encoding = result["encoding"]

                logger.warning(f"UTF-8 解码失败，尝试使用检测到的编码: {file_encoding}")
                self.factor_df = pd.read_csv(factor_file, encoding=file_encoding)

            return self.factor_df

        except Exception as e:
            logger.error(f"读取因子配置失败: {e}")
            self.factor_df = pd.DataFrame()
            return self.factor_df


    def load_strategy_config(self, config_file: Optional[str] = None) -> dict:
        """
        加载策略配置

        参数:
            config_file: 策略配置JSON文件名，默认为'premium_value_strategy.json'

        返回:
            策略配置字典
        """
        if config_file is None:
            config_file = "premium_value_strategy.json"

        config_path = self.config_dir / config_file
        try:
            logger.info(f"正在读取策略配置: {config_path}")
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            return self.config
        except Exception as e:
            logger.error(f"读取策略配置失败: {e}")
            self.config = {}
            return self.config

    def setup_factor_directory(self) -> Path:
        """
        设置因子目录

        返回:
            因子目录的Path对象
        """
        if self.config is None:
            self.load_strategy_config()

        # 从配置获取文件夹名称
        global_params = self.config.get('global_params', {})
        folder_name = global_params.get('folder_name')

        if not folder_name:
            logger.warning("配置中未指定folder_name，将使用'prem_value'")
            folder_name = "prem_value"

        # 尝试多个可能的路径
        # 首先尝试使用配置中的绝对路径
        if os.path.exists("/home/quant/zc/backtrader/QuantStockPicker"):
            base_path = Path(f"/home/quant/zc/backtrader/QuantStockPicker/result/{folder_name}")
        else:
            # 然后尝试相对于项目根目录的路径
            base_path = Path(__file__).parent.parent / "result" / folder_name

        # 检查路径是否存在，如果不存在则创建
        if not base_path.exists():
            logger.info(f"创建因子目录: {base_path}")
            base_path.mkdir(parents=True, exist_ok=True)

        self.factor_dir = base_path
        return base_path

    def generate_factor_files(self) -> None:
        """生成所有因子文件"""
        if self.factor_df is None or self.factor_df.empty:
            logger.error("因子配置为空，无法生成因子文件")
            return

        if self.factor_dir is None:
            self.setup_factor_directory()

        for index, row in self.factor_df.iterrows():
            factor_name = row['英文名称']
            factor_info = f"因子名称:{row.get('中文名称', '')},因子含义:{row.get('因子含义', '')}"

            # 检查因子文件是否已存在
            factor_file = self.factor_dir / f"{factor_name}.py"
            if not factor_file.exists():
                logger.info(f"正在生成因子文件: {factor_name}")
                generator = FactorCodeGenerator(factor_name, factor_info, self.factor_dir)
                generator.run()
            else:
                logger.info(f"因子文件已存在，跳过生成: {factor_name}")

    def calculate_factor(self, factor_name: str, date: str) -> pd.DataFrame:
        """
        计算单个因子

        参数:
            factor_name: 因子名称
            date: 计算日期

        返回:
            因子计算结果DataFrame
        """
        if self.factor_dir is None:
            self.setup_factor_directory()

        try:
            # 构建模块路径
            module_path = Path(self.factor_dir) / f"{factor_name}.py"

            if not module_path.exists():
                raise FileNotFoundError(f"因子计算文件不存在: {module_path}")

            # 动态导入模块
            spec = importlib.util.spec_from_file_location(factor_name, module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 实例化 CalculateFactor 并调用 main(date)
            calculator = module.CalculateFactor()
            return calculator.main(date)

        except Exception as e:
            logger.error(f"计算因子[{factor_name}]失败: {e}")
            # 返回空DataFrame
            return pd.DataFrame(columns=['S_INFO_WINDCODE', 'TRADE_DT', factor_name])

    def calculate_all_factors(self, date: str) -> Dict[str, pd.DataFrame]:
        """
        计算所有因子

        参数:
            date: 计算日期

        返回:
            因子计算结果字典 {因子名: DataFrame}
        """
        if self.factor_df is None or self.factor_df.empty:
            logger.error("因子配置为空，无法计算因子")
            return {}

        if self.factor_dir is None:
            self.setup_factor_directory()

        results = {}
        for index, row in self.factor_df.iterrows():
            factor_name = row['英文名称']
            try:
                factor_data = self.calculate_factor(factor_name, date)
                results[factor_name] = factor_data
                logger.info(f"计算成功: {factor_name}，大小:{factor_data.shape}")
            except Exception as e:
                logger.error(f"计算失败 [{factor_name}]: {e}")

        return results

    def merge_factor_results(self, factor_results: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        将多个因子的结果按股票代码和日期合并为一个宽表 DataFrame

        参数:
            factor_results: 字典格式 {因子名: DataFrame}

        返回:
            合并后的 DataFrame（列：S_INFO_WINDCODE, TRADE_DT, 因子1, 因子2, ...）
        """
        if not factor_results:
            return pd.DataFrame()

        # 初始化基准列（股票代码 + 日期）
        first_factor = list(factor_results.keys())[0]
        merged_df = factor_results[first_factor][["S_INFO_WINDCODE", "TRADE_DT"]].copy()

        # 逐个合并因子
        for factor_name, df in factor_results.items():
            # 确保列名一致（假设因子值在第三列）
            if len(df.columns) < 3:
                logger.warning(f"因子[{factor_name}]结果列数不足，跳过合并")
                continue

            value_col = df.columns[2]
            temp_df = df[["S_INFO_WINDCODE", "TRADE_DT", value_col]].copy()

            # 按股票代码和日期合并
            merged_df = pd.merge(
                merged_df,
                temp_df,
                on=["S_INFO_WINDCODE", "TRADE_DT"],
                how="outer"
            )

        # 按日期和股票代码排序
        merged_df.sort_values(by=["TRADE_DT", "S_INFO_WINDCODE"], inplace=True)
        return merged_df.reset_index(drop=True)

    def load_and_calculate(self, date: str, factor_csv: Optional[str] = None,
                           strategy_config: Optional[str] = None) -> Tuple[Dict[str, pd.DataFrame], pd.DataFrame]:
        """
        加载配置并计算所有因子（一键式调用）

        参数:
            date: 计算日期
            factor_csv: 因子配置CSV文件名，默认为None
            strategy_config: 策略配置文件名，默认为None

        返回:
            (因子结果字典, 合并后的DataFrame)
        """
        # 1. 加载配置
        self.load_factor_config(factor_csv)
        self.load_strategy_config(strategy_config)

        # 2. 设置因子目录
        self.setup_factor_directory()

        # 3. 生成因子文件
        self.generate_factor_files()

        # 4. 计算所有因子
        factor_results = self.calculate_all_factors(date)

        # 5. 合并因子结果
        merged_data = self.merge_factor_results(factor_results)

        return merged_data


if __name__=="__main__":
    date='20220630'
    loader=FactorLoader("/home/quant/zc/backtrader/QuantStockPicker/config")
    merged_data=loader.load_and_calculate(date,"factor.csv","premium_value_strategy.json")
    print("ok")