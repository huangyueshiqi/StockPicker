import argparse
import tempfile
import unittest


class TestRuleOverride(unittest.TestCase):
    def test_rule_override_skips_extract_rules(self):
        from fund.fund_prompt import get_fund_prompt_and_dates

        with tempfile.TemporaryDirectory() as d:
            df_path = f"{d}/df.csv"
            feat_path = f"{d}/selected_features_80pct.csv"
            with open(df_path, "w", encoding="utf-8") as f:
                f.write("fund,instrument,datetime,label\n")
            with open(feat_path, "w", encoding="utf-8") as f:
                f.write("feature\n")

            called = {"n": 0}

            def _fake_extract(*args, **kwargs):
                called["n"] += 1
                return ["rule"]

            try:
                args = argparse.Namespace(
                    prompt="",
                    interactive=False,
                    fund_df_path=df_path,
                    fund_features_file=feat_path,
                    fund_rule="my_rule",
                    fund_rule_file="",
                )
                prompt, _, _ = get_fund_prompt_and_dates(args, extract_rules_func=_fake_extract)
                self.assertEqual(prompt, "my_rule")
                self.assertEqual(called["n"], 0)
            finally:
                pass


if __name__ == "__main__":
    unittest.main()
