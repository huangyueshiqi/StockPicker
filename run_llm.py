import os
import logging
import sys
import argparse
import time


def parse_args():
    parser = argparse.ArgumentParser(description='LLM 策略量化交易回测系统')
    # 添加参数
    parser.add_argument('--mode', type=str, default='llm', help='回测模式，固定为llm')
    parser.add_argument('--trade_file', type=str, required=True, help='调仓表文件路径(必须提供)')
    parser.add_argument('--output', type=str, default='', help='输出结果文件路径')
    parser.add_argument('--plot_output', type=str, default='plot/llm_strategy_plot.png',
                        help='策略回测资产变化图保存路径')
    parser.add_argument('--plot_trades', action='store_true', default=False,
                        help='是否绘制每只股票的买卖点图 (默认关闭)')
    parser.add_argument('--verbose', action='store_true', help='是否输出详细信息')
    parser.add_argument('--project_root', type=str, default='/home/quant/zc/backtrader/QuantBacktester_57', help='QuantBacktester项目的根目录路径')

    return parser.parse_args()


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def run_backtest(
    trade_file: str,
    plot_output: str,
    plot_trades: bool,
    verbose: bool,
    project_root: str,
    output: str = "",
):
    # 验证输入文件
    if not os.path.exists(trade_file):
        raise FileNotFoundError(f"调仓表文件不存在: {trade_file}")

    import pandas as pd

    project_root_abs = os.path.abspath(project_root)
    if project_root_abs in sys.path:
        sys.path.remove(project_root_abs)
    sys.path.insert(0, project_root_abs)

    from main import BacktestManager
    from utils.config import config

    # 初始化回测管理器
    backtest_manager = BacktestManager()

    # 此处假设回测时间和从配置或文件读取
    # 更新策略配置参数，可以根据你的项目需要动态调整，或者从文件推断
    # 获取调仓表数据以推断起止时间
    try:
        trade_list = pd.read_csv(trade_file)
        if 'datetime' not in trade_list.columns and 'date' in trade_list.columns:
            date_col = 'date'
        elif 'datetime' in trade_list.columns:
            date_col = 'datetime'
        else:
            raise ValueError("调仓表中没有找到日期列 (date/datetime)")

        trade_list[date_col] = pd.to_datetime(trade_list[date_col])
        min_date = trade_list[date_col].min().strftime('%Y-%m-%d')
        max_date = trade_list[date_col].max().strftime('%Y-%m-%d')

        start_date = min_date
        # 加上一定的缓冲期，比如往后推一个月
        end_date = (pd.to_datetime(max_date) + pd.Timedelta(days=30)).strftime('%Y-%m-%d')

        logging.info(f"根据调仓表推断回测区间: {start_date} -> {end_date}")
    except Exception as e:
        raise RuntimeError(f"读取调仓表出错: {e}") from e

    param_map = {
        'start_date': start_date,
        'end_date': end_date,
        'deal_dividend': False,  # 分红
        'save_state': False,  # llm一般是全量回测
        'adjust_freq': 'D',  # 调仓频率
        'is_predict': False,
    }

    strategy_params = {k: v for k, v in param_map.items() if v is not None}
    if strategy_params:
        print("\n=== 策略配置参数更新 ===")
        config.update_strategy_params(**strategy_params)
        print("=======================")

    # 确保输出目录存在
    old_stdout = sys.stdout
    out_f = None
    try:
        if output:
            os.makedirs(os.path.dirname(output), exist_ok=True)
            out_f = open(output, 'w', encoding='utf-8')
            sys.stdout = out_f

        # 记录开始时间
        start_time = time.time()

        # 执行回测
        print("执行 LLM 回测...")
        backtest_manager.run_llm_backtest(
            trade_file=trade_file,
            plot_output=plot_output,
            plot_trades=plot_trades,
            verbose=verbose
        )

        # 输出总运行时间
        end_time = time.time()
        print(f'回测总运行时间：{end_time - start_time:.2f}秒')
    finally:
        if out_f:
            out_f.close()
        sys.stdout = old_stdout

def run():
    args = parse_args()
    run_backtest(
        trade_file=args.trade_file,
        plot_output=args.plot_output,
        plot_trades=args.plot_trades,
        verbose=args.verbose,
        project_root=args.project_root,
        output=args.output,
    )


if __name__ == "__main__":
    run()
