import unittest


class TestSkipNoRule(unittest.TestCase):
    def test_should_skip_fund_rule(self):
        from fund.run_fund_backtest_batch import should_skip_fund_rule

        self.assertTrue(should_skip_fund_rule(""))
        self.assertTrue(should_skip_fund_rule("   "))
        self.assertFalse(should_skip_fund_rule("x"))


if __name__ == "__main__":
    unittest.main()

