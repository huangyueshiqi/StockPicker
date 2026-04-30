import os
import sys


def build_run_llm_command(args, python_executable: str = None, script_dir: str = None):
    if python_executable is None:
        python_executable = sys.executable

    if script_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))

    run_llm_path = os.path.join(script_dir, "run_llm.py")
    cmd = [
        python_executable,
        run_llm_path,
        "--mode",
        args.mode,
        "--trade_file",
        args.trade_file,
        "--plot_output",
        args.plot_output,
        "--project_root",
        args.project_root,
    ]

    if getattr(args, "output", ""):
        cmd.extend(["--output", args.output])

    if getattr(args, "plot_trades", False):
        cmd.append("--plot_trades")

    if getattr(args, "verbose", False):
        cmd.append("--verbose")

    return cmd

