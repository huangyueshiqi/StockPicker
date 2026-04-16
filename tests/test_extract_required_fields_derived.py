import unittest


class TestExtractRequiredFieldsDerived(unittest.TestCase):
    def test_extract_required_fields_replaces_derived_with_base(self):
        from tools.strategy_field_utils import extract_required_fields

        strategy_config = {
            "filters": [
                {"column": "revenue_cagr_3y", "type": "simple", "name": "x", "operator": ">", "threshold": 0.1, "description": "x"},
            ],
            "ranking": {"method": "simple", "name": "r", "column": "revenue_cagr_3y", "ascending": True, "scope": "market"},
            "derived_features": [
                {"column": "revenue_cagr_3y", "base_column": "S_FA_OPERATEINCOME", "type": "cagr", "years": 3, "description": "营业收入3年复合增长率"}
            ],
        }

        required = set(extract_required_fields(strategy_config))
        self.assertIn("S_FA_OPERATEINCOME", required)
        self.assertNotIn("revenue_cagr_3y", required)


if __name__ == "__main__":
    unittest.main()
