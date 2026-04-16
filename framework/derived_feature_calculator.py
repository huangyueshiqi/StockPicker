from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


def apply_derived_features(
    df: pd.DataFrame,
    derived_features: List[Dict[str, Any]],
    field_to_actual: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    if df is None or df.empty or not derived_features:
        return df

    if field_to_actual is None:
        field_to_actual = {}

    out = df.copy()
    if "datetime" not in out.columns or "S_INFO_WINDCODE" not in out.columns:
        return out

    for spec in derived_features:
        if spec.get("type") != "cagr":
            continue

        col = spec.get("column")
        base_col = spec.get("base_column")
        years = int(spec.get("years") or 0)
        if not col or not base_col or years <= 0:
            continue

        base_actual = field_to_actual.get(base_col, base_col)
        if base_actual not in out.columns:
            continue

        s = out[["S_INFO_WINDCODE", "datetime", base_actual]].copy()
        s = s.dropna(subset=[base_actual])
        s = s.sort_values(["S_INFO_WINDCODE", "datetime"])

        past = s.rename(columns={base_actual: "_past_val"})
        past.loc[:, "datetime"] = past["datetime"] + pd.DateOffset(years=years)

        merged = pd.merge_asof(
            s,
            past,
            on="datetime",
            by="S_INFO_WINDCODE",
            direction="backward",
        )

        cur = merged[base_actual].astype(float)
        prev = merged["_past_val"].astype(float)

        with np.errstate(divide="ignore", invalid="ignore"):
            cagr = np.power(cur / prev, 1.0 / years) - 1.0

        cagr[(prev <= 0) | (cur <= 0)] = np.nan

        merged.loc[:, col] = cagr
        merged = merged[["S_INFO_WINDCODE", "datetime", col]]

        out = pd.merge(out, merged, on=["S_INFO_WINDCODE", "datetime"], how="left")

    return out
