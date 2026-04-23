import os
import types
import unittest


class TestRunLlmCommand(unittest.TestCase):
    def test_build_run_llm_command_includes_required_flags(self):
        import qlib_premium_value_strategy as s

        args = types.SimpleNamespace(
            mode="llm",
            trade_file="abc.csv",
            output="",
            plot_output="plot/x.png",
            plot_trades=False,
            verbose=False,
            project_root="/tmp/backtester",
        )

        cmd = s.build_run_llm_command(args, python_executable="python", script_dir="/workspace")
        self.assertEqual(cmd[0], "python")
        self.assertEqual(cmd[1], os.path.join("/workspace", "run_llm.py"))
        self.assertIn("--mode", cmd)
        self.assertIn("llm", cmd)
        self.assertIn("--trade_file", cmd)
        self.assertIn("abc.csv", cmd)
        self.assertIn("--plot_output", cmd)
        self.assertIn("plot/x.png", cmd)
        self.assertIn("--project_root", cmd)
        self.assertIn("/tmp/backtester", cmd)
        self.assertNotIn("--plot_trades", cmd)
        self.assertNotIn("--verbose", cmd)

    def test_build_run_llm_command_includes_optional_flags(self):
        import qlib_premium_value_strategy as s

        args = types.SimpleNamespace(
            mode="llm",
            trade_file="abc.csv",
            output="out.txt",
            plot_output="plot/x.png",
            plot_trades=True,
            verbose=True,
            project_root="/tmp/backtester",
        )

        cmd = s.build_run_llm_command(args, python_executable="python", script_dir="/workspace")
        self.assertIn("--plot_trades", cmd)
        self.assertIn("--verbose", cmd)
        self.assertIn("--output", cmd)
        self.assertIn("out.txt", cmd)


if __name__ == "__main__":
    unittest.main()

