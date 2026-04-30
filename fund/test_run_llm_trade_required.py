import subprocess
import unittest


class TestRunLlmTradeRequired(unittest.TestCase):
    def test_cli_requires_trade_file(self):
        p = subprocess.run(["python", "/workspace/run_llm.py", "--project_root", "/tmp/x"], capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("--trade_file", (p.stderr or "") + (p.stdout or ""))


if __name__ == "__main__":
    unittest.main()

