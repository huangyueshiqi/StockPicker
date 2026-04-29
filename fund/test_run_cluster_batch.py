import unittest


class TestSelectFeatureColumns(unittest.TestCase):
    def test_select_feature_columns_keeps_base_and_selected(self):
        from fund.run_cluster_batch import select_feature_columns

        df_cols = ["fund", "instrument", "datetime", "label", "a", "b", "c"]
        selected = ["c", "a", "x"]
        base = ["fund", "instrument", "datetime", "label"]

        out = select_feature_columns(df_cols, selected, base)
        self.assertEqual(out, ["fund", "instrument", "datetime", "label", "c", "a"])


if __name__ == "__main__":
    unittest.main()

