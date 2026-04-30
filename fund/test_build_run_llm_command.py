import argparse
import unittest


class TestBuildRunLlmCommand(unittest.TestCase):
    def test_build_run_llm_command_is_used(self):
        import backtest_subprocess as mod

        args = argparse.Namespace(
            mode="llm",
            trade_file="t.csv",
            plot_output="p.png",
            project_root="/tmp/backtrader_test",
            output="o.log",
            plot_trades=False,
            verbose=False,
        )
        cmd = mod.build_run_llm_command(args, python_executable="python", script_dir="/workspace")
        self.assertEqual(cmd[0], "python")
        self.assertTrue(cmd[1].endswith("/run_llm.py"))
        self.assertIn("--trade_file", cmd)
        self.assertIn("t.csv", cmd)


if __name__ == "__main__":
    unittest.main()
