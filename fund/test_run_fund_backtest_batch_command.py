import unittest


class TestCommandBuild(unittest.TestCase):
    def test_build_command_includes_fund_rule(self):
        from fund.run_fund_backtest_batch import build_qlib_strategy_command

        cmd = build_qlib_strategy_command(
            python="python",
            script="/workspace/qlib_premium_value_strategy.py",
            df_value_path="/tmp/df.csv",
            features_path="/tmp/feat.csv",
            fund_rule="RULE",
            trade_file="/tmp/trade.csv",
            plot_output="/tmp/plot.png",
            backtest_log="/tmp/backtest.log",
            cache_id="cid",
            project_root="/tmp/backtrader_test",
        )
        self.assertIn("--fund_rule", cmd)
        i = cmd.index("--fund_rule")
        self.assertEqual(cmd[i + 1], "RULE")


if __name__ == "__main__":
    unittest.main()

