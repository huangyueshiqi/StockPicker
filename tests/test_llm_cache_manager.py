import json
import os
import tempfile
import unittest
from datetime import datetime


class TestLlmCacheManager(unittest.TestCase):
    def test_make_cache_id_from_fixed_time(self):
        from framework.llm_cache_manager import make_cache_id

        cid = make_cache_id(now=datetime(2026, 4, 15, 16, 25, 39))
        self.assertEqual(cid, "20260415_162539")

    def test_latest_roundtrip(self):
        from framework.llm_cache_manager import read_latest, write_latest

        with tempfile.TemporaryDirectory() as d:
            cache_root = os.path.join(d, "llm_cache")
            os.makedirs(cache_root, exist_ok=True)
            self.assertIsNone(read_latest(cache_root))

            write_latest(cache_root, "20260415_162539")
            self.assertEqual(read_latest(cache_root), "20260415_162539")

    def test_write_meta(self):
        from framework.llm_cache_manager import write_meta

        with tempfile.TemporaryDirectory() as d:
            cache_dir = os.path.join(d, "20260415_162539")
            os.makedirs(cache_dir, exist_ok=True)
            write_meta(cache_dir, {"cache_id": "20260415_162539", "prompt": "x"})
            with open(os.path.join(cache_dir, "meta.json"), "r", encoding="utf-8") as f:
                meta = json.load(f)
            self.assertEqual(meta["cache_id"], "20260415_162539")
            self.assertEqual(meta["prompt"], "x")


if __name__ == "__main__":
    unittest.main()

