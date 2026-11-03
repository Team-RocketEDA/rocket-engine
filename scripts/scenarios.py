#!/usr/bin/env python3
"""Scenario harness (mock UI track): scripted MCP-client scenarios.

Each scenario submits through McpTransport into the real Engine, then
either dispatches a canned FakeAdapter (fake track) or runs a live
solver on a fixture cell (live track), then asserts verdicts/events.

Scenario YAML:
    name: <title>
    engine: {project_id, actor: {kind}, revision}
    steps:
      - {submit: {request_id, operation, target, expected_revision?},
         expect_error?: <code>}
      - {dispatch_fake: {exit_code, findings: [{severity, rule, message}]}}
      - {run_live: {cell, tech, backend?, rules?}}
      - {assert_verdict: FAIL}
      - {assert_event: job_queued}

Live scenarios need the real tool (magic for run_drc) and fail loudly
at startup without it (missing_dependency naming the binary — never a
mid-run NOT_RUN). PATH contract: dev-PATH with oss-cad-suite; see
scenarios/README.md. Fixture cells resolve under
tests/adapters/fixtures/drc/.

Usage:
    .venv/bin/python scripts/scenarios.py scenarios/ [--json] [-q]
"""

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ruamel.yaml import YAML

from rocket_engine.adapters import ToolAdapter
from rocket_engine.adapters.mcp import McpTransport
from rocket_engine.composition import Engine

ROOT = Path(__file__).resolve().parent.parent
DRC_FIXTURES = ROOT / "tests" / "adapters" / "fixtures" / "drc"
DRC_KL_FIXTURES = ROOT / "tests" / "adapters" / "fixtures" / "drc_kl"
DRC_SKY130_FIXTURES = ROOT / "tests" / "adapters" / "fixtures" / "drc_sky130"
HDL_FIXTURES = ROOT / "tests" / "adapters" / "fixtures" / "hdl"
SERV_UPSTREAM = ROOT / "fixtures" / "upstream" / "serv"
PICORV32_UPSTREAM = ROOT / "fixtures" / "upstream" / "picorv32"
NGSPICE_SNAPSHOT = (
    ROOT
    / "fixtures"
    / "upstream"
    / "sky130-bandgap"
    / "sim"
    / "output-voltage-tc"
    / "netlist-snapshots"
    / "20260817-015751-13476b7.spice"
)
NGSPICE_LIB_REL = "libs.tech/combined/sky130.lib.spice"
VREF_MIN = 1.176
VREF_MAX = 1.224
CSPDK_REF_GDS = (
    ROOT
    / "fixtures"
    / "upstream"
    / "cspdk"
    / "tests"
    / "gds_ref_si340"
    / "mzi.gds"
)
SIGMA_RTL = ROOT / "fixtures" / "upstream" / "ttsky-sigma-delta" / "rtl"
SIGMA_SPICE = ROOT / "fixtures" / "upstream" / "ttsky-sigma-delta" / "spice"
SDTOP_SNAPSHOT = SIGMA_SPICE / "sd_top_pex.spice"
MZI_DRC_RULES = {"layer": [3, 0], "width_um": 0.35, "space_um": 0.2}
KL_RULES = {"layer": [1, 0], "width_um": 3.0, "space_um": 3.0}
SKY130_PDK_SLUG = "sky130a"
SKY130_PDK_DISPLAY = "sky130A"
SKY130_DECK_REL = "libs.tech/klayout/drc/sky130A.lydrc"
LVS_SKY130_TECH_REL = "libs.tech/magic/sky130A.tech"
LVS_SKY130_SETUP_REL = "libs.tech/netgen/sky130A_setup.tcl"
LVS_SKY130_SPICE_LIB_REL = "libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice"
LVS_SKY130_MAG_DIR_REL = "libs.ref/sky130_fd_sc_hd/mag"
LVS_MUTATE_OLD = "X3 Y A VPWR VPB "
LVS_MUTATE_NEW = "X3 Y A VPWR VPB_BAD "

_BACKEND_PATH_TOOLS = {
    # SCENARIO-PATH: the gate's PATH contract. sax_mzi needs the sax
    # python module, not a PATH binary, so it has no entry here; its
    # mid-run module check stays.
    "magic": ("magic",),
    "klayout": ("klayout",),
    "klayout_sky130": ("klayout",),
    "hdl": ("iverilog", "vvp"),
    "hdl_serv": ("iverilog", "vvp"),
    "hdl_picorv32": ("iverilog", "vvp"),
    "hdl_sdm": ("iverilog", "vvp"),
    "ngspice_bandgap": ("ngspice",),
    "ngspice_sdtop": ("ngspice",),
    "klayout_mzi": ("klayout",),
    "extract_lvs_sky130": ("magic", "netgen"),
}

_TOOL_HINTS = {
    # Ownership refs carried on the startup line so a bare-PATH
    # failure still points at the ticket that owns the gap
    # (DEMO-PATH pins netgen → NGSPICE-LIVE).
    "magic": "B10-owned tooling",
    "ngspice": "see docs/tickets/NGSPICE-LIVE.md",
    "netgen": "see docs/tickets/NGSPICE-LIVE.md",
}


def _startup_line(tool, cause="absent"):
    if cause == "impostor":
        return (
            f"startup: missing_dependency: {tool} on PATH is not the "
            "LVS netgen (see docs/tickets/NGSPICE-LIVE.md)"
        )
    line = (
        f"startup: missing_dependency: {tool} not on PATH "
        "(scenario gate needs dev-PATH with oss-cad-suite; "
        "see scenarios/README.md)"
    )
    if tool in _TOOL_HINTS:
        line += f" [{_TOOL_HINTS[tool]}]"
    return line

_BACKENDS = {
    "magic": {
        "fixtures": DRC_FIXTURES,
        "ext": ".mag",
        "tech": "scmos",
        "file_key": "cell_file",
        "deck": None,
    },
    "klayout": {
        "fixtures": DRC_KL_FIXTURES,
        "ext": ".gds",
        "tech": "synthetic-kl",
        "file_key": "gds_file",
        "deck": "klayout",
        "rules": KL_RULES,
    },
    "klayout_sky130": {
        "fixtures": DRC_SKY130_FIXTURES,
        "ext": ".gds",
        "tech": "sky130A",
        "file_key": "gds_file",
        "deck": "klayout",
        "sky130_deck": True,
    },
}

yaml = YAML(typ="safe")


class FakeAdapter(ToolAdapter):
    """Canned ToolAdapter: canned findings in the violations shape."""

    def __init__(self, canned):
        self._canned = canned

    def capabilities(self, target):
        return {"operations": ["run_drc"], "simulated": True, "target": target}

    def preflight(self, job):
        return {"ready": True}

    def execute(self, job):
        return dict(self._canned)

    def parse(self, native_output):
        violations = [
            {
                "rule": finding["rule"],
                "message": finding.get("message", finding["rule"]),
                "severity": finding.get("severity", "error"),
            }
            for finding in native_output.get("findings", [])
        ]
        return {"total": len(violations), "violations": violations}


def _submit_envelope(project_id, revision, step):
    sub = step["submit"]
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": sub["request_id"],
            "method": "tools/call",
            "params": {
                "name": sub["operation"],
                "arguments": {
                    "project_id": project_id,
                    "expected_revision": sub.get("expected_revision", revision),
                    "target": {
                        "scope": "project",
                        "id": sub["target"],
                        "revision": "r1",
                    },
                },
            },
        }
    )


def _require_ack(ctx, label):
    if "ack" not in ctx:
        raise AssertionError(f"{label}: no submitted ack to dispatch")


def _sky130_entry(label):
    try:
        from rocket_engine.interfaces.paths import slugify
        from rocket_engine.interfaces.pdks import list_pdks
    except Exception as exc:
        raise AssertionError(f"{label}: pdk store unavailable: {exc}") from exc
    try:
        entries = list_pdks()
    except Exception as exc:
        raise AssertionError(
            f"{label}: sky130 PDK not registered ({exc}); "
            f"set ROCKETEDA_HOME to a store with {SKY130_PDK_DISPLAY}."
        ) from exc
    want_rev = os.environ.get("SKY130_PDK_REVISION")
    candidates = [
        e for e in entries if slugify(e.get("id") or "") == SKY130_PDK_SLUG
    ]
    if want_rev:
        candidates = [e for e in candidates if e.get("revision") == want_rev]
    if not candidates:
        raise AssertionError(
            f"{label}: sky130 PDK not registered; "
            f"set ROCKETEDA_HOME to a store with {SKY130_PDK_DISPLAY}."
        )
    return sorted(candidates, key=lambda e: e["revision"])[0]


def _resolve_sky130_deck(label, rel=SKY130_DECK_REL):
    try:
        from rocket_engine.interfaces.pdks import resolve_deck
    except Exception as exc:
        raise AssertionError(f"{label}: pdk store unavailable: {exc}") from exc
    entry = _sky130_entry(label)
    try:
        hit = resolve_deck(entry["id"], entry["revision"], rel)
    except Exception as exc:
        raise AssertionError(f"{label}: cannot resolve sky130 deck: {exc}") from exc
    return hit["path"]


def _run_live_hdl(ctx, label, sub):
    sources = sub.get("sources")
    if not sources:
        raise AssertionError(f"{label}: hdl run_live needs sources")
    workdir = Path(tempfile.mkdtemp(prefix="scen_live_"))
    ctx["tmpdirs"].append(workdir)
    staged = []
    for name in sources:
        fixture = HDL_FIXTURES / name
        if not fixture.is_file():
            raise AssertionError(f"{label}: no fixture for source {name}")
        dest = workdir / fixture.name
        shutil.copy(fixture, dest)
        staged.append(str(dest))
    out = ctx["engine"].run(
        {
            "project_id": ctx["project_id"],
            "operation": ctx["operation"],
            "arguments": {
                "sources": staged,
                "workdir": str(workdir),
                "deck": {"tool": "icarus"},
            },
            "snapshot_id": ctx["ack"]["snapshot_id"],
        }
    )
    ctx["verdict"] = out["verdict"]
    return None


def _run_live_hdl_serv(ctx, label, sub):
    return _run_live_hdl_vendored(ctx, label, sub, "serv")


def _run_live_hdl_picorv32(ctx, label, sub):
    return _run_live_hdl_vendored(ctx, label, sub, "picorv32")


def _run_live_hdl_sdm(ctx, label, sub):
    return _run_live_hdl_vendored(ctx, label, sub, "sdm_rx")


def _run_live_hdl_vendored(ctx, label, sub, design):
    from rocket_engine.mutate import (
        OPERATORS,
        apply_operator,
        stage_design_extras,
        stage_good_design,
    )

    if shutil.which("iverilog") is None or shutil.which("vvp") is None:
        raise AssertionError(f"{label}: iverilog/vvp not on PATH")
    upstream = {
        "serv": SERV_UPSTREAM,
        "picorv32": PICORV32_UPSTREAM,
        "sdm_rx": SIGMA_RTL,
    }[design]
    if design == "serv":
        marker = "rtl/serv_top.v"
    elif design == "picorv32":
        marker = "picorv32.v"
    else:
        marker = "sdm_rx.v"
    if not (upstream / marker).is_file():
        raise AssertionError(f"{label}: {design} fixture not fetched")
    workdir = Path(tempfile.mkdtemp(prefix="scen_live_"))
    ctx["tmpdirs"].append(workdir)
    mutation = sub.get("mutation") or {}
    try:
        if mutation:
            operator = mutation.get("operator", "")
            entry = OPERATORS[operator]
            if entry.get("design") != design:
                raise AssertionError(
                    f"{label}: operator {operator} is not a {design} mutation"
                )
            apply_operator(operator, workdir, mutation.get("seed", 0), upstream)
            staged = stage_design_extras(design, workdir, ROOT)
        else:
            staged = stage_good_design(design, workdir, ROOT)
    except AssertionError:
        raise
    except KeyError as exc:
        raise AssertionError(f"{label}: unknown mutation operator: {exc}") from exc
    except (FileNotFoundError, ValueError) as exc:
        raise AssertionError(f"{label}: cannot stage {design}: {exc}") from exc
    out = ctx["engine"].run(
        {
            "project_id": ctx["project_id"],
            "operation": ctx["operation"],
            "arguments": {
                "sources": staged["sources"],
                "workdir": str(workdir),
                "request": {"timeout_s": staged["timeout_s"]},
                "defines": staged["defines"],
                "deck": {"tool": "icarus"},
            },
            "snapshot_id": ctx["ack"]["snapshot_id"],
        }
    )
    ctx["verdict"] = out["verdict"]
    return None


def _run_live_ngspice_bandgap(ctx, label, sub):
    from rocket_engine.mutate import (
        OPERATORS,
        apply_operator,
        stage_design_extras,
        stage_good_design,
    )

    if shutil.which("ngspice") is None:
        raise AssertionError(f"{label}: ngspice not on PATH")
    if not NGSPICE_SNAPSHOT.is_file():
        raise AssertionError(f"{label}: bandgap snapshot not fetched")
    entry = _sky130_entry(label)
    _resolve_sky130_deck(label, NGSPICE_LIB_REL)
    workdir = Path(tempfile.mkdtemp(prefix="scen_live_"))
    ctx["tmpdirs"].append(workdir)
    mutation = sub.get("mutation") or {}
    try:
        if mutation:
            operator = mutation.get("operator", "")
            entry_op = OPERATORS[operator]
            if entry_op.get("design") != "bandgap":
                raise AssertionError(
                    f"{label}: operator {operator} is not a bandgap mutation"
                )
            apply_operator(
                operator, workdir, mutation.get("seed", 0), NGSPICE_SNAPSHOT.parent
            )
            staged = stage_design_extras("bandgap", workdir, ROOT)
        else:
            staged = stage_good_design("bandgap", workdir, ROOT)
    except AssertionError:
        raise
    except KeyError as exc:
        raise AssertionError(f"{label}: unknown mutation operator: {exc}") from exc
    except (FileNotFoundError, ValueError) as exc:
        raise AssertionError(f"{label}: cannot stage bandgap: {exc}") from exc
    out = ctx["engine"].run(
        {
            "project_id": ctx["project_id"],
            "operation": ctx["operation"],
            "arguments": {
                "sources": staged["sources"],
                "workdir": staged["workdir"],
                "request": {"timeout_s": staged["timeout_s"]},
                "params": staged["params"],
                "options": staged["options"],
                "analyses": staged["analyses"],
                "corner": staged["corner"],
                "temp_c": staged["temp_c"],
                "measurements": staged["measurements"],
                "pdk": {"id": entry["id"], "revision": entry["revision"]},
                "deck": {"tool": "ngspice"},
            },
            "snapshot_id": ctx["ack"]["snapshot_id"],
        }
    )
    ctx["verdict"] = out["verdict"]
    return None


def _run_live_ngspice_sdtop(ctx, label, sub):
    from rocket_engine.mutate import (
        OPERATORS,
        apply_operator,
        stage_design_extras,
        stage_good_design,
    )

    if shutil.which("ngspice") is None:
        raise AssertionError(
            f"{label}: ngspice not on PATH (see docs/tickets/NGSPICE-LIVE.md)"
        )
    if not SDTOP_SNAPSHOT.is_file():
        raise AssertionError(f"{label}: sd_top PEX snapshot not fetched")
    entry = _sky130_entry(label)
    _resolve_sky130_deck(label, NGSPICE_LIB_REL)
    workdir = Path(tempfile.mkdtemp(prefix="scen_live_"))
    ctx["tmpdirs"].append(workdir)
    mutation = sub.get("mutation") or {}
    try:
        if mutation:
            operator = mutation.get("operator", "")
            entry_op = OPERATORS[operator]
            if entry_op.get("design") != "sd_top":
                raise AssertionError(
                    f"{label}: operator {operator} is not an sd_top mutation"
                )
            apply_operator(
                operator, workdir, mutation.get("seed", 0), SDTOP_SNAPSHOT.parent
            )
            staged = stage_design_extras("sd_top", workdir, ROOT)
        else:
            staged = stage_good_design("sd_top", workdir, ROOT)
    except AssertionError:
        raise
    except KeyError as exc:
        raise AssertionError(f"{label}: unknown mutation operator: {exc}") from exc
    except (FileNotFoundError, ValueError) as exc:
        raise AssertionError(f"{label}: cannot stage sd_top: {exc}") from exc
    out = ctx["engine"].run(
        {
            "project_id": ctx["project_id"],
            "operation": ctx["operation"],
            "arguments": {
                "sources": staged["sources"],
                "workdir": staged["workdir"],
                "request": {"timeout_s": staged["timeout_s"]},
                "params": staged["params"],
                "options": staged["options"],
                "analyses": staged["analyses"],
                "corner": staged["corner"],
                "temp_c": staged["temp_c"],
                "measurements": staged["measurements"],
                "pdk": {"id": entry["id"], "revision": entry["revision"]},
                "deck": {"tool": "ngspice"},
            },
            "snapshot_id": ctx["ack"]["snapshot_id"],
        }
    )
    ctx["verdict"] = out["verdict"]
    return None


def _run_live_sax_mzi(ctx, label, sub):
    from rocket_engine.mutate import (
        OPERATORS,
        apply_operator,
        stage_design_extras,
        stage_good_design,
    )

    if importlib.util.find_spec("sax") is None:
        raise AssertionError(
            f"{label}: sax not installed, "
            "uv sync --group photonic (B10-owned tooling)"
        )
    if not CSPDK_REF_GDS.is_file():
        raise AssertionError(f"{label}: cspdk fixture not fetched")
    workdir = Path(tempfile.mkdtemp(prefix="scen_live_"))
    ctx["tmpdirs"].append(workdir)
    mutation = sub.get("mutation") or {}
    try:
        if mutation:
            operator = mutation.get("operator", "")
            entry_op = OPERATORS[operator]
            if entry_op.get("design") != "mzi":
                raise AssertionError(
                    f"{label}: operator {operator} is not an mzi mutation"
                )
            apply_operator(
                operator, workdir, mutation.get("seed", 0), ROOT / entry_op["base"]
            )
            staged = stage_design_extras("mzi", workdir, ROOT)
        else:
            staged = stage_good_design("mzi", workdir, ROOT)
    except AssertionError:
        raise
    except KeyError as exc:
        raise AssertionError(f"{label}: unknown mutation operator: {exc}") from exc
    except (FileNotFoundError, ValueError) as exc:
        raise AssertionError(f"{label}: cannot stage mzi: {exc}") from exc
    out = ctx["engine"].run(
        {
            "project_id": ctx["project_id"],
            "operation": ctx["operation"],
            "arguments": {
                "sources": staged["sources"],
                "workdir": staged["workdir"],
                "request": {"timeout_s": staged["timeout_s"]},
                "deck": {"tool": "sax"},
            },
            "snapshot_id": ctx["ack"]["snapshot_id"],
        }
    )
    ctx["verdict"] = out["verdict"]
    return None


def _write_sliver_mutant(label, ref_gds, dest_gds, workdir):
    # Scenario-side layout sensitivity probe (mirrors the VALIDATE-P
    # test helper; LVS precedent: inline mutation, not an operator):
    # one 100 nm sliver on 3/0 must trip the 350 nm width rule.
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
    )
    try:
        proc = subprocess.run(
            ["klayout", "-b", "-r", str(script)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=workdir,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(f"{label}: klayout sliver write timed out") from exc
    if proc.returncode != 0 or not Path(dest_gds).is_file():
        raise AssertionError(f"{label}: klayout sliver write failed: {proc.stderr[:300]}")


def _run_live_klayout_mzi(ctx, label, sub):
    from rocket_engine.mutate import stage_good_design

    if shutil.which("klayout") is None:
        raise AssertionError(f"{label}: klayout not on PATH")
    if not CSPDK_REF_GDS.is_file():
        raise AssertionError(f"{label}: cspdk fixture not fetched")
    workdir = Path(tempfile.mkdtemp(prefix="scen_live_"))
    ctx["tmpdirs"].append(workdir)
    try:
        staged = stage_good_design("mzi", workdir, ROOT)
    except (FileNotFoundError, ValueError) as exc:
        raise AssertionError(f"{label}: cannot stage mzi: {exc}") from exc
    gds_file = staged["layout"]["gds_file"]
    if sub.get("sliver"):
        mutant = workdir / "sliver.gds"
        _write_sliver_mutant(label, gds_file, mutant, workdir)
        gds_file = str(mutant)
    out = ctx["engine"].run(
        {
            "project_id": ctx["project_id"],
            "operation": ctx["operation"],
            "arguments": {
                "tech": staged["layout"]["tech"],
                "cell": staged["layout"]["cell"],
                "gds_file": gds_file,
                "rules": dict(MZI_DRC_RULES),
                "workdir": str(workdir),
                "deck": {"tool": "klayout"},
            },
            "snapshot_id": ctx["ack"]["snapshot_id"],
        }
    )
    ctx["verdict"] = out["verdict"]
    return None


def _run_live_lvs_sky130(ctx, label, sub):
    # Tool checks live in the startup preflight (single mechanism)
    # plus the adapter port — not here.
    from rocket_engine.adapters.lvs_netgen import flatten_spice

    cell = sub.get("cell")
    if not cell:
        raise AssertionError(f"{label}: lvs run_live needs cell")
    tech = _resolve_sky130_deck(label, LVS_SKY130_TECH_REL)
    setup = _resolve_sky130_deck(label, LVS_SKY130_SETUP_REL)
    mag = _resolve_sky130_deck(label, f"{LVS_SKY130_MAG_DIR_REL}/{cell}.mag")
    lib = _resolve_sky130_deck(label, LVS_SKY130_SPICE_LIB_REL)
    workdir = Path(tempfile.mkdtemp(prefix="scen_live_"))
    ctx["tmpdirs"].append(workdir)
    shutil.copy(mag, workdir / f"{cell}.mag")
    try:
        ref_text = flatten_spice(Path(lib).read_text(), cell)
    except Exception as exc:
        raise AssertionError(f"{label}: cannot slice {cell}: {exc}") from exc
    if sub.get("mutate"):
        if ref_text.count(LVS_MUTATE_OLD) != 1:
            raise AssertionError(f"{label}: mismatch probe site changed")
        ref_text = ref_text.replace(LVS_MUTATE_OLD, LVS_MUTATE_NEW)
    schematic = workdir / "schematic.spice"
    schematic.write_text(ref_text)
    extracted = ctx["engine"].run(
        {
            "project_id": ctx["project_id"],
            "operation": "run_extraction",
            "arguments": {
                "cell": cell,
                "cell_file": str(workdir / f"{cell}.mag"),
                "tech_file": tech,
                "workdir": str(workdir),
                "deck": {"tool": "magic"},
            },
            "snapshot_id": ctx["ack"]["snapshot_id"],
        }
    )
    if (extracted["verdict"] or {}).get("status") != "PASS":
        raise AssertionError(
            f"{label}: extraction did not pass: {extracted['verdict']}"
        )
    layout_spice = workdir / f"{cell}.spice"
    if not layout_spice.is_file():
        raise AssertionError(f"{label}: extraction produced no spice")
    out = ctx["engine"].run(
        {
            "project_id": ctx["project_id"],
            "operation": ctx["operation"],
            "arguments": {
                "layout_spice": str(layout_spice),
                "schematic_spice": str(schematic),
                "setup_file": setup,
                "workdir": str(workdir),
                "deck": {"tool": "netgen"},
            },
            "snapshot_id": ctx["ack"]["snapshot_id"],
        }
    )
    ctx["verdict"] = out["verdict"]
    return None


def _run_step(ctx, num, step):
    label = f"step {num} ({next(iter(step))})"
    if "submit" in step:
        try:
            ack = ctx["transport"].handle(
                _submit_envelope(ctx["project_id"], ctx["revision"], step)
            )
        except Exception as exc:
            want = step.get("expect_error")
            if want and getattr(exc, "code", None) == want:
                return None
            raise AssertionError(f"{label}: unexpected error {exc!r}") from exc
        if step.get("expect_error"):
            raise AssertionError(f"{label}: expected error {step['expect_error']}, got ack")
        ctx["ack"] = ack
        ctx["operation"] = step["submit"]["operation"]
        ctx["target"] = step["submit"]["target"]
        return None
    if "dispatch_fake" in step:
        _require_ack(ctx, label)
        sub = step["dispatch_fake"]
        ctx["engine"].register_solver(
            ctx["operation"],
            FakeAdapter({"findings": sub.get("findings", [])}),
            tool="fake",
        )
        out = ctx["engine"].run(
            {"project_id": ctx["project_id"], "operation": ctx["operation"],
             "arguments": {"deck": {"tool": "fake"}},
             "snapshot_id": ctx["ack"]["snapshot_id"]}
        )
        ctx["verdict"] = out["verdict"]
        return None
    if "run_live" in step:
        _require_ack(ctx, label)
        sub = step["run_live"]
        backend = sub.get("backend", "magic")
        if backend == "hdl":
            return _run_live_hdl(ctx, label, sub)
        if backend == "hdl_serv":
            return _run_live_hdl_serv(ctx, label, sub)
        if backend == "hdl_picorv32":
            return _run_live_hdl_picorv32(ctx, label, sub)
        if backend == "hdl_sdm":
            return _run_live_hdl_sdm(ctx, label, sub)
        if backend == "ngspice_bandgap":
            return _run_live_ngspice_bandgap(ctx, label, sub)
        if backend == "ngspice_sdtop":
            return _run_live_ngspice_sdtop(ctx, label, sub)
        if backend == "sax_mzi":
            return _run_live_sax_mzi(ctx, label, sub)
        if backend == "klayout_mzi":
            return _run_live_klayout_mzi(ctx, label, sub)
        if backend == "extract_lvs_sky130":
            return _run_live_lvs_sky130(ctx, label, sub)
        try:
            table = _BACKENDS[backend]
        except KeyError:
            raise AssertionError(f"{label}: unknown backend {backend}") from None
        fixture = table["fixtures"] / f"{sub['cell']}{table['ext']}"
        if not fixture.is_file():
            raise AssertionError(f"{label}: no fixture for cell {sub['cell']}")
        workdir = Path(tempfile.mkdtemp(prefix="scen_live_"))
        ctx["tmpdirs"].append(workdir)
        layout_file = workdir / fixture.name
        shutil.copy(fixture, layout_file)
        arguments = {
            "tech": sub.get("tech", table["tech"]),
            "cell": sub["cell"],
            table["file_key"]: str(layout_file),
            "workdir": str(workdir),
        }
        if table["deck"] is not None:
            arguments["deck"] = {"tool": table["deck"]}
        if "rules" in table:
            arguments["rules"] = sub.get("rules", table["rules"])
        if table.get("sky130_deck"):
            arguments["deck_file"] = _resolve_sky130_deck(label)
        out = ctx["engine"].run(
            {
                "project_id": ctx["project_id"],
                "operation": ctx["operation"],
                "arguments": arguments,
                "snapshot_id": ctx["ack"]["snapshot_id"],
            }
        )
        ctx["verdict"] = out["verdict"]
        return None
    if "assert_verdict" in step:
        verdict = ctx.get("verdict") or {}
        got = verdict.get("status")
        if got != step["assert_verdict"]:
            reason = verdict.get("reason")
            detail = f" ({reason})" if reason else ""
            raise AssertionError(
                f"{label}: verdict {got}{detail}, want {step['assert_verdict']}"
            )
        return None
    if "assert_event" in step:
        names = [e["event"] for e in ctx["engine"].events_since(0)]
        if step["assert_event"] not in names:
            raise AssertionError(f"{label}: no {step['assert_event']} in {names}")
        return None
    raise AssertionError(f"{label}: unknown step verb")


def required_path_tools(doc):
    """Sorted PATH binaries a scenario doc needs (SCENARIO-PATH).

    Derived from each run_live backend (default backend "magic",
    matching _run_step); unknown backends contribute nothing (the
    mid-run step still rejects them as unknown).
    """
    tools = set()
    for step in doc.get("steps", []) or []:
        if not isinstance(step, dict) or "run_live" not in step:
            continue
        sub = step["run_live"] or {}
        tools.update(_BACKEND_PATH_TOOLS.get(sub.get("backend", "magic"), ()))
    return sorted(tools)


def preflight_path_tools(doc):
    """{tool: cause} for needed PATH binaries that are missing or wrong.

    netgen goes through the LVS identity probe, not bare PATH
    presence: the Schoeberl mesher shares the name.
    """
    from rocket_engine.adapters.lvs_netgen import resolve_netgen

    missing = {}
    for tool in required_path_tools(doc):
        if shutil.which(tool) is None:
            missing[tool] = "absent"
        elif tool == "netgen" and resolve_netgen() is None:
            missing[tool] = "impostor"
    return missing


def run_scenario(path):
    doc = yaml.load(Path(path).read_text())
    missing = preflight_path_tools(doc)
    if missing:
        return {
            "name": doc.get("name", Path(path).name),
            "passed": False,
            "failures": [
                _startup_line(tool, cause) for tool, cause in missing.items()
            ],
        }
    engine = doc.get("engine", {})
    project_id = engine.get("project_id", "demo")
    live = Engine(
        project_id=project_id,
        actor=engine.get("actor", {"kind": "user"}),
        catalog_root=".",
    )
    ctx = {
        "project_id": project_id,
        "revision": engine.get("revision", "p12"),
        "engine": live,
        "transport": McpTransport(live, project_id=project_id),
        "tmpdirs": [],
    }
    failures = []
    try:
        for num, step in enumerate(doc.get("steps", []), 1):
            try:
                _run_step(ctx, num, step)
            except AssertionError as exc:
                failures.append(str(exc))
                break
    finally:
        for tmpdir in ctx["tmpdirs"]:
            shutil.rmtree(tmpdir, ignore_errors=True)
    return {"name": doc.get("name", Path(path).name), "passed": not failures,
            "failures": failures}


def run_all(directory):
    results = [run_scenario(p) for p in sorted(Path(directory).glob("*.yaml"))]
    passed = sum(1 for r in results if r["passed"])
    return {"scenarios": results, "passed": passed, "failed": len(results) - passed}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run engine scenario files.")
    parser.add_argument("directory")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-q", action="store_true")
    args = parser.parse_args(argv)
    report = run_all(args.directory)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for item in report["scenarios"]:
            status = "PASS" if item["passed"] else "FAIL"
            print(f"{status} {item['name']}")
            if not args.q:
                for failure in item["failures"]:
                    print(f"  - {failure}")
        print(f"{report['passed']} passed, {report['failed']} failed")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
