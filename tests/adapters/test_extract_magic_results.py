"""Extract_magic results RED — pure v1 ResultBundle normalizer.

Valid RED = `rocket_engine.adapters.extract_magic.results` does not
exist yet, so every test fails on ImportError. Fixtures are v0
magic-extraction parse shapes (two devices plus the empty cell);
the normalizer must map them to a schema-valid ResultBundle with
a devices table, a device-count measurement, and no findings on
clean extraction.
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
    "cell": "ota",
    "ext_file": "run/ota.ext",
    "spice_file": "run/ota.spice",
    "device_count": 2,
    "devices": [
        {
            "name": "XM1",
            "nets": ["vdd", "out", "vss", "vss"],
            "class": "nmos",
            "w": 2.0,
            "l": 0.13,
        },
        {
            "name": "XC1",
            "nets": ["out", "vss"],
            "class": "cap",
            "w": None,
            "l": None,
        },
    ],
    "violations": [],
}

EMPTY = {
    "cell": "filler",
    "ext_file": "run/filler.ext",
    "spice_file": "run/filler.spice",
    "device_count": 0,
    "devices": [],
    "violations": [],
}


def _normalize(parsed, **over):
    from rocket_engine.adapters.extract_magic.results import normalize

    params = {"run_id": "run-extract-good", "project_id": "analog_demo"}
    params.update(over)
    return normalize(parsed, **params)


def test_good_bundle_validates_and_carries_table(contract):
    """Extracted devices normalize to a valid bundle with a table."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    assert bundle["task"] == "run_extraction"
    tables = [d for d in bundle["datasets"] if d["kind"] == "table"]
    assert tables and tables[0]["row_count"] == 2
    assert bundle["findings"] == []
    ids = {d["id"] for d in bundle["datasets"]}
    assert bundle["views"]
    assert all(v["dataset_id"] in ids for v in bundle["views"])


def test_device_count_becomes_pass_measurement(contract):
    """The device count rides a PASS measurement with its value."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    by_name = {m["name"]: m for m in bundle["measurements"]}
    assert by_name["device_count"]["status"] == "PASS"
    assert by_name["device_count"]["value"]["value"] == pytest.approx(2.0)


def test_empty_cell_validates_with_empty_table(contract):
    """A device-free cell still validates with zero rows."""
    bundle = _normalize(EMPTY, run_id="run-extract-empty")
    assert not check(contract, bundle)
    tables = [d for d in bundle["datasets"] if d["kind"] == "table"]
    assert tables and tables[0]["row_count"] == 0
    by_name = {m["name"]: m for m in bundle["measurements"]}
    assert by_name["device_count"]["value"]["value"] == pytest.approx(0.0)


def test_table_rows_name_devices_and_classes(contract):
    """Every device row carries its name and class."""
    bundle = _normalize(GOOD, run_id="run-extract-rows")
    assert not check(contract, bundle)
    table = next(d for d in bundle["datasets"] if d["kind"] == "table")
    by_name = {c["name"]: c["data"] for c in table["columns"]}
    assert by_name["name"] == ["XM1", "XC1"]
    assert by_name["class"] == ["nmos", "cap"]


def test_bundles_are_deterministic(contract):
    """Repeat calls are byte-identical."""
    first = _normalize(GOOD, run_id="run-extract-det")
    second = _normalize(GOOD, run_id="run-extract-det")
    assert not check(contract, first)
    assert first == second
