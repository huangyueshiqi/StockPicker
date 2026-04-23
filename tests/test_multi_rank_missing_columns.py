import unittest

import pandas as pd


class TestMultiSimpleRankMethod(unittest.TestCase):
    def test_apply_skips_missing_rank_columns(self):
        from framework.stock_logic_framework import SimpleRankMethod, MultiSimpleRankMethod

        df = pd.DataFrame(
            {
                "S_INFO_WINDCODE": ["000001.SZ", "000002.SZ", "000003.SZ"],
                "A": [3.0, 2.0, 1.0],
            }
        )

        m1 = SimpleRankMethod(name="rank_a", column="A", ascending=True, weight=1.0, scope="market")
        m2 = SimpleRankMethod(name="rank_missing", column="B", ascending=True, weight=1.0, scope="market")
        multi = MultiSimpleRankMethod(name="multi", rank_methods=[m1, m2])

        out = multi.apply(df)

        self.assertIn("A_rank", out.columns)
        self.assertNotIn("B_rank", out.columns)
        self.assertIn("composite_rank", out.columns)
        self.assertIn("final_rank", out.columns)
        self.assertTrue(out["composite_rank"].equals(out["A_rank"]))


if __name__ == "__main__":
    unittest.main()

