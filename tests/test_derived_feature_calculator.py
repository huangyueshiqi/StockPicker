import unittest

import pandas as pd


class TestDerivedFeatureCalculator(unittest.TestCase):
    def test_cagr_3y(self):
        from framework.derived_feature_calculator import apply_derived_features

        df = pd.DataFrame(
            {
                "S_INFO_WINDCODE": ["000001.SZ", "000001.SZ"],
                "datetime": pd.to_datetime(["2018-01-04", "2021-01-04"]),
                "TRADE_DT": ["20180104", "20210104"],
                "cor_s_fa_operateincome_ashareincomehis": [100.0, 133.1],
            }
        )

        derived_features = [
            {
                "column": "revenue_cagr_3y",
                "type": "cagr",
                "base_column": "S_FA_OPERATEINCOME",
                "years": 3,
                "description": "营业收入3年复合增长率",
            }
        ]

        out = apply_derived_features(
            df=df,
            derived_features=derived_features,
            field_to_actual={"S_FA_OPERATEINCOME": "cor_s_fa_operateincome_ashareincomehis"},
        )

        self.assertIn("revenue_cagr_3y", out.columns)
        v = out.loc[out["TRADE_DT"] == "20210104", "revenue_cagr_3y"].iloc[0]
        self.assertAlmostEqual(v, 0.1, places=3)


if __name__ == "__main__":
    unittest.main()

