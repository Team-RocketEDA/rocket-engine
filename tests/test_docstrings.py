"""Docstring guard: enforced endpoints carry Google-style docstrings.

ADR-003 makes docstrings the API contract source: one text feeds
human docs, machine schemas, and MCP help. The guard fails loudly
on missing/malformed endpoint docstrings — same posture as the
no-cloud guard — naming the endpoint so the fix is mechanical.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_checker():
    # RED: scripts/check_docstrings.py does not exist yet.
    spec = importlib.util.spec_from_file_location(
        "check_docstrings", ROOT / "scripts" / "check_docstrings.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_enforced_files_have_google_docstrings():
    checker = _load_checker()
    violations = checker.scan(checker.enforced_files())
    assert violations == [], violations


def test_scanner_flags_bad_docstring_naming_endpoint(tmp_path):
    checker = _load_checker()
    planted = tmp_path / "bad_endpoint.py"
    planted.write_text(
        'def run_widget(widget, timeout_s=30):\n'
        '    """Run a widget."""\n'
        '    if timeout_s < 0:\n'
        '        raise ValueError("bad timeout")\n'
        '    return {"ok": True}\n',
        encoding="utf-8",
    )
    violations = checker.scan_file(planted)
    assert violations != []
    assert any(v[2] == "run_widget" for v in violations), violations


def test_scanner_accepts_good_docstring(tmp_path):
    checker = _load_checker()
    planted = tmp_path / "good_endpoint.py"
    planted.write_text(
        'def run_widget(widget, timeout_s=30):\n'
        '    """Run a widget to completion.\n'
        '\n'
        '    Args:\n'
        '        widget: Widget to run.\n'
        '        timeout_s: Timeout in seconds.\n'
        '\n'
        '    Returns:\n'
        '        Result mapping with run evidence.\n'
        '\n'
        '    Raises:\n'
        '        ValueError: If the timeout is negative.\n'
        '    """\n'
        '    if timeout_s < 0:\n'
        '        raise ValueError("bad timeout")\n'
        '    return {"ok": True}\n',
        encoding="utf-8",
    )
    assert checker.scan_file(planted) == [], checker.scan_file(planted)
