"""Syntax results RED — pure v1 ResultBundle normalizer.

Valid RED = `rocket_engine.adapters.syntax.results` does not exist
yet, so every test fails on ImportError. Fixtures are v0 parse
shapes (warnings-only plus an error diagnostic); the normalizer
must map them to a schema-valid ResultBundle with a diagnostics
table, bound views, and findings per diagnostic.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "v1_contract", ROOT / "scripts/check_v1_contract.py"
)
CONTRACT_MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT_MOD)


@pytest.fixture(scope="module")
def contract():
    """Load the one canonical v1 contract bundle."""
    return CONTRACT_MOD.load_contract()


def check(contract, value):
    """Collect ResultBundle schema errors for one bundle."""
    return list(
        CONTRACT_MOD.validator(contract, "#/$defs/ResultBundle").iter_errors(
            value
        )
    )


GOOD = {
    "total": 1,
    "violations": [
        {
            "rule": "-Wunused",
            "severity": "warning",
            "message": "unused signal `tmp` [-Wunused]",
            "file": "top.sv",
            "line": 8,
            "col": 9,
        },
    ],
}

BAD = {
    "total": 2,
    "violations": [
        {
            "rule": "-Werror",
            "severity": "error",
            "message": "unknown module `missing` [-Werror]",
            "file": "top.sv",
            "line": 3,
            "col": 5,
        },
        {
            "rule": "-Wunused",
            "severity": "warning",
            "message": "unused signal `tmp` [-Wunused]",
            "file": "top.sv",
            "line": 8,
            "col": 9,
        },
    ],
}


def _normalize(parsed, **over):
    from rocket_engine.adapters.syntax.results import normalize

    params = {"run_id": "run-syntax-good", "project_id": "digital_demo"}
    params.update(over)
    return normalize(parsed, **params)


def test_warnings_only_bundle_validates(contract):
    """Warnings-only lint normalizes to a valid diagnostics bundle."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    assert bundle["task"] == "run_syntax"
    tables = [d for d in bundle["datasets"] if d["kind"] == "table"]
    assert tables and tables[0]["row_count"] == 1
    ids = {d["id"] for d in bundle["datasets"]}
    assert bundle["views"]
    assert all(v["dataset_id"] in ids for v in bundle["views"])


def test_errors_surface_as_error_findings(contract):
    """Error diagnostics normalize to error findings, never clean."""
    bundle = _normalize(BAD, run_id="run-syntax-bad")
    assert not check(contract, bundle)
    errors = [f for f in bundle["findings"] if f["severity"] == "error"]
    assert len(errors) == 1
    assert len(bundle["findings"]) == 2


def test_diagnostics_capped_and_deterministic(contract):
    """Long tool text is capped and repeat calls are byte-identical."""
    parsed = {
        "total": 1,
        "violations": [
            {
                "rule": "-Werror",
                "severity": "error",
                "message": "z" * 6000,
                "file": "top.sv",
                "line": 1,
                "col": 1,
            },
        ],
    }
    first = _normalize(parsed, run_id="run-syntax-cap")
    assert not check(contract, first)
    assert first == _normalize(parsed, run_id="run-syntax-cap")
    assert all(len(f["message"]) <= 240 for f in first["findings"])
