"""Split lock for execution mega modules (REFACTOR-EXEC).

python_exec.py decomposes into a thin surface plus the pyexec
subpackage, and the console surface lives at console/session.py +
console/route.py with the routing subpackage — one word per module
level. The public API, __all__ re-exports, and the api_spec
docstring seam stay byte-identical.
"""

from pathlib import Path

import rocket_engine.execution as E
import rocket_engine.execution.console.route as cr
import rocket_engine.execution.python_exec as pe

SRC = Path(__file__).resolve().parents[2] / "src"


def _lines(path):
    return path.read_text().count("\n") + 1


def test_surfaces_under_limit():
    """Surfaces stay under 1000 lines."""
    for name in ("python_exec.py",):
        n = _lines(SRC / "execution" / name)
        assert n < 1000, f"{name} has {n} lines"


def test_subpackages_exist_and_small():
    """Each split module exists and stays under 1000 lines."""
    for rel in (
        "pyexec/__init__.py", "pyexec/support.py", "pyexec/runner.py",
        "pyexec/approvals.py", "routing/__init__.py", "routing/calls.py",
        "routing/namespace.py", "routing/tools.py",
        "console/__init__.py", "console/session.py", "console/route.py",
    ):
        path = SRC / "execution" / rel
        assert path.exists(), f"missing {path}"
        n = _lines(path)
        assert n < 1000, f"{path} has {n} lines"


def test_pyexec_api_intact():
    """Every __all__ name still imports from python_exec."""
    for name in pe.__all__:
        assert hasattr(pe, name), name
    assert callable(pe.PythonExecService.request_execution)
    assert callable(pe.PythonExecRunner.run)
    assert "Approval" in (pe.PythonExecService.request_execution.__doc__ or "")


def test_console_api_intact():
    """Every __all__ name still imports from console_route."""
    for name in cr.__all__:
        assert hasattr(cr, name), name
    assert callable(cr.ConsoleNamespace.write_doc)
    assert callable(cr.ConsoleTools.write_doc)


def test_package_reexports_intact():
    """execution/__init__ still re-exports both surfaces."""
    for name in (
        "MCP_INPUT_SCHEMA", "PythonExecRunner", "PythonExecService",
        "build_worker_source", "ConsoleNamespace", "ConsoleTools",
        "admission_envelope", "TIER_2_OPERATIONS",
    ):
        assert hasattr(E, name), name
