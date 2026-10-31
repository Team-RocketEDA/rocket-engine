"""VALIDATE-A RED — analog correctness end-to-end (sky130-bandgap).

Valid RED = the vendored bandgap operators do not exist yet in
`rocket_engine.mutate` (KeyError), the shared staging helpers
reject "bandgap" (KeyError), and the ngspice_bandgap scenario
backend ignores mutations — so every operator/staging test below
fails while the oracle/canned tests prove the parse path without
the binary.

Correct = the designer's documented numbers. sky130-bandgap
(2amlogic): DR-005 ratifies Output reference 1.20 V +/-2%
untrimmed => [1.176, 1.224] V over -40..125 C
(spec/decision-records/DR-005-ratify-target-spec.md, README
target-spec table). The signoff envelope
sim/signoff-envelopes/output-voltage-tc.1a.klt-sim.json records
45/45 PASS on that window (worst vref_27 1.212093 at
sf_-40c_3.63v, vref_min 1.186028 at fs_-40c_3.30v, vref_max
1.217801 at fs_-40c_3.63v). The recorded corner log
sim/output-voltage-tc/corners/20260817-015751-13476b7/tt_27c_3.30v.log
gives vref_27 1.210323, vref_min 1.186357, vref_max 1.216902
(ngspice-47, tt / 27 C / 3.30 V). measurements/ holds only
.gitkeep until tape-out — the spec + signoff envelope are the
source, not silicon. Each vendored mutation must flip its e2e to
FAIL with measurement and only it. Corners beyond tt/27/3.3 are
stretch (docs/tickets/VALIDATE-A.md).
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
BANDGAP = ROOT / "fixtures" / "upstream" / "sky130-bandgap"
SNAPSHOT = (
    BANDGAP
    / "sim"
    / "output-voltage-tc"
    / "netlist-snapshots"
    / "20260817-015751-13476b7.spice"
)
RECORDED_LOG = (
    BANDGAP
    / "sim"
    / "output-voltage-tc"
    / "corners"
    / "20260817-015751-13476b7"
    / "tt_27c_3.30v.log"
)
ENVELOPE_1A = BANDGAP / "sim" / "signoff-envelopes" / "output-voltage-tc.1a.klt-sim.json"
ARTIFACTS = ROOT / "tmp" / "validate-a"

# DR-005 ratified accuracy row: 1.20 V +/-2% untrimmed.
VREF_MIN = 1.176
VREF_MAX = 1.224

# Recorded tt_27c_3.30v oracle (ngspice-47, envelope 1a + corner log).
ORACLE_VREF_27 = 1.210323
ORACLE_VREF_MIN = 1.186357
ORACLE_VREF_MAX = 1.216902

BANDGAP_OP_SEEDS = {
    "bandgap_sizing_out_of_spec": [0, 1, 2],
    "bandgap_open_net": [0, 1],
}

SNAPSHOT_NAME = "20260817-015751-13476b7.spice"


def _require_bandgap():
    if not SNAPSHOT.is_file():
        pytest.skip(
            "VALIDATE-A live: sky130-bandgap fixture not fetched "
            "(scripts/fetch_fixtures.py; docs/tickets/VALIDATE-A.md)"
        )


def _require_ngspice():
    if shutil.which("ngspice") is None:
        pytest.skip(
            "VALIDATE-A live: ngspice not on PATH "
            "(see docs/tickets/NGSPICE-LIVE.md)"
        )


def _require_pdk():
    try:
        from rocket_engine.interfaces.paths import slugify
        from rocket_engine.interfaces.pdks import list_pdks, resolve_deck
    except Exception as exc:
        pytest.skip(
            "VALIDATE-A live: pdk store unavailable "
            f"({exc}; see docs/tickets/NGSPICE-LIVE.md)"
        )
    try:
        entries = list_pdks()
    except Exception as exc:
        pytest.skip(
            "VALIDATE-A live: sky130 PDK not registered "
            f"({exc}; set ROCKETEDA_HOME; see docs/tickets/NGSPICE-LIVE.md)"
        )
    cands = [e for e in entries
             if slugify(e.get("id") or "") == "sky130a"]
    if not cands:
        pytest.skip(
            "VALIDATE-A live: sky130 PDK not registered "
            "(set ROCKETEDA_HOME to a store with sky130A; "
            "see docs/tickets/NGSPICE-LIVE.md)"
        )
    entry = sorted(cands, key=lambda e: e["revision"])[0]
    try:
        resolve_deck(
            entry["id"], entry["revision"], "libs.tech/combined/sky130.lib.spice"
        )
    except Exception as exc:
        pytest.skip(
            "VALIDATE-A live: sky130 model lib not resolvable "
            f"({exc}; see docs/tickets/NGSPICE-LIVE.md)"
        )
    return entry


def _engine_run(project, operation, arguments):
    from rocket_engine.composition import Engine

    engine = Engine(project, actor="validate-a")
    out = engine.run(
        {"project_id": project, "operation": operation, "arguments": arguments}
    )
    return engine, out


def _stage_good(dest):
    # RED: stage_good_design rejects "bandgap" (KeyError).
    from rocket_engine.mutate import stage_good_design

    return stage_good_design("bandgap", dest, ROOT)


def _stage_mut(operator, dest, seed):
    # RED: vendored operators are not in the registry yet.
    from rocket_engine.mutate import OPERATORS, apply_operator, stage_design_extras

    entry = OPERATORS[operator]
    apply_operator(operator, dest, seed, ROOT / entry["base"])
    return stage_design_extras(entry["design"], dest, ROOT)


def _job(staged, pdk_entry):
    return {
        "operation": "run_spice",
        "sources": staged["sources"],
        "workdir": staged["workdir"],
        "timeout_s": staged["timeout_s"],
        "measurements": staged["measurements"],
        "analyses": staged["analyses"],
        "options": staged["options"],
        "params": staged["params"],
        "corner": staged["corner"],
        "temp_c": staged["temp_c"],
        "pdk": {"id": pdk_entry["id"], "revision": pdk_entry["revision"]},
        "deck": {"tool": "ngspice"},
    }


def _canon_findings(findings):
    canon = []
    for finding in findings:
        location = dict(finding.get("location") or {})
        if "file" in location:
            location["file"] = Path(location["file"]).name
        canon.append(
            (
                finding.get("rule"),
                finding.get("severity"),
                finding.get("message"),
                sorted(location.items()),
            )
        )
    return sorted(canon)


def _fixture_pin():
    note = ROOT / "fixtures" / "upstream" / "sky130-bandgap.md"
    rev = None
    if note.is_file():
        for line in note.read_text().splitlines():
            if "pinned rev:" in line:
                rev = line.split("`")[1]
    head = None
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        cwd=BANDGAP,
    )
    if proc.returncode == 0:
        head = proc.stdout.strip()
    return rev, head


def _tool_versions():
    versions = {}
    found = shutil.which("ngspice")
    versions["ngspice"] = found or "absent"
    if found:
        try:
            proc = subprocess.run(
                ["ngspice", "--version"], capture_output=True, text=True, timeout=30
            )
            versions["ngspice"] = (proc.stdout + proc.stderr).splitlines()[0][:120]
        except Exception:
            pass
    return versions


def _write_artifacts(case, *, verdict, findings, native, staged, mutation, pdk_entry):
    case_dir = ARTIFACTS / case
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "verdict.json").write_text(
        json.dumps(
            {"verdict": verdict, "findings": findings}, indent=2, sort_keys=True
        )
        + "\n"
    )
    (case_dir / "native.log").write_text(
        "=== deck ===\n"
        + (native.get("deck") or "")
        + "\n=== stdout ===\n"
        + (native.get("stdout") or "")
        + "\n=== stderr ===\n"
        + (native.get("stderr") or "")
        + "\n=== log ===\n"
        + (native.get("log") or "")
    )
    pinned, head = _fixture_pin()
    sources = []
    for path in staged["sources"]:
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        sources.append({"name": Path(path).name, "sha256": digest})
    try:
        from rocket_engine.interfaces.pdks import pdk_ingredient

        pdk_ing = pdk_ingredient(pdk_entry["id"], pdk_entry["revision"])
    except Exception:
        pdk_ing = {"pdk_id": pdk_entry["id"], "pdk_revision": pdk_entry["revision"]}
    record = {
        "case": case,
        "design": "bandgap",
        "engine": {"operation": "run_spice", "project_id": "validate-a"},
        "ingredients": {
            "fixture": {"pinned_rev": pinned, "actual_head": head},
            "sources": sorted(sources, key=lambda s: s["name"]),
            "measurements": staged["measurements"],
            "analyses": staged["analyses"],
            "options": staged["options"],
            "params": staged["params"],
            "corner": staged["corner"],
            "temp_c": staged["temp_c"],
            "solver": {"tool": "ngspice", **_tool_versions()},
            "pdk": pdk_ing,
            "mutation": mutation,
        },
        "results": {"verdict": verdict, "findings": findings},
    }
    (case_dir / "run_record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    )
    return case_dir


def _spice_measurements():
    return [
        {
            "name": "vref",
            "expr": "v(vref)",
            "unit": "V",
            "min": VREF_MIN,
            "max": VREF_MAX,
        }
    ]


# Good-matches-documented: bandgap Vref through the engine.
#
# Live where ngspice + the sky130 store exist; otherwise the
# oracle + canned tests below pin the parse path and this skips
# LOUDLY with the NGSPICE-LIVE ref (never fake-green).


def test_bandgap_good_matches_documented_outcome(tmp_path):
    from rocket_engine.adapters.ngspice import NgspiceAdapter

    _require_bandgap()
    # RED: staging rejects "bandgap" before any tool check runs.
    staged = _stage_good(tmp_path / "good")
    _require_ngspice()
    pdk_entry = _require_pdk()
    assert staged["measurements"][0]["min"] == VREF_MIN
    assert staged["measurements"][0]["max"] == VREF_MAX
    engine, out = _engine_run("validate_a_good", "run_spice", _job(staged, pdk_entry))
    assert out["verdict"]["status"] == "PASS", out["verdict"]
    assert engine.findings(out["run_id"])["findings"] == []
    native = NgspiceAdapter().execute(_job(staged, pdk_entry))
    result = NgspiceAdapter().parse(native)
    assert result["total"] == 0, result["violations"]
    value = result["measurements"][0]["value"]
    assert VREF_MIN <= value <= VREF_MAX, value
    assert value == pytest.approx(1.21, abs=0.02)


def test_bandgap_oracle_parses_recorded_log_verbatim():
    # Oracle check (SIM-SKY130 precedent): parse proven against
    # real ngspice-47 output from the vendored record, not against
    # the adapter's own staging. Runs without the binary.
    from rocket_engine.adapters.ngspice import NgspiceAdapter

    _require_bandgap()
    if not RECORDED_LOG.is_file():
        pytest.skip(
            "VALIDATE-A oracle: recorded corner log absent "
            "(fixtures/upstream/sky130-bandgap; docs/tickets/VALIDATE-A.md)"
        )
    text = RECORDED_LOG.read_text()
    stdout = text.split("# ==== ngspice stdout ====")[1].split(
        "# ==== ngspice stderr ===="
    )[0]
    measurements = [
        {"name": "vref_27", "expr": "vref27", "unit": "V",
         "min": VREF_MIN, "max": VREF_MAX},
        {"name": "vref_min", "expr": "minimum(v(vref))", "unit": "V",
         "min": VREF_MIN, "max": VREF_MAX},
        {"name": "vref_max", "expr": "maximum(v(vref))", "unit": "V",
         "min": VREF_MIN, "max": VREF_MAX},
    ]
    native = {
        "exit_code": 0,
        "stdout": stdout,
        "stderr": "",
        "log": "",
        "deck": "ngspice_deck.spice",
        "sources": [str(SNAPSHOT)],
        "measurements": measurements,
    }
    result = NgspiceAdapter().parse(native)
    assert result["total"] == 0, result["violations"]
    by_name = {m["name"]: m for m in result["measurements"]}
    assert by_name["vref_27"]["value"] == pytest.approx(ORACLE_VREF_27, abs=1e-5)
    assert by_name["vref_min"]["value"] == pytest.approx(ORACLE_VREF_MIN, abs=1e-5)
    assert by_name["vref_max"]["value"] == pytest.approx(ORACLE_VREF_MAX, abs=1e-5)


def test_bandgap_signoff_envelope_1a_passes():
    # The designer's own 45/45 PASS on DR-005 [1.176, 1.224] V —
    # quoted here so the engine window is tied to fixture bytes.
    _require_bandgap()
    if not ENVELOPE_1A.is_file():
        pytest.skip(
            "VALIDATE-A envelope: signoff envelope 1a absent "
            "(fixtures/upstream/sky130-bandgap; docs/tickets/VALIDATE-A.md)"
        )
    envelope = json.loads(ENVELOPE_1A.read_text())
    assert envelope["status"] == "pass"
    assert envelope["passed"] == 45 and envelope["failed"] == 0
    for meas in envelope["measurements"]:
        assert meas["limits"] == {"min": VREF_MIN, "max": VREF_MAX}, meas
        assert meas["status"] == "pass", meas
    by_name = {m["name"]: m for m in envelope["measurements"]}
    assert by_name["vref_27"]["worst_case"]["value"] == pytest.approx(
        1.212093, abs=1e-6
    )
    assert by_name["vref_min"]["worst_case"]["value"] == pytest.approx(
        1.186028, abs=1e-6
    )
    assert by_name["vref_max"]["worst_case"]["value"] == pytest.approx(
        1.217801, abs=1e-6
    )


def test_bandgap_measurements_dir_empty_until_tapeout():
    # measurements/ is silicon, not sim: only .gitkeep today. The
    # spec + signoff envelope above are the documented source.
    _require_bandgap()
    measurements = BANDGAP / "measurements"
    names = sorted(p.name for p in measurements.iterdir())
    assert names == [".gitkeep"], names


# Mutation-flips-only-target: file level (no tool needed).


def _op_params(table):
    return [(op, seed) for op, seeds in table.items() for seed in seeds]


@pytest.mark.parametrize("operator,seed", _op_params(BANDGAP_OP_SEEDS))
def test_bandgap_mutation_targets_vendored_site(operator, seed, tmp_path):
    from rocket_engine.mutate import OPERATORS, apply_operator

    _require_bandgap()
    assert OPERATORS[operator]["operation"] == "run_spice"
    assert OPERATORS[operator]["expected_verdict"] == "FAIL"
    assert OPERATORS[operator]["expected_rules"] == ["measurement"]
    dest = tmp_path / "mut"
    evidence = apply_operator(operator, dest, seed, BANDGAP / "sim"
                              / "output-voltage-tc" / "netlist-snapshots")
    assert evidence["operator"] == operator
    assert evidence["seed"] == seed
    assert evidence["target_file"] == SNAPSHOT_NAME
    staged = dest / evidence["target_file"]
    assert staged.is_file()
    base = SNAPSHOT
    assert staged.read_bytes() != base.read_bytes()
    text = staged.read_text()
    if operator == "bandgap_sizing_out_of_spec":
        assert ".param n_r2=51" not in text
        assert f".param n_r2={evidence['n_r2']}" in text
    else:
        assert "VOUT_OPEN" in text or text.count("\nXR2A ") == 0


def test_bandgap_operator_files_match_snapshot():
    from rocket_engine.mutate import OPERATORS

    for operator in BANDGAP_OP_SEEDS:
        assert OPERATORS[operator]["files"] == [SNAPSHOT_NAME], operator
        assert OPERATORS[operator]["design"] == "bandgap", operator


# Canned-parse proofs (no tool needed): the verdict mapping is
# pinned even where ngspice is absent (NGSPICE-LIVE quarantine).


def test_bandgap_parse_good_passes_canned():
    from rocket_engine.adapters.ngspice import NgspiceAdapter

    native = {
        "exit_code": 0,
        "stdout": f"meas_vref = {ORACLE_VREF_27}e+00\n",
        "stderr": "",
        "log": "",
        "deck": "ngspice_deck.spice",
        "sources": [SNAPSHOT_NAME],
        "measurements": _spice_measurements(),
    }
    result = NgspiceAdapter().parse(native)
    assert result["total"] == 0
    assert result["measurements"][0]["status"] == "pass"


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_bandgap_parse_mutated_sizing_fails_canned(tmp_path, seed):
    from rocket_engine.adapters.ngspice import NgspiceAdapter
    from rocket_engine.mutate import apply_operator

    _require_bandgap()
    src = BANDGAP / "sim" / "output-voltage-tc" / "netlist-snapshots"
    evidence, _ = (apply_operator(
        "bandgap_sizing_out_of_spec", tmp_path / "mut", seed, src
    ), None)
    assert evidence["expected_vref"] < VREF_MIN or (
        evidence["expected_vref"] > VREF_MAX
    )
    native = {
        "exit_code": 0,
        "stdout": f"meas_vref = {evidence['expected_vref']}e+00\n",
        "stderr": "",
        "log": "",
        "deck": "ngspice_deck.spice",
        "sources": [SNAPSHOT_NAME],
        "measurements": _spice_measurements(),
    }
    result = NgspiceAdapter().parse(native)
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "measurement"
    assert result["measurements"][0]["status"] == "fail"
    assert result["measurements"][0]["margin"] < 0


@pytest.mark.parametrize("value", [0.0, 2.8])
def test_bandgap_parse_open_net_fails_canned(value):
    # An open is a topology break, not a value change: the
    # feedback path is cut (VOUT_OPEN) or the device is lifted, so
    # Vref collapses toward ground or toward the ~2.8 V
    # collapse the netlist header documents for mistuned ratios.
    # Either way the DR-005 window misses with rule measurement.
    from rocket_engine.adapters.ngspice import NgspiceAdapter

    native = {
        "exit_code": 0,
        "stdout": f"meas_vref = {value}e+00\n",
        "stderr": "",
        "log": "",
        "deck": "ngspice_deck.spice",
        "sources": [SNAPSHOT_NAME],
        "measurements": _spice_measurements(),
    }
    result = NgspiceAdapter().parse(native)
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "measurement"
    assert result["measurements"][0]["status"] == "fail"


# Mutation-flips-only-target: live rechecks.


@pytest.mark.parametrize("operator,seed", _op_params(BANDGAP_OP_SEEDS))
def test_bandgap_mutated_fails_only_target(operator, seed, tmp_path):
    _require_bandgap()
    # RED: staging rejects "bandgap" before any tool check runs.
    staged = _stage_mut(operator, tmp_path / "mut", seed)
    _require_ngspice()
    pdk_entry = _require_pdk()
    engine, out = _engine_run(
        f"validate_a_{seed}", "run_spice", _job(staged, pdk_entry)
    )
    assert out["verdict"]["status"] == "FAIL", (operator, seed, out["verdict"])
    found = engine.findings(out["run_id"])["findings"]
    errors = [f for f in found if f["severity"] == "error"]
    assert errors, (operator, seed)
    assert {f["rule"] for f in errors} == {"measurement"}, (operator, seed, found)


# Determinism-3x: identical verdicts across repeat runs.


def test_bandgap_determinism_3x(tmp_path):
    _require_bandgap()
    # RED: staging rejects "bandgap" before any tool check runs.
    probe = _stage_good(tmp_path / "probe")
    assert probe["measurements"][0]["min"] == VREF_MIN
    _require_ngspice()
    pdk_entry = _require_pdk()
    from rocket_engine.adapters.ngspice import NgspiceAdapter

    cases = [("good", None, None)]
    cases += [(op, op, seed) for op, seed in _op_params(BANDGAP_OP_SEEDS)]
    for name, operator, seed in cases:
        seen = []
        for rep in range(3):
            dest = tmp_path / f"{name}-{seed}-{rep}"
            if operator is None:
                staged = _stage_good(dest)
            else:
                staged = _stage_mut(operator, dest, seed)
            job = _job(staged, pdk_entry)
            engine, out = _engine_run(f"validate_a_det_{rep}", "run_spice", job)
            found = engine.findings(out["run_id"])["findings"]
            native = NgspiceAdapter().execute(job)
            parsed = NgspiceAdapter().parse(native)
            values = tuple(
                (m["name"], m["value"], m["status"])
                for m in parsed.get("measurements", [])
            )
            seen.append(
                (out["verdict"]["status"], _canon_findings(found), values)
            )
        assert seen[0] == seen[1] == seen[2], (name, seed, seen)
        want = "PASS" if operator is None else "FAIL"
        assert seen[0][0] == want, (name, seed, seen)


# Artifacts-kept: verdict JSON + native logs + run record.


def test_bandgap_failure_artifacts_kept(tmp_path):
    from rocket_engine.adapters.ngspice import NgspiceAdapter
    from rocket_engine.mutate import OPERATORS, apply_operator, stage_design_extras

    _require_bandgap()
    operator, seed = "bandgap_sizing_out_of_spec", 0
    # RED: operator missing from the registry (KeyError).
    entry = OPERATORS[operator]
    dest = tmp_path / "mut"
    evidence = apply_operator(operator, dest, seed, ROOT / entry["base"])
    staged = stage_design_extras(entry["design"], dest, ROOT)
    _require_ngspice()
    pdk_entry = _require_pdk()
    job = _job(staged, pdk_entry)
    engine, out = _engine_run("validate_a_art", "run_spice", job)
    assert out["verdict"]["status"] == "FAIL"
    native = NgspiceAdapter().execute(job)
    assert NgspiceAdapter().parse(native)["total"] >= 1
    found = engine.findings(out["run_id"])["findings"]
    case_dir = _write_artifacts(
        "bandgap_sizing_out_of_spec-0",
        verdict=out["verdict"],
        findings=found,
        native=native,
        staged=staged,
        mutation=evidence,
        pdk_entry=pdk_entry,
    )
    for name in ("verdict.json", "native.log", "run_record.json"):
        path = case_dir / name
        assert path.is_file(), name
        assert path.stat().st_size > 0, name
    record = json.loads((case_dir / "run_record.json").read_text())
    assert record["ingredients"]["mutation"]["operator"] == operator
    assert record["ingredients"]["solver"]["tool"] == "ngspice"
    from rocket_engine.interfaces.paths import slugify
    assert slugify(
        record["ingredients"]["pdk"]["pdk_id"]) == "sky130a"
    assert len(record["ingredients"]["sources"]) == len(staged["sources"])
    assert "meas_vref" in (case_dir / "native.log").read_text() or "vref" in (
        case_dir / "native.log"
    ).read_text().lower()


# Staging guards: unknown designs and missing pieces fail loudly
# (no tool needed).


def test_stage_bandgap_missing_base_raises(tmp_path):
    from rocket_engine.mutate import stage_design_extras

    dest = tmp_path / "mut"
    dest.mkdir()
    try:
        stage_design_extras("bandgap", dest, ROOT)
    except KeyError:
        # RED: "bandgap" is not a known design yet.
        raise AssertionError("expected FileNotFoundError for missing base")
    except FileNotFoundError as exc:
        assert "base file missing" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError for missing base")


# CLI rechecks prove the scripts/mutate.py path on the bandgap.


@pytest.mark.parametrize(
    "operator", ["bandgap_sizing_out_of_spec", "bandgap_open_net"]
)
def test_cli_recheck_proves_bandgap_flip(operator, tmp_path):
    from rocket_engine.mutate import OPERATORS

    _require_bandgap()
    # RED: operator missing from the registry (KeyError).
    assert operator in OPERATORS
    _require_ngspice()
    _require_pdk()
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mutate.py"), "recheck",
         "--operator", operator, "--seed", "0",
         "--dest", str(tmp_path / "recheck")],
        capture_output=True,
        text=True,
        timeout=280,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    assert report["proven"] is True, report
    assert report["good"] == "PASS", report
    assert report["mutated"] == "FAIL", report
