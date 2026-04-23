import json
import os
from datetime import datetime
from typing import Any, Dict, Optional


def make_cache_id(now: Optional[datetime] = None) -> str:
    if now is None:
        now = datetime.now()
    return now.strftime("%Y%m%d_%H%M%S")


def latest_file_path(cache_root: str) -> str:
    return os.path.join(cache_root, "latest.txt")


def read_latest(cache_root: str) -> Optional[str]:
    p = latest_file_path(cache_root)
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        v = f.read().strip()
    return v or None


def write_latest(cache_root: str, cache_id: str) -> None:
    os.makedirs(cache_root, exist_ok=True)
    p = latest_file_path(cache_root)
    with open(p, "w", encoding="utf-8") as f:
        f.write(cache_id)


def write_meta(cache_dir: str, meta: Dict[str, Any]) -> None:
    os.makedirs(cache_dir, exist_ok=True)
    p = os.path.join(cache_dir, "meta.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

