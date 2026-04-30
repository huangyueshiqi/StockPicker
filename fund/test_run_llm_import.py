import importlib
import sys
import unittest


class TestRunLlmImport(unittest.TestCase):
    def test_import_has_no_external_project_side_effects(self):
        sys.modules.pop("run_llm", None)
        m = importlib.import_module("run_llm")
        self.assertTrue(hasattr(m, "run_backtest"))


if __name__ == "__main__":
    unittest.main()

