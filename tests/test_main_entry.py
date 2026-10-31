"""`python -m rocket_engine` entrypoint: thin alias over adapters.cli."""

import subprocess
import sys


def test_main_entrypoint_exposes_cli_help():
    proc = subprocess.run(
        [sys.executable, "-m", "rocket_engine", "--help"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0
    assert "usage" in proc.stdout.lower()
