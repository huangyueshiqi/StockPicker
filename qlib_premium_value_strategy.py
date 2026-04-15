import os
import json
import pandas as pd
import argparse
import logging
import sys
import time
import subprocess

from framework.strategy_framework import (
    BaseDataProcessor, BaseStockFilter,
    BaseFeatureCalculator, BaseStrategy
)
from framework.qlib_data_reader import QlibDataReader
from framework.stock_selectors import PremiumValueStockSelector
from framework.llm_cache_manager import make_cache_id, read_latest, write_latest, write_meta
from tools.llm_strategy_generator import LLMStrategyGenerator

class QlibPremiumValueDataProcessor(BaseDataProcessor):
    """
    基于 Qlib 数据源的数据处理器
    """
    def process_data(self, data_dict, end_date):
        """
        数据预处理
        
        参数:
            data_dict: 包含原始数据的字典
            end_date: 结束日期
            
        返回:
            处理后的数据字典
        """
        if 'qlib_data' in data_dict and not data_dict['qlib_data'].empty:
            df = data_dict['qlib_data']
            # 基本的清洗逻辑
            df = df.dropna(how='all', axis=1)  # 删除全为NaN的列
            data_dict['qlib_data'] = df
            print(f'去重和删除NaN值后 Qlib 数据形状: {data_dict["qlib_data"].shape}')

        return data_dict


class QlibPremiumValueStockFilter(BaseStockFilter):
    """
    基于 Qlib 数据源的股票筛选器
    """
    def filter_stocks(self, data_dict, date, **kwargs):
        """
        初步筛选符合条件的股票
        
        参数:
            data_dict: 包含所有数据的字典
            date: 当前日期
            
        返回:
            符合条件的股票代码列表
        """
        # 由于是基于提前设定好的 stock_pool_file 提取，
        # 如果有进一步的基于上市时间的筛选需求，可以在这里补充，
        # 目前直接返回所有获取到的股票。
        if 'qlib_data' in data_dict and not data_dict['qlib_data'].empty:
            return data_dict['qlib_data']['S_INFO_WINDCODE'].unique().tolist()
        return []


class QlibPremiumValueFeatureCalculator(BaseFeatureCalculator):
    """
    基于 Qlib 数据源的特征计算器
    """
    def calculate_features(self, data_dict, stock_list):
        """
        计算特征并合并最终宽表
        
        参数:
            data_dict: 包含所有数据的字典
            stock_list: 股票列表
            
        返回:
            包含特征的DataFrame
        """
        if 'qlib_data' not in data_dict or data_dict['qlib_data'].empty:
            return pd.DataFrame()

        res_df = data_dict['qlib_data']
        # 仅保留股票列表中的数据
        res_df = res_df[res_df['S_INFO_WINDCODE'].isin(stock_list)].copy()
        
        print(f'最终特征宽表形状: {res_df.shape}')
        print(f'最终股票数量：{len(res_df["S_INFO_WINDCODE"].unique())}')
        
        return res_df


class QlibPremiumValueStrategy(BaseStrategy):
    """
    使用 Qlib 作为数据源的优质价值策略
    """
    def __init__(self, 
                 mapping_file: str,
                 stock_pool_file: str,
                 macro_file: str,
                 start_date=None, 
                 end_date=None, 
                 rebalance_freq='Q', 
                 rebalance_period=60,
                 use_config=True,
                 config_filename=None,
                 config_dir="config"):
        """
        初始化策略
        """
        if use_config:
            if config_filename is None:
                config_filename = "premium_value_strategy.json"

            config_path = os.path.join(config_dir, config_filename)

            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            global_params = config.get('global_params', {})
            start_date = start_date or global_params.get('start_date')
            end_date = end_date or global_params.get('end_date')
            rebalance_period = rebalance_period or global_params.get('rebalance_period')

            # 复用原有的 Selector，因为其基于 Pipeline，只依赖 DataFrame 中的列名
            stock_selector = PremiumValueStockSelector(
                weight_method='equal',
                use_config=True,
                config_path=config_path
            )
        else:
            stock_selector = PremiumValueStockSelector()
            config_path = None

        # 实例化基于 Qlib 的 Reader
        data_reader = QlibDataReader(
            mapping_file=mapping_file,
            stock_pool_file=stock_pool_file,
            macro_file=macro_file,
            config_path=config_path
        )
        
        data_processor = QlibPremiumValueDataProcessor()
        stock_filter = QlibPremiumValueStockFilter()
        feature_calculator = QlibPremiumValueFeatureCalculator()
        
        super().__init__(
            data_reader=data_reader,
            data_processor=data_processor,
            stock_filter=stock_filter,
            feature_calculator=feature_calculator,
            stock_selector=stock_selector,
            start_date=start_date,
            end_date=end_date,
            rebalance_freq=rebalance_freq,
            rebalance_period=rebalance_period,
        )


def parse_args():
    parser = argparse.ArgumentParser(description='LLM 策略量化交易回测系统端到端流水线')
    parser.add_argument('--prompt', type=str, default='', help='自然语言策略描述')
    parser.add_argument('--interactive', action='store_true', help='如果没有提供prompt，是否进入交互模式输入')
    parser.add_argument('--cache_id', type=str, default='', help='使用指定 cache_id(时间戳) 目录下的策略配置与映射文件')
    parser.add_argument('--mode', type=str, default='llm', help='回测模式，固定为llm')
    parser.add_argument('--trade_file', type=str, default='qlib_premium_value_strategy_result.csv', help='调仓表文件路径')
    parser.add_argument('--output', type=str, default='', help='输出结果文件路径')
    parser.add_argument('--plot_output', type=str, default='plot/llm_strategy_plot.png', help='策略回测资产变化图保存路径')
    parser.add_argument('--plot_trades', action='store_true', default=False, help='是否绘制每只股票的买卖点图 (默认关闭)')
    parser.add_argument('--verbose', action='store_true', help='是否输出详细信息')
    parser.add_argument('--project_root', type=str, default='/home/quant/zc/backtrader/QuantBacktester_57', help='QuantBacktester项目的根目录路径')
    return parser.parse_args()


def build_run_llm_command(args, python_executable: str = None, script_dir: str = None):
    if python_executable is None:
        python_executable = sys.executable

    if script_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))

    run_llm_path = os.path.join(script_dir, "run_llm.py")
    cmd = [
        python_executable,
        run_llm_path,
        "--mode", args.mode,
        "--trade_file", args.trade_file,
        "--plot_output", args.plot_output,
        "--project_root", args.project_root,
    ]

    if getattr(args, "output", ""):
        cmd.extend(["--output", args.output])

    if getattr(args, "plot_trades", False):
        cmd.append("--plot_trades")

    if getattr(args, "verbose", False):
        cmd.append("--verbose")

    return cmd


def should_generate_mapping(strategy_regenerated: bool, mapping_exists: bool) -> bool:
    return strategy_regenerated or not mapping_exists


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

    # === 1. 环境与路径准备 ===
    config_dir = "config"
    docs_dir = "documents"
    
    cache_root = os.path.join(config_dir, "llm_cache")
    cache_id = args.cache_id.strip() if getattr(args, "cache_id", "") else ""
    has_prompt_input = bool(args.prompt) or bool(args.interactive)

    if not cache_id:
        if has_prompt_input:
            cache_id = make_cache_id()
        else:
            latest = read_latest(cache_root)
            if not latest:
                print(f"未提供 prompt 且未找到可用的 latest 缓存: {os.path.join(cache_root, 'latest.txt')}")
                return
            cache_id = latest

    cache_dir = os.path.join(cache_root, cache_id)
    os.makedirs(cache_dir, exist_ok=True)

    config_filename = "generated_strategy.json"
    config_path = os.path.join(cache_dir, config_filename)
    mapping_file = os.path.join(cache_dir, "mapping_result.json")
    prompt_file = os.path.join(cache_dir, "prompt.txt")
    
    # 外部依赖的参考数据文件
    stock_pool_file = os.path.join(config_dir, "filtered_stock_pool.json")
    macro_file = os.path.join(docs_dir, "macro_data.csv")
    
    # 字段候选文件列表，用于传递给大模型进行映射
    csv_files = [
        os.path.join(docs_dir, "财务字段中英文对照表.csv"),
        os.path.join(docs_dir, "宏观微观字段名对照表.csv"),
        os.path.join(docs_dir, "量价字段中英文对照表.csv")
    ]
    
    # 为演示环境初始化基础文件（如果在空环境测试）
    os.makedirs(docs_dir, exist_ok=True)
    os.makedirs(config_dir, exist_ok=True)
    if not os.path.exists(macro_file):
        with open(macro_file, 'w') as f: f.write("datetime,macro_value\n")
    if not os.path.exists(stock_pool_file):
        with open(stock_pool_file, 'w') as f: json.dump(["000001.SH"], f)
        
    # === 2. 策略配置与字段映射 (LLM 端到端链路) ===
    
    # 初始化 LLM 生成器
    # 这里的模型和 base_url 可根据需要更改，或者依赖环境变量 OPENAI_API_KEY
    generator = LLMStrategyGenerator()
    
    strategy_regenerated = False
    if has_prompt_input:
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(prompt)

    if has_prompt_input or not os.path.exists(config_path):
        print(f"正在通过 LLM 生成策略配置... cache_id={cache_id}")
        strategy_config = generator.generate(prompt, config_path)
        strategy_regenerated = True
        write_latest(cache_root, cache_id)
        write_meta(cache_dir, {"cache_id": cache_id, "prompt": prompt, "created_at": time.time()})
    else:
        print(f"发现已存在的策略配置，直接读取。cache_id={cache_id}")
        with open(config_path, 'r', encoding='utf-8') as f:
            strategy_config = json.load(f)
            
    if not strategy_config:
        print("策略配置生成或读取失败，无法继续。")
        return
        
    # 根据策略配置动态生成/复用 字段映射文件 (mapping_result.json)
    if should_generate_mapping(strategy_regenerated=strategy_regenerated, mapping_exists=os.path.exists(mapping_file)):
        print(f"未找到字段映射文件或需要重新生成，正在通过 LLM 自动匹配真实数据表... cache_id={cache_id}")
        success = generator.generate_mapping(strategy_config, csv_files, mapping_file)
        if not success:
            print("字段映射生成失败。")
            return
    else:
        print(f"发现已缓存的字段映射 mapping_result.json，直接复用。cache_id={cache_id}")

    # === 3. 执行策略回测 ===
    
    strategy = QlibPremiumValueStrategy(
        mapping_file=mapping_file,
        stock_pool_file=stock_pool_file,
        macro_file=macro_file,
        use_config=True,
        config_filename=config_filename,
        config_dir=cache_dir
    )
    
    rebalance_result = strategy.run()
    strategy.save_results(rebalance_result, args.trade_file)
    print(f"调仓表已保存至: {args.trade_file}")

    # === 4. 执行回测 ===
    print("\n===== 开始调用回测框架 =====")
    cmd = build_run_llm_command(args)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"回测脚本执行失败，退出码: {result.returncode}")

if __name__ == "__main__":
    args = parse_args()
    main(args)
