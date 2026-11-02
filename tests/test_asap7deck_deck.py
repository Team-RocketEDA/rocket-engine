"""ASAP7-DRC-DECK: our deck through the KLayout DRC adapter deck mode.

The adapter is used UNCHANGED: preflight must accept the lane deck
without synthetic rules, and parse(execute(job)) must report per-rule
violations from the report database. Every breaker trips exactly its
rule (plus documented geometric companions, if any); the synthetic
clean ref, the empty control, and the INVx1 PDK cell stay marker-free.
Fixtures are generated at session scope from the committed fixture
spec via klayout; tests skip (never fake-green) where klayout or the
spec is absent — except the deck-presence test, which is the RED gate.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LANE = REPO_ROOT / "docs" / "work" / "ASAP7-DRC-DECK"
DECK = LANE / "asap7.drc"
SPEC = LANE / "fixtures" / "spec.json"
MAKE_FIXTURES = LANE / "fixtures" / "make_fixtures.py"
INVX1 = REPO_ROOT / "tests" / "pdk_asap7" / "fixtures" / "invx1_r.gds"

klayout_present = shutil.which("klayout") is not None
needs_klayout = pytest.mark.skipif(not klayout_present, reason="klayout not installed")


def _read_spec():
    if not SPEC.is_file():
        raise FileNotFoundError(f"fixture spec not found: {SPEC}.")
    return json.loads(SPEC.read_text())


def _breaker_ids():
    try:
        return [entry["id"] for entry in _read_spec()["breakers"]]
    except FileNotFoundError:
        return ["spec-missing"]


def _job(gds_file, workdir):
    return {
        "operation": "run_drc",
        "tech": "asap7",
        "gds_file": str(gds_file),
        "workdir": str(workdir),
        "deck": {"tool": "klayout"},
        "deck_file": str(DECK),
    }


@pytest.fixture(scope="module")
def fixture_dir(tmp_path_factory):
    if not klayout_present:
        pytest.skip("klayout not installed")
    if not MAKE_FIXTURES.is_file():
        raise FileNotFoundError(f"fixture generator not found: {MAKE_FIXTURES}.")
    spec = _read_spec()
    outdir = tmp_path_factory.mktemp("asap7deck_gds")
    proc = subprocess.run(
        ["klayout", "-b", "-r", str(MAKE_FIXTURES)],
        capture_output=True, text=True, timeout=300, cwd=outdir,
        env={"PATH": "/usr/bin:/bin", "SPEC_PATH": str(SPEC),
              "OUT_DIR": str(outdir)},
    )
    assert proc.returncode == 0, proc.stderr
    want = {f"{e['id']}.gds" for e in spec["breakers"] + spec["cleans"]}
    missing = sorted(n for n in want if not (outdir / n).is_file())
    assert not missing, f"generator did not emit: {missing}"
    return outdir


def test_deck_file_present():
    assert DECK.is_file(), f"lane deck missing: {DECK}"


@needs_klayout
def test_preflight_accepts_deck_without_rules(tmp_path, fixture_dir):
    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

    workdir = tmp_path / "work"
    workdir.mkdir()
    gds = workdir / "empty.gds"
    shutil.copy(fixture_dir / "empty.gds", gds)
    checked = KlayoutDrcAdapter().preflight(_job(gds, workdir))
    assert checked.get("deck_file") == str(DECK)


@needs_klayout
@pytest.mark.parametrize("breaker_id", _breaker_ids())
def test_breaker_trips_exactly_its_rule(tmp_path, fixture_dir, breaker_id):
    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

    spec = _read_spec()
    entries = {entry["id"]: entry for entry in spec["breakers"]}
    assert breaker_id in entries, f"breaker {breaker_id} not in spec"
    entry = entries[breaker_id]
    allowed = {entry["rule"]} | set(entry.get("also", []))
    workdir = tmp_path / "work"
    workdir.mkdir()
    gds = workdir / f"{breaker_id}.gds"
    shutil.copy(fixture_dir / f"{breaker_id}.gds", gds)
    adapter = KlayoutDrcAdapter()
    result = adapter.parse(adapter.execute(_job(gds, workdir)))
    assert result["total"] >= 1, f"{breaker_id}: expected violations, got none"
    rules = {v["rule"] for v in result["violations"]}
    assert entry["rule"] in rules, f"{breaker_id}: {entry['rule']} not in {rules}"
    assert rules <= allowed, f"{breaker_id}: stray rules {rules - allowed}"


@needs_klayout
@pytest.mark.parametrize("clean_id", ["clean_all", "empty"])
def test_clean_refs_marker_free(tmp_path, fixture_dir, clean_id):
    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

    workdir = tmp_path / "work"
    workdir.mkdir()
    gds = workdir / f"{clean_id}.gds"
    shutil.copy(fixture_dir / f"{clean_id}.gds", gds)
    adapter = KlayoutDrcAdapter()
    result = adapter.parse(adapter.execute(_job(gds, workdir)))
    assert result["total"] == 0, result["violations"]
    assert result["violations"] == []


@needs_klayout
def test_invx1_cell_marker_free(tmp_path):
    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

    if not INVX1.is_file():
        pytest.skip("invx1 fixture not present")
    workdir = tmp_path / "work"
    workdir.mkdir()
    gds = workdir / "invx1_r.gds"
    shutil.copy(INVX1, gds)
    adapter = KlayoutDrcAdapter()
    result = adapter.parse(adapter.execute(_job(gds, workdir)))
    assert result["total"] == 0, result["violations"]


@needs_klayout
def test_oracle_raw_klayout_breaker_and_clean(tmp_path, fixture_dir):
    # Oracle check: labels verified against klayout + our deck directly,
    # not against the adapter under test.
    spec = _read_spec()
    first = spec["breakers"][0]
    for name, want_items, want_rule in (
        (f"{first['id']}.gds", None, first["rule"]),
        ("clean_all.gds", 0, None),
    ):
        report = tmp_path / f"oracle_{name}.lyrdb"
        proc = subprocess.run(
            ["klayout", "-b",
             "-rd", f"input={fixture_dir / name}",
             "-rd", f"report={report}",
             "-r", str(DECK)],
            capture_output=True, text=True, timeout=120, cwd=tmp_path,
        )
        assert proc.returncode == 0
        assert report.is_file()
        text = report.read_text()
        if want_items is not None:
            assert text.count("<item>") == want_items
        else:
            assert text.count("<item>") >= 1
        if want_rule:
            assert want_rule in text
