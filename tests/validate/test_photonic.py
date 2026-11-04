"""VALIDATE-P RED — photonic correctness end-to-end (cspdk MZI + SAX).

Valid RED = the "mzi" design does not exist yet in
`rocket_engine.mutate` (KeyError on stage_good_design /
stage_design_extras, no "design" key on the photonic operators),
the sax_mzi / klayout_mzi scenario backends are unknown, and the
cspdk catalog entry is new — so every staging/layout/live test
below fails while the recorded-oracle + canned tests prove the
parse path without the binaries.

Correct = two-source truth (docs/tickets/VALIDATE-P.md). Layout:
the cspdk reference si340 MZI GDS (tests/gds_ref_si340/mzi.gds @
3323b17b, MIT) passes the documented CORNERSTONE min rules on GDS
3/0 — 350 nm feature, 200 nm gap (49th-call design guidelines,
section 5.3-5.4 Table 4) — with zero violations under KLayout
0.28.16. Behavior: the SAX-notebook balanced MZI
(tests/adapters/fixtures/sax/mzi.yml) reproduces its documented
transmission through SaxAdapter (cross 1.0 / 0 dB, bar 0.0 at
1550 nm). Each photonic mutation must flip its e2e to FAIL with
transmission and only it, while the layout side stays PASS.

sax + gdsfactory are absent here (B10-owned tooling): optical
live tests skip LOUDLY, and the sim mapping is pinned by oracle
envelopes recorded against real sax 0.18.2 in a throwaway venv
plus canned parses. KLayout is present, so the layout side runs
live on both PATHs. SiEPIC-Tools explicitly NOT used.
"""

import hashlib
import importlib.util
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
MZI_YML = ROOT / "tests" / "adapters" / "fixtures" / "sax" / "mzi.yml"
CSPDK = ROOT / "fixtures" / "upstream" / "cspdk"
REF_GDS_REL = Path("tests") / "gds_ref_si340" / "mzi.gds"
REF_GDS = CSPDK / REF_GDS_REL
ARTIFACTS = ROOT / "tmp" / "validate-p"

# Documented CORNERSTONE min rules for GDS 3/0 (waveguide layer):
# 49th-call design guidelines section 5.3-5.4, Table 4 (340 nm SOI).
# Min feature 350 nm -> width_um 0.35; min gap 200 nm -> space_um 0.2.
DRC_LAYER = [3, 0]
DRC_WIDTH_UM = 0.35
DRC_SPACE_UM = 0.2
DRC_RULES_REF = (
    "CORNERSTONE-49th-Call-Design-Guidelines-1.pdf section 5.3-5.4 "
    "Table 4 (vendored cspdk references/)"
)

# Reference MZI structure (klayout 0.28.16 read of the pinned GDS):
# single waveguide layer, 16 shapes, ~201 x 51 um.
REF_TOP_PREFIX = "mzi_"
REF_LAYER_SHAPES = {"3/0": 16}
REF_BBOX_UM = [-20.0, -27.8, 181.3, 22.8]

# sax 0.18.2 recorded oracle: exact transmission triples on the
# [1540, 1550, 1560] nm grid for the two mzi.yml target pairs,
# captured 2026-10-29 in a throwaway venv via SaxAdapter.execute
# (tool_dir) on mzi.yml plus apply_operator mutants. Confirms the
# MUTATE-HARNESS evidence (0.33972 / 0.10276 / 0.8 @1550 nm).
ORACLE_GRID_NM = [1540.0, 1550.0, 1560.0]
ORACLE_GOOD = {
    "in0>out1": [1.0000000000000004, 1.0000000000000004, 1.0],
    "in0>out0": [0.0, 0.0, 0.0],
}
ORACLE_GEOMETRY = {
    0: {
        "in0>out1": [0.3312689288688903, 0.3397201693774351, 0.3481134387186262],
        "in0>out0": [0.6687310711311101, 0.6602798306225655, 0.651886561281374],
    },
    1: {
        "in0>out1": [0.1138806974602156, 0.10275849641759266, 0.09227810999153457],
        "in0>out0": [0.8861193025397847, 0.8972415035824077, 0.9077218900084659],
    },
}
ORACLE_CIRCUIT = {
    "in0>out1": [0.8000000000000002, 0.8000000000000004, 0.8000000000000002],
    "in0>out0": [0.19999999999999998, 0.20000000000000004, 0.20000000000000004],
}

MZI_OP_SEEDS = {
    "photonic_geometry_mistune": [0, 1],
    "photonic_circuit_mistune": [0],
}

STAGED_GDS_NAME = "mzi_ref.gds"


def _require_cspdk():
    if not REF_GDS.is_file():
        pytest.skip(
            "VALIDATE-P live: cspdk fixture not fetched "
            "(scripts/fetch_fixtures.py --only cspdk; "
            "docs/tickets/VALIDATE-P.md)"
        )


def _require_klayout():
    if shutil.which("klayout") is None:
        pytest.skip(
            "VALIDATE-P layout live: klayout not on PATH (B10-owned tooling)"
        )


def _require_sax():
    if importlib.util.find_spec("sax") is None:
        pytest.skip(
            "VALIDATE-P optical live: sax not installed, "
            "uv sync (B10-owned tooling)"
        )


def _engine_run(project, operation, arguments):
    from rocket_engine.composition import Engine

    engine = Engine(project, actor="validate-p")
    out = engine.run(
        {"project_id": project, "operation": operation, "arguments": arguments}
    )
    return engine, out


def _stage_good(dest):
    # RED: stage_good_design rejects "mzi" (KeyError).
    from rocket_engine.mutate import stage_good_design

    return stage_good_design("mzi", dest, ROOT)


def _stage_mut(operator, dest, seed):
    # RED: photonic operators carry no "mzi" design yet (KeyError).
    from rocket_engine.mutate import OPERATORS, apply_operator, stage_design_extras

    entry = OPERATORS[operator]
    apply_operator(operator, dest, seed, ROOT / entry["base"])
    return stage_design_extras(entry["design"], dest, ROOT)


def _drc_job(staged):
    layout = staged["layout"]
    return {
        "operation": "run_drc",
        "tech": layout["tech"],
        "cell": layout["cell"],
        "gds_file": layout["gds_file"],
        "rules": layout["rules"],
        "workdir": staged["workdir"],
        "deck": {"tool": "klayout"},
    }


def _optical_job(staged):
    return {
        "operation": "run_optical",
        "sources": staged["sources"],
        "workdir": staged["workdir"],
        "request": {"timeout_s": staged["timeout_s"]},
        "deck": {"tool": "sax"},
    }


def _mzi_targets():
    return [
        {"from": "in0", "to": "out1", "at_nm": 1550.0, "min_db": -0.5},
        {"from": "in0", "to": "out0", "at_nm": 1550.0, "max_db": -40.0},
    ]


def _recorded_native(pairs, spec="mzi.yml"):
    return {
        "exit_code": 0,
        "stdout": json.dumps(
            {
                "ok": True,
                "sax_version": "0.18.2-recorded",
                "result": {
                    "wavelength_nm": list(ORACLE_GRID_NM),
                    "transmission": {k: list(v) for k, v in pairs.items()},
                    "ports": ["in0", "out0", "out1"],
                },
            }
        ),
        "stderr": "",
        "spec": spec,
        "targets": _mzi_targets(),
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
                sorted(
                    (k, json.dumps(v, sort_keys=True))
                    for k, v in location.items()
                ),
            )
        )
    return sorted(canon)


def _fixture_pin():
    note = ROOT / "fixtures" / "upstream" / "cspdk.md"
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
        cwd=CSPDK,
    )
    if proc.returncode == 0:
        head = proc.stdout.strip()
    return rev, head


def _tool_versions():
    versions = {}
    for binary in ("klayout",):
        found = shutil.which(binary)
        versions[binary] = found or "absent"
        if found:
            try:
                proc = subprocess.run(
                    [binary, "-v"], capture_output=True, text=True, timeout=30
                )
                versions[binary] = (proc.stdout + proc.stderr).splitlines()[0][
                    :120
                ]
            except Exception:
                pass
    spec = importlib.util.find_spec("sax")
    versions["sax"] = "absent"
    if spec is not None:
        try:
            import sax

            versions["sax"] = getattr(sax, "__version__", "present")
        except Exception:
            versions["sax"] = "present"
    return versions


def _write_artifacts(case, *, verdict, findings, native, staged, mutation, tool):
    case_dir = ARTIFACTS / case
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "verdict.json").write_text(
        json.dumps(
            {"verdict": verdict, "findings": findings}, indent=2, sort_keys=True
        )
        + "\n"
    )
    (case_dir / "native.log").write_text(
        "=== stdout ===\n"
        + (native.get("stdout") or "")
        + "\n=== stderr ===\n"
        + (native.get("stderr") or "")
    )
    pinned, head = _fixture_pin()
    sources = []
    for path in staged["sources"]:
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        sources.append({"name": Path(path).name, "sha256": digest})
    layout = dict(staged.get("layout") or {})
    gds_file = layout.get("gds_file")
    if gds_file and Path(gds_file).is_file():
        digest = hashlib.sha256(Path(gds_file).read_bytes()).hexdigest()
        sources.append({"name": Path(gds_file).name, "sha256": digest})
    record = {
        "case": case,
        "design": "mzi",
        "engine": {
            "operation": {"klayout": "run_drc", "sax": "run_optical"}.get(tool, tool),
            "project_id": "validate-p",
        },
        "ingredients": {
            "fixture": {"pinned_rev": pinned, "actual_head": head},
            "sources": sorted(sources, key=lambda s: s["name"]),
            "layout": layout,
            "timeout_s": staged.get("timeout_s"),
            "solver": {"tool": tool, **_tool_versions()},
            "mutation": mutation,
        },
        "results": {"verdict": verdict, "findings": findings},
    }
    (case_dir / "run_record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    )
    return case_dir


def _op_params(table):
    return [(op, seed) for op, seeds in table.items() for seed in seeds]


# Layout side: reference MZI GDS through engine KLayout DRC.
#
# Live on both PATHs (klayout present); the cspdk tree gates the
# fixture, never the tool.


def test_mzi_design_staging_pairs_circuit_and_layout(tmp_path):
    _require_cspdk()
    # RED: stage_good_design rejects "mzi" (KeyError).
    staged = _stage_good(tmp_path / "good")
    assert staged["sources"] == [str(tmp_path / "good" / "mzi.yml")]
    assert Path(staged["sources"][0]).is_file()
    layout = staged["layout"]
    assert layout["tech"] == "cornerstone-si340"
    assert layout["cell"] == "mzi"
    assert layout["rules"] == {
        "layer": DRC_LAYER,
        "width_um": DRC_WIDTH_UM,
        "space_um": DRC_SPACE_UM,
    }
    assert DRC_RULES_REF in layout["rules_ref"]
    staged_gds = Path(layout["gds_file"])
    assert staged_gds.name == STAGED_GDS_NAME
    # Staged bytes equal the pinned reference bytes.
    assert staged_gds.read_bytes() == REF_GDS.read_bytes()


def test_layout_good_matches_reference(tmp_path):
    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

    _require_cspdk()
    # RED: staging rejects "mzi" before any tool check runs.
    staged = _stage_good(tmp_path / "good")
    _require_klayout()
    assert staged["layout"]["rules"]["width_um"] == DRC_WIDTH_UM
    assert staged["layout"]["rules"]["space_um"] == DRC_SPACE_UM
    engine, out = _engine_run("validate_p_layout_good", "run_drc", _drc_job(staged))
    assert out["verdict"]["status"] == "PASS", out["verdict"]
    assert engine.findings(out["run_id"])["findings"] == []
    native = KlayoutDrcAdapter().execute(_drc_job(staged))
    result = KlayoutDrcAdapter().parse(native)
    assert result["total"] == 0, result["violations"]
    assert "TOTAL 0" in native["stdout"]


def test_layout_reference_structure_oracle(tmp_path):
    # Structural quote tying the test to fixture bytes: the pinned
    # reference holds one waveguide layer (16 shapes) in the
    # documented MZI footprint. Read via klayout batch, not via the
    # adapter under test.
    _require_cspdk()
    _require_klayout()
    script = tmp_path / "probe.py"
    script.write_text(
        "import json, pya\n"
        f"layout = pya.Layout()\nlayout.read({str(REF_GDS)!r})\n"
        "top = layout.top_cell()\n"
        "layers = {}\n"
        "for li in layout.layer_indexes():\n"
        "    info = layout.get_info(li)\n"
        "    key = '%d/%d' % (info.layer, info.datatype)\n"
        "    layers[key] = pya.Region(top.begin_shapes_rec(li)).count()\n"
        "box = top.bbox()\n"
        "dbu = layout.dbu\n"
        "print(json.dumps({'top': top.name, 'layers': layers,\n"
        "    'bbox_um': [box.left * dbu, box.bottom * dbu,\n"
        "                box.right * dbu, box.top * dbu]}))\n"
    )
    proc = subprocess.run(
        ["klayout", "-b", "-r", str(script)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout.strip().splitlines()[-1])
    assert got["top"].startswith(REF_TOP_PREFIX), got["top"]
    assert got["layers"] == REF_LAYER_SHAPES, got["layers"]
    assert got["bbox_um"] == pytest.approx(REF_BBOX_UM, abs=0.05)


def _write_sliver_mutant(ref_gds, dest_gds, workdir):
    # Test-level layout sensitivity probe (NOT a MUTATE-HARNESS
    # operator: GDS is binary, no text probe site): copy the
    # reference and add one 100 nm sliver on 3/0, far clear of the
    # MZI footprint — it must trip exactly the documented 350 nm
    # width rule, proving the good-PASS is not vacuous.
    script = Path(workdir) / "sliver.py"
    script.write_text(
        "import pya\n"
        "layout = pya.Layout()\n"
        f"layout.read({str(ref_gds)!r})\n"
        "top = layout.top_cell()\n"
        "layer = layout.layer(3, 0)\n"
        "dbu = layout.dbu\n"
        "x0 = int(round(200.0 / dbu))\n"
        "top.shapes(layer).insert(pya.Box(x0, 0, x0 + int(round(0.1 / dbu)),\n"
        "    int(round(2.0 / dbu))))\n"
        f"layout.write({str(dest_gds)!r})\n"
        "print('WROTE SLIVER')\n"
    )
    proc = subprocess.run(
        ["klayout", "-b", "-r", str(script)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=workdir,
    )
    assert proc.returncode == 0, proc.stderr
    assert Path(dest_gds).is_file()


def test_layout_sliver_mutant_fails_only_width(tmp_path):
    _require_cspdk()
    # RED: staging rejects "mzi" before any tool check runs.
    staged = _stage_good(tmp_path / "good")
    _require_klayout()
    mutant_gds = tmp_path / "sliver.gds"
    _write_sliver_mutant(staged["layout"]["gds_file"], mutant_gds, tmp_path)
    assert mutant_gds.read_bytes() != REF_GDS.read_bytes()
    job = _drc_job(staged)
    job["gds_file"] = str(mutant_gds)
    engine, out = _engine_run("validate_p_layout_sliver", "run_drc", job)
    assert out["verdict"]["status"] == "FAIL", out["verdict"]
    found = engine.findings(out["run_id"])["findings"]
    errors = [f for f in found if f["severity"] == "error"]
    assert errors
    assert {f["rule"] for f in errors} == {"L3_0_width"}, found
    assert all(len(f["location"]["bbox_um"]) == 4 for f in errors)


# Behavior side: SAX sim through SaxAdapter vs documented transmission.
#
# Live where sax exists; otherwise the recorded-oracle + canned
# tests below pin the mapping and live tests skip LOUDLY with the
# B10 ref (never fake-green).


def test_optical_good_matches_documented_transmission(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter

    _require_cspdk()
    # RED: staging rejects "mzi" before any tool check runs.
    staged = _stage_good(tmp_path / "good")
    _require_sax()
    engine, out = _engine_run(
        "validate_p_optical_good", "run_optical", _optical_job(staged)
    )
    assert out["verdict"]["status"] == "PASS", out["verdict"]
    assert engine.findings(out["run_id"])["findings"] == []
    native = SaxAdapter().execute(_optical_job(staged))
    result = SaxAdapter().parse(native)
    assert result["total"] == 0, result["violations"]
    by_name = {m["name"]: m for m in result["measurements"]}
    cross = by_name["T(in0->out1)@1550.0nm"]
    assert cross["value"] == pytest.approx(0.0, abs=1e-9)
    assert cross["unit"] == "dB"
    assert cross["status"] == "pass"
    assert by_name["T(in0->out0)@1550.0nm"]["status"] == "pass"


def test_optical_recorded_good_oracle_passes():
    # Oracle check (SIM-SKY130 precedent): recorded real sax
    # 0.18.2 output parses to the documented transmission. Runs
    # without the binary.
    from rocket_engine.adapters.sax import SaxAdapter

    result = SaxAdapter().parse(_recorded_native(ORACLE_GOOD))
    assert result["total"] == 0, result["violations"]
    by_name = {m["name"]: m for m in result["measurements"]}
    assert by_name["T(in0->out1)@1550.0nm"]["value"] == pytest.approx(
        0.0, abs=1e-9
    )
    assert [m["status"] for m in result["measurements"]] == ["pass", "pass"]


@pytest.mark.parametrize("seed,linear,db", [(0, 0.33972, -4.689), (1, 0.10276, -9.882)])
def test_optical_recorded_geometry_oracle_fails(seed, linear, db):
    from rocket_engine.adapters.sax import SaxAdapter

    result = SaxAdapter().parse(_recorded_native(ORACLE_GEOMETRY[seed]))
    assert result["total"] >= 1
    assert {v["rule"] for v in result["violations"]} == {"transmission"}
    by_name = {m["name"]: m for m in result["measurements"]}
    cross = by_name["T(in0->out1)@1550.0nm"]
    assert cross["value"] == pytest.approx(db, abs=1e-3)
    assert cross["status"] == "fail"
    assert cross["margin"] < 0


def test_optical_recorded_circuit_oracle_fails():
    from rocket_engine.adapters.sax import SaxAdapter

    result = SaxAdapter().parse(_recorded_native(ORACLE_CIRCUIT))
    assert result["total"] >= 1
    assert {v["rule"] for v in result["violations"]} == {"transmission"}
    by_name = {m["name"]: m for m in result["measurements"]}
    cross = by_name["T(in0->out1)@1550.0nm"]
    assert cross["value"] == pytest.approx(-0.969, abs=1e-3)
    assert cross["status"] == "fail"
    assert cross["margin"] < 0


def test_optical_recorded_oracles_match_mutation_evidence(tmp_path):
    # The recorded sax numbers agree with the operators' declared
    # evidence: oracle and MUTATE-HARNESS quote the same physics.
    from rocket_engine.mutate import apply_operator

    base = ROOT / "tests" / "adapters" / "fixtures" / "sax"
    for operator, seeds in MZI_OP_SEEDS.items():
        for seed in seeds:
            evidence = apply_operator(operator, tmp_path / f"{operator}-{seed}", seed, base)
            recorded = ORACLE_GEOMETRY[seed]["in0>out1"][1] if operator.endswith("geometry_mistune") else ORACLE_CIRCUIT["in0>out1"][1]
            assert recorded == pytest.approx(evidence["expected_linear"], abs=1e-4)
            assert 10.0 * math.log10(recorded) == pytest.approx(
                evidence["expected_db"], abs=1e-3
            )


# Mutation-flips-only-target: file level (no tool needed).


@pytest.mark.parametrize("operator,seed", _op_params(MZI_OP_SEEDS))
def test_optical_mutation_targets_circuit_site(operator, seed, tmp_path):
    from rocket_engine.mutate import OPERATORS, apply_operator

    assert OPERATORS[operator]["operation"] == "run_optical"
    assert OPERATORS[operator]["expected_verdict"] == "FAIL"
    assert OPERATORS[operator]["expected_rules"] == ["transmission"]
    # RED: photonic operators carry no "design" key yet (KeyError).
    assert OPERATORS[operator]["design"] == "mzi"
    dest = tmp_path / "mut"
    evidence = apply_operator(
        operator, dest, seed, ROOT / OPERATORS[operator]["base"]
    )
    assert evidence["operator"] == operator
    assert evidence["seed"] == seed
    assert evidence["target_file"] == "mzi.yml"
    staged = dest / "mzi.yml"
    assert staged.is_file()
    assert staged.read_bytes() != MZI_YML.read_bytes()


def test_mzi_operator_files_match_fixture():
    from rocket_engine.mutate import OPERATORS

    for operator in MZI_OP_SEEDS:
        assert OPERATORS[operator]["files"] == ["mzi.yml"], operator
        # RED: photonic operators carry no "design" key yet (KeyError).
        assert OPERATORS[operator]["design"] == "mzi", operator


# Mutation-flips-only-target: live rechecks (optical flips, layout stays).


@pytest.mark.parametrize("operator,seed", _op_params(MZI_OP_SEEDS))
def test_optical_mutated_fails_only_target(operator, seed, tmp_path):
    _require_cspdk()
    # RED: staging rejects "mzi" before any tool check runs.
    staged = _stage_mut(operator, tmp_path / "mut", seed)
    _require_sax()
    engine, out = _engine_run(
        f"validate_p_{seed}", "run_optical", _optical_job(staged)
    )
    assert out["verdict"]["status"] == "FAIL", (operator, seed, out["verdict"])
    found = engine.findings(out["run_id"])["findings"]
    errors = [f for f in found if f["severity"] == "error"]
    assert errors, (operator, seed)
    assert {f["rule"] for f in errors} == {"transmission"}, (operator, seed, found)


@pytest.mark.parametrize("operator,seed", _op_params(MZI_OP_SEEDS))
def test_layout_stays_pass_on_circuit_mutation(operator, seed, tmp_path):
    # Only the target flips: a circuit mistune breaks behavior, not
    # the reference layout — the layout side stays PASS.
    _require_cspdk()
    # RED: staging rejects "mzi" before any tool check runs.
    staged = _stage_mut(operator, tmp_path / "mut", seed)
    _require_klayout()
    engine, out = _engine_run(
        f"validate_p_layout_{seed}", "run_drc", _drc_job(staged)
    )
    assert out["verdict"]["status"] == "PASS", (operator, seed, out["verdict"])
    assert engine.findings(out["run_id"])["findings"] == []


# Determinism-3x: identical verdicts across repeat runs.


def test_layout_determinism_3x(tmp_path):
    _require_cspdk()
    # RED: staging rejects "mzi" before any tool check runs.
    probe = _stage_good(tmp_path / "probe")
    assert probe["layout"]["rules"]["width_um"] == DRC_WIDTH_UM
    _require_klayout()
    for name, sliver in (("good", False), ("sliver", True)):
        seen = []
        for rep in range(3):
            dest = tmp_path / f"{name}-{rep}"
            staged = _stage_good(dest)
            job = _drc_job(staged)
            if sliver:
                mutant_gds = dest / "sliver.gds"
                _write_sliver_mutant(staged["layout"]["gds_file"], mutant_gds, dest)
                job["gds_file"] = str(mutant_gds)
            engine, out = _engine_run(f"validate_p_layout_det_{rep}", "run_drc", job)
            found = engine.findings(out["run_id"])["findings"]
            seen.append((out["verdict"]["status"], _canon_findings(found)))
        assert seen[0] == seen[1] == seen[2], (name, seen)
        want = "FAIL" if sliver else "PASS"
        assert seen[0][0] == want, (name, seen)


def test_optical_determinism_3x(tmp_path):
    _require_cspdk()
    # RED: staging rejects "mzi" before any tool check runs.
    probe = _stage_good(tmp_path / "probe")
    assert probe["sources"][0].endswith("mzi.yml")
    _require_sax()
    from rocket_engine.adapters.sax import SaxAdapter

    cases = [("good", None, None)]
    cases += [(op, op, seed) for op, seed in _op_params(MZI_OP_SEEDS)]
    for name, operator, seed in cases:
        seen = []
        for rep in range(3):
            dest = tmp_path / f"{name}-{seed}-{rep}"
            if operator is None:
                staged = _stage_good(dest)
            else:
                staged = _stage_mut(operator, dest, seed)
            job = _optical_job(staged)
            engine, out = _engine_run(f"validate_p_opt_det_{rep}", "run_optical", job)
            found = engine.findings(out["run_id"])["findings"]
            native = SaxAdapter().execute(job)
            parsed = SaxAdapter().parse(native)
            values = tuple(
                (m["name"], m["value"], m["status"])
                for m in parsed.get("measurements", [])
            )
            seen.append((out["verdict"]["status"], _canon_findings(found), values))
        assert seen[0] == seen[1] == seen[2], (name, seed, seen)
        want = "PASS" if operator is None else "FAIL"
        assert seen[0][0] == want, (name, seed, seen)


def test_optical_canned_determinism_3x():
    # Results-not-bytes on the recorded mapping: the same recorded
    # envelope parses identically every time (no binary needed).
    from rocket_engine.adapters.sax import SaxAdapter

    for pairs in (
        ORACLE_GOOD,
        ORACLE_GEOMETRY[0],
        ORACLE_GEOMETRY[1],
        ORACLE_CIRCUIT,
    ):
        seen = []
        for _ in range(3):
            parsed = SaxAdapter().parse(_recorded_native(pairs))
            seen.append(
                (
                    parsed["total"],
                    sorted(
                        (v["rule"], v.get("severity", "error"))
                        for v in parsed["violations"]
                    ),
                    tuple(
                        (m["name"], m["value"], m["status"])
                        for m in parsed["measurements"]
                    ),
                )
            )
        assert seen[0] == seen[1] == seen[2], pairs


# Artifacts-kept: verdict JSON + native logs + run record.


def test_layout_failure_artifacts_kept(tmp_path):
    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

    _require_cspdk()
    # RED: staging rejects "mzi" before any tool check runs.
    staged = _stage_good(tmp_path / "good")
    _require_klayout()
    mutant_gds = tmp_path / "sliver.gds"
    _write_sliver_mutant(staged["layout"]["gds_file"], mutant_gds, tmp_path)
    staged["sources"] = list(staged["sources"])
    job = _drc_job(staged)
    job["gds_file"] = str(mutant_gds)
    engine, out = _engine_run("validate_p_layout_art", "run_drc", job)
    assert out["verdict"]["status"] == "FAIL"
    native = KlayoutDrcAdapter().execute(job)
    assert KlayoutDrcAdapter().parse(native)["total"] >= 1
    found = engine.findings(out["run_id"])["findings"]
    staged = dict(staged)
    staged["layout"] = dict(staged["layout"], gds_file=str(mutant_gds))
    case_dir = _write_artifacts(
        "layout_sliver_width",
        verdict=out["verdict"],
        findings=found,
        native=native,
        staged=staged,
        mutation={"operator": None, "note": "test-level 100nm sliver probe"},
        tool="klayout",
    )
    for name in ("verdict.json", "native.log", "run_record.json"):
        path = case_dir / name
        assert path.is_file(), name
        assert path.stat().st_size > 0, name
    record = json.loads((case_dir / "run_record.json").read_text())
    assert record["ingredients"]["layout"]["rules"]["width_um"] == DRC_WIDTH_UM
    assert record["ingredients"]["solver"]["tool"] == "klayout"
    assert "TOTAL" in (case_dir / "native.log").read_text()


@pytest.mark.parametrize("operator,seed", _op_params(MZI_OP_SEEDS))
def test_optical_failure_artifacts_canned(operator, seed, tmp_path):
    # Artifacts-kept without the binary: the recorded mutant
    # envelope parses to FAIL and the failure bundle is written.
    from rocket_engine.adapters.sax import SaxAdapter
    from rocket_engine.mutate import OPERATORS, apply_operator

    _require_cspdk()
    evidence = apply_operator(
        operator, tmp_path / "mut", seed, ROOT / OPERATORS[operator]["base"]
    )
    pairs = (
        ORACLE_GEOMETRY[seed]
        if operator == "photonic_geometry_mistune"
        else ORACLE_CIRCUIT
    )
    native = _recorded_native(pairs)
    parsed = SaxAdapter().parse(native)
    assert parsed["total"] >= 1
    verdict = {"status": "FAIL", "run_id": "canned"}
    staged = {
        "sources": [str(tmp_path / "mut" / "mzi.yml")],
        "workdir": str(tmp_path / "mut"),
        "timeout_s": 120,
        "layout": {
            "gds_file": str(REF_GDS),
            "cell": "mzi",
            "tech": "cornerstone-si340",
            "rules": {
                "layer": DRC_LAYER,
                "width_um": DRC_WIDTH_UM,
                "space_um": DRC_SPACE_UM,
            },
            "rules_ref": DRC_RULES_REF,
        },
    }
    case_dir = _write_artifacts(
        f"{operator}-{seed}",
        verdict=verdict,
        findings=parsed["violations"],
        native=native,
        staged=staged,
        mutation=evidence,
        tool="sax",
    )
    for name in ("verdict.json", "native.log", "run_record.json"):
        path = case_dir / name
        assert path.is_file(), name
        assert path.stat().st_size > 0, name
    record = json.loads((case_dir / "run_record.json").read_text())
    assert record["ingredients"]["mutation"]["operator"] == operator
    assert record["ingredients"]["solver"]["tool"] == "sax"
    assert "0.18.2-recorded" in (case_dir / "native.log").read_text()


# Staging guards: unknown designs and missing pieces fail loudly
# (no tool needed).


def test_stage_mzi_missing_base_raises(tmp_path):
    from rocket_engine.mutate import stage_design_extras

    dest = tmp_path / "mut"
    dest.mkdir()
    try:
        stage_design_extras("mzi", dest, ROOT)
    except KeyError:
        # RED: "mzi" is not a known design yet.
        raise AssertionError("expected FileNotFoundError for missing base")
    except FileNotFoundError as exc:
        assert "base file missing" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError for missing base")


def test_stage_mzi_missing_cspdk_raises(tmp_path):
    from rocket_engine.mutate import stage_design_extras

    dest = tmp_path / "mut"
    dest.mkdir()
    (dest / "mzi.yml").write_text(MZI_YML.read_text())
    try:
        stage_design_extras("mzi", dest, tmp_path / "empty-root")
    except KeyError:
        # RED: "mzi" is not a known design yet.
        raise AssertionError("expected FileNotFoundError for missing cspdk GDS")
    except FileNotFoundError as exc:
        assert "cspdk" in str(exc).lower() or "mzi.gds" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError for missing cspdk GDS")


# CLI rechecks prove the scripts/mutate.py path per photonic operator —
# proven where sax exists, quarantined LOUDLY where it does not.


@pytest.mark.parametrize("operator", list(MZI_OP_SEEDS))
def test_cli_recheck_proves_photonic_flip_or_quarantines(operator, tmp_path):
    from rocket_engine.mutate import OPERATORS

    assert operator in OPERATORS
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mutate.py"), "recheck",
         "--operator", operator, "--seed", "0",
         "--dest", str(tmp_path / "recheck")],
        capture_output=True,
        text=True,
        timeout=280,
        cwd=ROOT,
    )
    if importlib.util.find_spec("sax") is None:
        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "QUARANTINED" in proc.stdout + proc.stderr
        assert "photonic" in proc.stdout + proc.stderr
    else:
        assert proc.returncode == 0, proc.stdout + proc.stderr
        report = json.loads(proc.stdout)
        assert report["proven"] is True, report
        assert report["good"] == "PASS", report
        assert report["mutated"] == "FAIL", report

