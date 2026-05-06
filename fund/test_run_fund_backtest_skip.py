import unittest


class TestSkipLogic(unittest.TestCase):
    def test_skip_when_pos_too_few(self):
        from fund.run_fund_backtest_batch import should_skip_fund

        self.assertEqual(should_skip_fund(pos_count=0, rule="x", min_pos=5), "too_few_pos")

    def test_skip_when_rule_empty(self):
        from fund.run_fund_backtest_batch import should_skip_fund

        self.assertEqual(should_skip_fund(pos_count=10, rule="", min_pos=5), "empty_rule")

    def test_not_skip(self):
        from fund.run_fund_backtest_batch import should_skip_fund

        self.assertIsNone(should_skip_fund(pos_count=5, rule="x", min_pos=5))


if __name__ == "__main__":
    unittest.main()

