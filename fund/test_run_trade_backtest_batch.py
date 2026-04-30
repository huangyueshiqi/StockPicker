import unittest


class TestParseTargets(unittest.TestCase):
    def test_parse_targets(self):
        from fund.run_trade_backtest_batch import parse_targets

        self.assertEqual(parse_targets("all"), None)
        self.assertEqual(parse_targets("0,1,2"), ["0", "1", "2"])
        self.assertEqual(parse_targets("[\"a\",\"b\"]"), ["a", "b"])


if __name__ == "__main__":
    unittest.main()

