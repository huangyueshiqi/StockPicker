import json
import os
import tempfile
import unittest


class TestFundConfigSaved(unittest.TestCase):
    def test_config_copied_when_exists(self):
        import fund.run_fund_backtest_batch as mod

        with tempfile.TemporaryDirectory() as d:
            fund_dir = os.path.join(d, "fund_x")
            os.makedirs(fund_dir, exist_ok=True)
            cache_dir = os.path.join(d, "cache")
            os.makedirs(cache_dir, exist_ok=True)

            src = os.path.join(cache_dir, "generated_strategy.json")
            with open(src, "w", encoding="utf-8") as f:
                json.dump({"a": 1}, f)

            dst = os.path.join(fund_dir, "generated_strategy.json")
            ok = mod.copy_if_exists(src, dst)
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(dst))


if __name__ == "__main__":
    unittest.main()

