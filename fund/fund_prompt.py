import os
from typing import Callable, Optional, Tuple


def get_fund_prompt_and_dates(
    args,
    extract_rules_func: Optional[Callable] = None,
) -> Tuple[str, Optional[str], Optional[str]]:
    prompt = getattr(args, "prompt", "")
    fund_df_path = getattr(args, "fund_df_path", "")
    fund_features_file = getattr(args, "fund_features_file", "")
    fund_rule = getattr(args, "fund_rule", "")
    fund_rule_file = getattr(args, "fund_rule_file", "")

    if fund_rule_file and not fund_rule and os.path.exists(fund_rule_file):
        with open(fund_rule_file, "r", encoding="utf-8") as f:
            fund_rule = f.read().strip()

    fund_start_date = None
    fund_end_date = None

    if fund_rule:
        try:
            import pandas as pd
        except Exception:
            pd = None
        if fund_df_path and os.path.exists(fund_df_path) and pd is not None:
            try:
                df_fund = pd.read_csv(fund_df_path)
                if "datetime" in df_fund.columns:
                    dt = pd.to_datetime(df_fund["datetime"], errors="coerce")
                    if not dt.isna().all():
                        fund_start_date = dt.min().strftime("%Y%m%d")
                        fund_end_date = dt.max().strftime("%Y%m%d")
            except Exception:
                pass
        return fund_rule, fund_start_date, fund_end_date

    if fund_df_path and os.path.exists(fund_df_path) and fund_features_file and os.path.exists(fund_features_file):
        if extract_rules_func is None:
            raise ValueError("extract_rules_func is required when fund_rule is not provided")
        import pandas as pd

        df_fund = pd.read_csv(fund_df_path)
        if "datetime" in df_fund.columns:
            dt = pd.to_datetime(df_fund["datetime"], errors="coerce")
            if not dt.isna().all():
                fund_start_date = dt.min().strftime("%Y%m%d")
                fund_end_date = dt.max().strftime("%Y%m%d")
        pandas_rules = extract_rules_func(
            df_fund,
            top_features_file=fund_features_file,
            target_col="label",
            max_depth=5,
        )
        if pandas_rules and len(pandas_rules) > 0:
            return pandas_rules[0], fund_start_date, fund_end_date

    return prompt, fund_start_date, fund_end_date

