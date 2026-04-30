import unittest


class TestCommandBuild(unittest.TestCase):
    def test_build_command_includes_fund_rule(self):
        from fund.run_fund_backtest_batch import build_qlib_strategy_command

        cmd = build_qlib_strategy_command(
            python="python",
            script="/workspace/qlib_premium_value_strategy.py",
            fund_rule_file="/tmp/rule.txt",
            trade_file="/tmp/trade.csv",
            plot_output="/tmp/plot.png",
            backtest_log="/tmp/backtest.log",
            cache_id="cid",
            project_root="/tmp/backtrader_test",
        )
        self.assertIn("--fund_rule_file", cmd)
        i = cmd.index("--fund_rule_file")
        self.assertEqual(cmd[i + 1], "/tmp/rule.txt")


if __name__ == "__main__":
    unittest.main()
