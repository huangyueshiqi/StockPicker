import json
import os
import tempfile
import unittest


class TestStrategyVariants(unittest.TestCase):
    def test_parse_variants(self):
        from fund.run_fund_backtest_batch import parse_variants

        variants = parse_variants("rb60_top20,rb20_top10")
        self.assertEqual(len(variants), 2)
        self.assertEqual(variants[0]["variant_id"], "rb60_top20")
        self.assertEqual(variants[0]["rebalance_period"], 60)
        self.assertEqual(variants[0]["top_k"], 20)
        self.assertEqual(variants[1]["variant_id"], "rb20_top10")
        self.assertEqual(variants[1]["rebalance_period"], 20)
        self.assertEqual(variants[1]["top_k"], 10)

    def test_apply_variant_to_config(self):
        from fund.run_fund_backtest_batch import apply_variant_to_strategy_config

        base = {"global_params": {"top_K": 20, "rebalance_period": 60, "folder_name": "x"}}
        out = apply_variant_to_strategy_config(base, rebalance_period=20, top_k=10)
        self.assertEqual(out["global_params"]["top_K"], 10)
        self.assertEqual(out["global_params"]["rebalance_period"], 20)
        self.assertEqual(out["global_params"]["folder_name"], "x")

    def test_build_command_no_llm(self):
        from fund.run_fund_backtest_batch import build_qlib_strategy_command

        cmd = build_qlib_strategy_command(
            python="python",
            script="/workspace/qlib_premium_value_strategy.py",
            fund_rule_file="/tmp/rule.txt",
            trade_file="/tmp/trade.csv",
            cache_id="cid",
            project_root="/tmp/backtrader_test",
            no_llm=True,
            strategy_config="/tmp/strategy_config.json",
            mapping_file="/tmp/mapping_result.json",
        )
        self.assertIn("--no_llm", cmd)
        self.assertIn("--strategy_config", cmd)
        i = cmd.index("--strategy_config")
        self.assertEqual(cmd[i + 1], "/tmp/strategy_config.json")
        self.assertIn("--mapping_file", cmd)
        i = cmd.index("--mapping_file")
        self.assertEqual(cmd[i + 1], "/tmp/mapping_result.json")
        self.assertNotIn("--fund_rule_file", cmd)

    def test_qlib_script_supports_no_llm_flags(self):
        p = "/workspace/qlib_premium_value_strategy.py"
        with open(p, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("--no_llm", content)
        self.assertIn("--strategy_config", content)
        self.assertIn("--mapping_file", content)


if __name__ == "__main__":
    unittest.main()

