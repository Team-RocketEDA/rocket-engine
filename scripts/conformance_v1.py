#!/usr/bin/env python3
"""Run the v1 conformance gate: contract plus consumer/provider proof.

Runs scripts/check_v1_contract.py (no writes; stale artifacts fail)
then the owned v1 suites: tests/test_v1_clients_runtime.py,
tests/test_v1_tools_binding.py, and
contracts/conformance/test_v1_conformance.py. The suites execute
against the working tree through a temporary package shim, so no
install or site-packages sync is needed.

Usage: .venv/bin/python scripts/conformance_v1.py [-- pytest args]
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITES = [
    "tests/test_v1_clients_runtime.py",
    "tests/test_v1_tools_binding.py",
    "contracts/conformance/test_v1_conformance.py",
]


def run_contract():
    """Check the canonical v1 boundary without writing artifacts.

    Returns:
        Completed process for the contract checker.
    """
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_v1_contract.py")],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )


def run_suites(extra):
    """Run the v1 suites against the working tree.

    Args:
        extra: Extra pytest arguments appended after the suite paths.

    Returns:
        Completed process for the pytest run.
    """
    with tempfile.TemporaryDirectory(prefix="v1-tree-pkg-") as shim:
        link = Path(shim) / "rocket_engine"
        try:
            link.symlink_to(ROOT / "src", target_is_directory=True)
        except FileExistsError:
            pass
        env = dict(os.environ)
        env["PYTHONPATH"] = shim + os.pathsep + env.get("PYTHONPATH", "")
        return subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *SUITES, *extra],
            cwd=ROOT, env=env, capture_output=True, text=True, check=False,
        )


def main(argv=None):
    """Run the contract gate then the v1 suites and report.

    Args:
        argv: Extra pytest arguments after the suite paths.

    Returns:
        Process exit status: 0 only when the contract and every
            suite pass.
    """
    extra = list(argv) if argv is not None else []
    contract = run_contract()
    print(contract.stdout, end="")
    print(contract.stderr, end="", file=sys.stderr)
    if contract.returncode != 0:
        print("V1 CONFORMANCE: contract gate FAILED")
        return contract.returncode
    suites = run_suites(extra)
    print(suites.stdout, end="")
    print(suites.stderr, end="", file=sys.stderr)
    if suites.returncode != 0:
        print("V1 CONFORMANCE: suites FAILED")
        return suites.returncode
    print("V1 CONFORMANCE: green "
          f"({len(SUITES)} suites, contract gate green)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
