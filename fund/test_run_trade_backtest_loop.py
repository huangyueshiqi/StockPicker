import unittest


class TestLoopHelpers(unittest.TestCase):
    def test_is_file_stable(self):
        from fund.run_trade_backtest_batch import is_file_stable

        self.assertFalse(is_file_stable("/tmp/not-exist.csv", min_age_seconds=1))


if __name__ == "__main__":
    unittest.main()

