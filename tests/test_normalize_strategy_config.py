import unittest


class TestNormalizeStrategyConfig(unittest.TestCase):
    def test_normalize_adds_defaults(self):
        from tools.llm_strategy_generator import normalize_strategy_config

        cfg = {"global_params": {"start_date": "20210101", "end_date": "20211231"}}
        out = normalize_strategy_config(cfg)
        self.assertIn("derived_features", out)
        self.assertIsInstance(out["derived_features"], list)
        self.assertIn("lookback_years", out["global_params"])
        self.assertEqual(out["global_params"]["lookback_years"], 5)


if __name__ == "__main__":
    unittest.main()

