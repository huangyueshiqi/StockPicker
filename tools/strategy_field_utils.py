from typing import Dict, List


def extract_required_fields(strategy_config: Dict) -> List[str]:
    derived = strategy_config.get("derived_features") or []
    derived_col_to_base = {}
    for d in derived:
        col = d.get("column")
        base = d.get("base_column")
        if col and base:
            derived_col_to_base[col] = base

    required_fields = set()

    for f in strategy_config.get("filters", []):
        col = f.get("column")
        if not col:
            continue
        required_fields.add(derived_col_to_base.get(col, col))

    ranking = strategy_config.get("ranking", {}) or {}
    col = ranking.get("column")
    if col:
        required_fields.add(derived_col_to_base.get(col, col))

    for comp in ranking.get("components", []) or []:
        c = comp.get("column")
        if c:
            required_fields.add(derived_col_to_base.get(c, c))

    required_fields.add("close")

    excluded_fields = {"NAME"}
    required_fields = {f for f in required_fields if f not in excluded_fields}

    return list(required_fields)

