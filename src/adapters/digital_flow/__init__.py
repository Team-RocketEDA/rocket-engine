"""LibreLane digital-flow solver adapter: run_digital_flow behind the ToolAdapter port.

Protocol (LibreLane 3.0.17 Classic, subprocess): stage the project RTL
into a design dir (`src/` plus a generated `digital_flow_config.json`
carrying DESIGN_NAME/VERILOG_FILES/CLOCK_PERIOD/CLOCK_PORT/PDK), run
`librelane <config> --tag <tag> --pdk <pdk> --overwrite`
(`--pdk-root`/`--scl` when the job names them) under the job timeout in
its own process group, then scan `design/runs/<tag>/` step dirs for
per-stage evidence (config, reports, DB checkpoints). Each D11-D27 gate
passes on its step's evidence, fails loudly naming the stage plus the
report, or is force-bypassed via the job `force` list (a warning, never
silent). A nonzero exit marks the first failing gate failed and
everything downstream not_run; a timeout SIGKILLs the whole tree and
reports digital_flow_timeout with whatever partial evidence survived.

Tool resolution: an explicit job `tool_dir` wins, else PATH, and the
resolved binary must answer `librelane --version` with the pinned
3.0.17 banner — ambient installs are kept and version-asserted, never
reinstalled. Where the tools live on disk is B10/PROV scope.
"""

import json
import os
import re
import shutil
import signal
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...execution.runner import tool_roots
from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_digital_flow"
_TOOL = "librelane"
_FLOW = "Classic"
_PIN = "3.0.17"
_TIMEOUT_S = 3600
_VERSION_TIMEOUT_S = 30

_CONFIG_NAME = "digital_flow_config.json"
_LOG_NAME = "digital_flow.log"
_DESIGN_DIR = "design"
_SRC_DIR = "src"
_RUNS_DIR = "runs"

_MISSING_REMEDY = (
    "install the pinned LibreLane 3.0.17 supported distribution (run "
    "scripts/provision_toolchain.sh --install for the pinned AppImage per "
    "the upstream install docs); inside a nix-shell env, `librelane "
    "--version` must report 3.0.17 (see "
    "src/interfaces/setup_catalogue.yaml id librelane)"
)

_TOP_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TAG_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
_PDK_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
_ERROR_RE = re.compile(r"ERROR: (.*)")
_DRC_TOTAL_RE = re.compile(r"(?i)total\s*[:=]\s*(\d+)")
_DRC_COUNT_RE = re.compile(r"(?i)(\d+)\s+violations?")
_DRC_CLEAN_RE = re.compile(r"(?i)(no violations?\b|drc clean)")
_STA_FAIL_RE = re.compile(r"(?i)violated")
_EQUIV_FAIL_RE = re.compile(r"(?i)\b(not equivalent|inequivalent|mismatch|failed|failure)\b")
_LVS_MATCH_RE = re.compile(r"(Circuits match uniquely|Netlists match uniquely)\.")
_LVS_MISMATCH_RES = (
    re.compile(r"Netlists do not match\."),
    re.compile(r"\*\*\* MISMATCH \*\*\*"),
)

# PRD D11-D27 projected onto LibreLane Classic step dirs: lowercase
# substrings matched against the step-dir name (first path part under
# runs/<tag>/), plus filename substrings for that stage's artifacts.
# Step IDs drift across LibreLane versions; the match stays substring
# on purpose, and a gate with no match fails loudly (never skipped).
_STAGES = (
    {"id": "D11", "label": "Start the LibreLane flow", "steps": (), "artifacts": ()},
    {"id": "D12", "label": "Synthesize to standard cells",
     "steps": ("synthesis",), "artifacts": (".v", "stat")},
    {"id": "D13", "label": "Pre-placement constraint and timing check",
     "steps": ("sdc", "constraint", "staprepnr"), "artifacts": (".rpt", ".sdc", ".log")},
    {"id": "D14", "label": "Floorplan", "steps": ("floorplan",),
     "artifacts": (".odb", ".def")},
    {"id": "D15", "label": "Power grid", "steps": ("tapendcap", "pdn", "powergrid"),
     "artifacts": (".def", ".rpt")},
    {"id": "D16", "label": "Placement", "steps": ("placement", "repairdesign"),
     "artifacts": (".odb", ".def", ".rpt")},
    {"id": "D17", "label": "Clock tree", "steps": ("cts", "clocktree"),
     "artifacts": (".odb", ".rpt", ".log")},
    {"id": "D18", "label": "Global routing", "steps": ("globalrout", "groute"),
     "artifacts": (".guide", ".rpt")},
    {"id": "D19", "label": "Detail routing",
     "steps": ("detailedrout", "detailroute", "droute", "antenna"),
     "artifacts": (".odb", ".def", ".rpt")},
    {"id": "D20", "label": "Filler and density",
     "steps": ("filler", "densityfill", "fill"), "artifacts": (".odb", ".def")},
    {"id": "D21", "label": "RC extraction", "steps": ("rcx", "parasitic"),
     "artifacts": (".spef",)},
    {"id": "D22", "label": "Post-PNR STA", "steps": ("stapostpnr", "stamidpnr"),
     "artifacts": (".rpt",)},
    {"id": "D23", "label": "Power and IR drop", "steps": ("irdrop", "power", "redist"),
     "artifacts": (".rpt",)},
    {"id": "D24", "label": "Stream GDS/LEF views",
     "steps": ("writegds", "writeviews", "streamout", "gds"),
     "artifacts": (".gds", ".lef")},
    {"id": "D25", "label": "Foundry-deck DRC", "steps": ("drc", "cvc"),
     "artifacts": (".rpt", ".lyrdb")},
    {"id": "D26", "label": "LVS vs reference", "steps": ("lvs", "netgen", "extract"),
     "artifacts": (".out", ".rpt", ".spice")},
    {"id": "D27", "label": "Equivalence and final gates",
     "steps": ("eqy", "equiv", "signoff", "finish"), "artifacts": (".rpt", ".log")},
)
_STAGE_IDS = tuple(stage["id"] for stage in _STAGES)

_EVIDENCE_CAP = 25
_REPORT_READ_BYTES = 65536
_STREAM_KEEP_BYTES = 131072


def _scan_run(run_dir):
    """Map step-dir names to their files under one run root.

    Args:
        run_dir: runs/<tag>/ dir path, or None when the flow never
            created it.

    Returns:
        Step-dir name to sorted file-path list (empty when no run).
    """
    found = {}
    if run_dir is None or not Path(run_dir).is_dir():
        return found
    root = Path(run_dir)
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if len(rel.parts) < 2:
            continue
        found.setdefault(rel.parts[0], []).append(path)
    return found


def _match_steps(step_names, needles):
    """Step-dir names containing any needle (case-insensitive).

    Args:
        step_names: Step-dir names from the run scan.
        needles: Lowercase substrings to match.

    Returns:
        Sorted matching step-dir names.
    """
    return sorted(name for name in step_names if any(n in name.lower() for n in needles))


def _evidence_files(scan, step_names, artifacts):
    """Artifact files under the matched step dirs, capped.

    Args:
        scan: Step-dir to file-list mapping from the run scan.
        step_names: Matched step-dir names for one stage.
        artifacts: Lowercase filename substrings for the stage.

    Returns:
        Sorted matching file paths, capped at _EVIDENCE_CAP.
    """
    out = []
    for name in step_names:
        for path in scan.get(name, []):
            lowered = path.name.lower()
            if any(a in lowered for a in artifacts):
                out.append(path)
    return sorted(out)[:_EVIDENCE_CAP]


def _read_text_capped(paths):
    """Decode the head of each report path for content checks.

    Args:
        paths: Report file paths to read.

    Returns:
        Joined decoded text (unreadable files skipped).
    """
    chunks = []
    for path in paths:
        try:
            data = Path(path).read_bytes()[:_REPORT_READ_BYTES]
        except OSError:
            continue
        chunks.append(data.decode("utf-8", "replace"))
    return "\n".join(chunks)


def _first_error(paths):
    """First `ERROR:` line across one stage's files, with its file.

    Args:
        paths: File paths to search.

    Returns:
        (line, path) for the first ERROR line, else (None, None).
    """
    for path in sorted(paths):
        try:
            data = Path(path).read_bytes()[:_REPORT_READ_BYTES]
        except OSError:
            continue
        for line in data.decode("utf-8", "replace").splitlines():
            match = _ERROR_RE.search(line)
            if match is not None:
                return match.group(1).strip(), str(path)
    return None, None


def _parse_drc_total(text):
    """DRC violation total from report text, or None when unparseable.

    Args:
        text: Combined DRC report text.

    Returns:
        Integer total when a count or clean marker parses, else None.
    """
    match = _DRC_TOTAL_RE.search(text) or _DRC_COUNT_RE.search(text)
    if match is not None:
        for group in match.groups():
            if group is not None:
                return int(group)
    if _DRC_CLEAN_RE.search(text):
        return 0
    return None


def _tail_kept(text):
    """Bound one captured stream to its tail with a marker.

    Args:
        text: Full captured stream text.

    Returns:
        Tail text, marked when truncated.
    """
    encoded = text.encode("utf-8", "replace")
    if len(encoded) <= _STREAM_KEEP_BYTES:
        return text
    tail = encoded[-_STREAM_KEEP_BYTES:].decode("utf-8", "replace")
    return f"...[truncated to the last {_STREAM_KEEP_BYTES} bytes]\n{tail}"


def _stage_gate(stage, scan, native):
    """Judge one stage gate from the run scan plus native context.

    D11 passes on the staged config plus the versioned binary (no run
    dirs needed); D12 fails on any synthesis ERROR line with the first
    line as the cause; D22/D25/D26/D27 apply their report-content
    rules; D24 requires a non-empty GDS; the rest pass on matched
    step plus artifact evidence.

    Args:
        stage: Stage row (id, label, steps, artifacts).
        scan: Step-dir to file-list mapping from the run scan.
        native: Native output with config, version, and run context.

    Returns:
        (ok, reason, steps, evidence, reports) for the gate.
    """
    stage_id = stage["id"]
    run_dir = native.get("run_dir") or "run dir"
    if stage_id == "D11":
        config = native.get("config")
        version = native.get("librelane_version") or ""
        if config is not None and Path(config).is_file() and version:
            count = len(scan)
            evidence = [config]
            return True, f"flow {native.get('flow')}, {count} step dirs", [], evidence, evidence
        return False, "no staged flow config", [], [], []
    steps = _match_steps(scan, stage["steps"])
    evidence = _evidence_files(scan, steps, stage["artifacts"])
    reports = [str(p) for p in evidence]
    if stage_id == "D12":
        synth_files = [p for name in steps for p in scan.get(name, [])]
        cause, cause_file = _first_error(synth_files)
        if cause is not None:
            return False, f"synthesis error: {cause}", steps, evidence, [cause_file]
        if not evidence:
            return False, f"no synthesis evidence in {run_dir}", steps, [], []
        return True, f"{len(evidence)} netlist/stat artifacts", steps, evidence, reports
    if stage_id == "D22":
        if not evidence:
            return False, f"no STA reports in {run_dir}", steps, [], []
        if _STA_FAIL_RE.search(_read_text_capped(evidence)):
            return False, "timing violated", steps, evidence, reports
        return True, f"{len(evidence)} STA reports", steps, evidence, reports
    if stage_id == "D24":
        gds = [p for p in evidence if p.name.lower().endswith((".gds", ".gds.gz"))]
        if not gds:
            return False, f"no GDS evidence in {run_dir}", steps, evidence, reports
        sized = [p for p in gds if p.is_file() and p.stat().st_size > 0]
        if not sized:
            return False, "GDS artifact is empty", steps, evidence, [str(p) for p in gds]
        return True, f"GDS {sized[0].name}", steps, evidence, [str(p) for p in sized]
    if stage_id == "D25":
        if not evidence:
            return False, f"no DRC reports in {run_dir}", steps, [], []
        total = _parse_drc_total(_read_text_capped(evidence))
        if total is None:
            return False, "unparseable DRC report", steps, evidence, reports
        if total > 0:
            return False, f"{total} DRC violations", steps, evidence, reports
        return True, "DRC total 0", steps, evidence, reports
    if stage_id == "D26":
        if not evidence:
            return False, f"no LVS reports in {run_dir}", steps, [], []
        text = _read_text_capped(evidence)
        if _LVS_MATCH_RE.search(text):
            return True, "netlists match", steps, evidence, reports
        if any(rx.search(text) for rx in _LVS_MISMATCH_RES):
            return False, "netlists do not match", steps, evidence, reports
        return False, "unparseable LVS report", steps, evidence, reports
    if stage_id == "D27":
        if not evidence:
            return False, f"no equivalence evidence in {run_dir}", steps, [], []
        if _EQUIV_FAIL_RE.search(_read_text_capped(evidence)):
            return False, "equivalence failure", steps, evidence, reports
        return True, f"{len(evidence)} equivalence reports", steps, evidence, reports
    if not steps and not evidence:
        return False, f"no {stage['label'].lower()} evidence in {run_dir}", steps, [], []
    if not evidence:
        return False, f"no {stage['label'].lower()} artifacts in {', '.join(steps)}", steps, [], []
    return True, f"{len(evidence)} artifacts", steps, evidence, reports


def _evaluate_stages(native):
    """Judge every D11-D27 gate, applying force-bypass and exit rules.

    A failed run marks the first failing gate failed and evidence-free
    downstream gates not_run (no violation — they never ran); a clean
    exit turns every missing gate into a failure. Forced failures
    become warnings; force on a passing gate is inert. D27 additionally
    fails as blocked while any earlier gate stays failed.

    Args:
        native: Native output with exit_code, run scan inputs, the
            forced list, and flow context.

    Returns:
        (stages, violations) with per-stage status plus evidence and
            gate/forced violations.
    """
    scan = _scan_run(native.get("run_dir"))
    forced = set(native.get("forced") or [])
    exit_code = native.get("exit_code")
    failed_run = exit_code is not None and exit_code != 0
    judged = []
    for stage in _STAGES:
        ok, reason, steps, evidence, reports = _stage_gate(stage, scan, native)
        judged.append(
            {
                "id": stage["id"],
                "label": stage["label"],
                "ok": ok,
                "reason": reason,
                "steps": steps,
                "evidence": [str(p) for p in evidence],
                "reports": [str(r) for r in reports],
            }
        )
    blocked = [j["id"] for j in judged[:-1] if not j["ok"] and j["id"] not in forced]
    if blocked:
        final = judged[-1]
        final["ok"] = False
        final["reason"] = f"blocked by {', '.join(blocked)}"
        if not final["reports"]:
            final["reports"] = [native.get("run_dir") or native.get("design_dir", "")]
    first_fail = next((i for i, j in enumerate(judged) if not j["ok"]), None)
    stages = []
    violations = []
    for index, entry in enumerate(judged):
        status = "pass" if entry["ok"] else "fail"
        if failed_run and first_fail is not None and index > first_fail:
            if not entry["steps"] and not entry["evidence"]:
                status = "not_run"
        if status == "fail" and entry["id"] in forced:
            status = "forced"
        stages.append(
            {
                "id": entry["id"],
                "label": entry["label"],
                "status": status,
                "steps": entry["steps"],
                "evidence": entry["evidence"],
                "reports": entry["reports"],
                "reason": entry["reason"],
            }
        )
        if status == "fail":
            report = entry["reports"][0] if entry["reports"] else native.get("run_dir")
            message = f"{entry['id']} {entry['label']} failed: {entry['reason']}"
            if report:
                message += f" (see {report})"
            violation = {
                "rule": "digital_flow_gate",
                "severity": "error",
                "message": message,
            }
            if report:
                violation["file"] = report
            violations.append(violation)
        elif status == "forced":
            report = entry["reports"][0] if entry["reports"] else native.get("run_dir")
            message = (
                f"{entry['id']} {entry['label']} gate bypassed "
                f"via force: {entry['reason']}"
            )
            if report:
                message += f" (see {report})"
            violation = {
                "rule": "digital_flow_forced",
                "severity": "warning",
                "message": message,
            }
            if report:
                violation["file"] = report
            violations.append(violation)
    if failed_run and not [v for v in violations if v["severity"] == "error"]:
        violations.append(
            {
                "rule": "digital_flow_error",
                "severity": "error",
                "message": f"librelane exited {exit_code} with no failing gate",
            }
        )
    return stages, violations


class LibrelaneFlowAdapter(ToolAdapter):
    """run_digital_flow via LibreLane: RTL to verified GDS plus evidence.

    Serves the run_digital_flow operation with deck.tool `librelane`
    (the only tool). Stages the project RTL into a LibreLane design
    dir, runs the Classic flow as a subprocess under the job timeout,
    and judges the D11-D27 stage gates from the run's step dirs:
    per-stage evidence is the config, reports, and DB checkpoints
    found there, failures name the stage plus the report, and the job
    `force` list bypasses named gates as warnings.

    Job keys:
        sources (required): Verilog source paths staged to design/.
        top (required): Top module name (plain identifier).
        clock_port: Clock port name (default clk; None omits it).
        clock_period: Clock period in ns (default 10.0).
        pdk: PDK name for --pdk (default sky130A).
        pdk_root: PDK root dir for --pdk-root; omitted when None.
        scl: Standard-cell library for --scl; omitted when None.
        flow: Flow name; only Classic is supported.
        tag: Run tag for runs/<tag>/ (default engine).
        force: Stage ids (D11-D27) whose gate failures bypass.
        config: Extra config mapping merged into the flow config.
        timeout_s: Flow budget in seconds (default 3600).
        tool_dir: Directory holding librelane; PATH otherwise.
        deck: Optional mapping; deck.tool must be librelane here.
        workdir: Run directory (default ".").

    Args:
        runner: Optional isolated runner; direct subprocess when None.

    Caution: Overwrites design/, the flow config, and digital_flow.log
        in the workdir; long runs die by timeout_s with partial
        evidence, never a hang — and a failed run never parses as
        clean.
    """

    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        """Report the served operation, tool, flow, and stage gates.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one flow run per job).

        Returns:
            Capability mapping with operations, tool, flow, stages,
                and force-bypass support.
        """
        return {
            "operations": [OPERATION],
            "tool": _TOOL,
            "flow": _FLOW,
            "stages": list(_STAGE_IDS),
            "force": True,
        }

    def preflight(self, job):
        """Check operation, deck, flow inputs, sources, and librelane.

        Cheap deterministic checks first, tool resolution and its
        version probe last; the resolved binary must report the
        pinned 3.0.17 banner.

        Args:
            job: Solver job with operation run_digital_flow plus
                sources, top, clock, PDK, tag, force, and config
                inputs.

        Returns:
            Checked mapping with the resolved librelane path and
                version plus the staged flow inputs.

        Raises:
            AdapterError: unsupported_operation for another
                operation or a foreign deck.tool, invalid_command
                for bad flow inputs, invalid_reference for missing
                sources or pdk_root, missing_dependency for an
                unresolvable or unpinned librelane.
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"LibreLane flow handles {OPERATION}, got {job.get('operation')}.",
            )
        deck = job.get("deck")
        if deck is not None:
            if not isinstance(deck, dict):
                raise AdapterError("invalid_command", f"Bad deck: {deck!r}.")
            if deck.get("tool", _TOOL) != _TOOL:
                raise AdapterError(
                    "unsupported_operation",
                    f"LibreLane flow handles deck.tool {_TOOL}, got {deck.get('tool')}.",
                )
        top = job.get("top")
        if not isinstance(top, str) or not _TOP_RE.fullmatch(top):
            raise AdapterError("invalid_command", f"Bad top: {top!r}.")
        timeout = job.get("timeout_s", _TIMEOUT_S)
        if (
            not isinstance(timeout, (int, float))
            or isinstance(timeout, bool)
            or not timeout > 0
        ):
            raise AdapterError("invalid_command", f"Bad timeout_s: {timeout!r}.")
        flow = job.get("flow", _FLOW)
        if flow != _FLOW:
            raise AdapterError(
                "invalid_command", f"Bad flow: {flow!r} (only {_FLOW})."
            )
        tag = job.get("tag", "engine")
        if not isinstance(tag, str) or not _TAG_RE.fullmatch(tag):
            raise AdapterError("invalid_command", f"Bad tag: {tag!r}.")
        pdk = job.get("pdk", "sky130A")
        if not isinstance(pdk, str) or not _PDK_RE.fullmatch(pdk):
            raise AdapterError("invalid_command", f"Bad pdk: {pdk!r}.")
        period = job.get("clock_period", 10.0)
        if (
            not isinstance(period, (int, float))
            or isinstance(period, bool)
            or not period > 0
        ):
            raise AdapterError("invalid_command", f"Bad clock_period: {period!r}.")
        port = job.get("clock_port", "clk")
        if port is not None and (
            not isinstance(port, str) or not _TOP_RE.fullmatch(port)
        ):
            raise AdapterError("invalid_command", f"Bad clock_port: {port!r}.")
        sources = job.get("sources") or []
        missing = [s for s in sources if not Path(s).is_file()]
        if not sources or missing:
            raise AdapterError(
                "invalid_reference", f"Sources not found: {missing or sources}."
            )
        basenames = [Path(s).name for s in sources]
        dupes = sorted({name for name in basenames if basenames.count(name) > 1})
        if dupes:
            raise AdapterError(
                "invalid_command",
                f"Duplicate source basenames collide in design/src/: {dupes}.",
            )
        force = job.get("force", [])
        if (
            not isinstance(force, list)
            or any(not isinstance(f, str) or f not in _STAGE_IDS for f in force)
        ):
            raise AdapterError("invalid_command", f"Bad force: {force!r}.")
        extra = job.get("config", {})
        if not isinstance(extra, dict) or any(not isinstance(k, str) for k in extra):
            raise AdapterError("invalid_command", f"Bad config: {extra!r}.")
        try:
            json.dumps(extra)
        except (TypeError, ValueError) as exc:
            raise AdapterError("invalid_command", f"Bad config: {exc}.") from exc
        pdk_root = job.get("pdk_root")
        if pdk_root is not None and not Path(pdk_root).is_dir():
            raise AdapterError("invalid_reference", f"PDK root not found: {pdk_root}.")
        scl = job.get("scl")
        if scl is not None and (not isinstance(scl, str) or not scl.strip()):
            raise AdapterError("invalid_command", f"Bad scl: {scl!r}.")
        librelane = self._resolve(job)
        checked = {
            "librelane": librelane,
            "librelane_version": self._version(librelane),
            "sources": list(sources),
            "top": top,
            "clock_port": port,
            "clock_period": period,
            "pdk": pdk,
            "pdk_root": pdk_root,
            "scl": scl,
            "flow": flow,
            "tag": tag,
            "force": list(force),
            "config": dict(extra),
            "timeout_s": timeout,
        }
        if self._runner is not None:
            try:
                self._runner.preflight()
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        return checked

    def execute(self, job):
        """Stage the design, run the Classic flow bounded and cancellable.

        The flow runs in its own process group under timeout_s; expiry
        SIGKILLs the whole tree and reports a timeout native block
        with partial evidence instead of hanging the engine.

        Args:
            job: Solver job with operation run_digital_flow plus
                sources, top, clock, PDK, tag, force, and config
                inputs.

        Returns:
            Native output with exit_code, bounded streams, the full
                log path, run/config dirs, the forced list, and the
                librelane version.

        Raises:
            AdapterError: invalid_reference for a missing workdir or
                an unstageable design, plus the preflight codes
                (execute re-checks first).
        """
        checked = self.preflight(job)
        workdir = Path(job.get("workdir", "."))
        if not workdir.is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        design = workdir / _DESIGN_DIR
        try:
            src_dir = design / _SRC_DIR
            src_dir.mkdir(parents=True, exist_ok=True)
            staged = []
            for source in checked["sources"]:
                dest = src_dir / Path(source).name
                shutil.copy(source, dest)
                staged.append(str(dest))
            config = {
                "DESIGN_NAME": checked["top"],
                "VERILOG_FILES": staged,
                "CLOCK_PERIOD": checked["clock_period"],
                "PDK": checked["pdk"],
            }
            if checked["clock_port"] is not None:
                config["CLOCK_PORT"] = checked["clock_port"]
            config.update(checked["config"])
            config_path = design / _CONFIG_NAME
            config_path.write_text(json.dumps(config, indent=2) + "\n")
        except OSError as exc:
            raise AdapterError(
                "invalid_reference", f"Cannot stage digital-flow design: {exc}."
            ) from exc
        argv = [
            checked["librelane"],
            str(config_path),
            "--tag",
            checked["tag"],
            "--pdk",
            checked["pdk"],
            "--overwrite",
        ]
        if checked["pdk_root"] is not None:
            argv += ["--pdk-root", checked["pdk_root"]]
        if checked["scl"] is not None:
            argv += ["--scl", checked["scl"]]
        binds = tool_roots([checked["librelane"]])
        if checked["pdk_root"] is not None:
            binds = list(binds) + [(checked["pdk_root"], checked["pdk_root"])]
        timed_out, proc = self._run(argv, str(workdir), checked["timeout_s"], binds)
        stdout = proc.stdout if proc is not None else ""
        stderr = proc.stderr if proc is not None else ""
        (workdir / _LOG_NAME).write_text(
            f"$ {' '.join(argv)}\n{stdout}\n{stderr}", encoding="utf-8"
        )
        run_dir = design / _RUNS_DIR / checked["tag"]
        return {
            "exit_code": proc.returncode if proc is not None else None,
            "stdout": _tail_kept(stdout or ""),
            "stderr": _tail_kept(stderr or ""),
            "log": _tail_kept(f"{stdout or ''}\n{stderr or ''}"),
            "log_file": str(workdir / _LOG_NAME),
            "timed_out": timed_out,
            "workdir": str(workdir),
            "design_dir": str(design),
            "run_dir": str(run_dir) if run_dir.is_dir() else None,
            "config": str(config_path),
            "top": checked["top"],
            "tag": checked["tag"],
            "pdk": checked["pdk"],
            "flow": checked["flow"],
            "forced": list(checked["force"]),
            "librelane_version": checked["librelane_version"],
            "timeout_s": checked["timeout_s"],
        }

    def parse(self, native_output):
        """Judge the D11-D27 gates from the run's step evidence.

        Timeouts report digital_flow_timeout plus the partial gates;
        failed runs fail the first gate and mark evidence-free
        downstream gates not_run; clean exits fail every gateless
        stage. Forced failures warn instead of erroring, and a flow
        failure always names its stage plus report.

        Args:
            native_output: Native output from execute with exit
                state, run/config dirs, the forced list, and flow
                context.

        Returns:
            {total, violations[], measurements{}} with the per-stage
                table plus gds, netlist, spef, drc_total, lvs_match,
                version, tag, run_dir, and timed_out evidence.

        Raises:
            AdapterError: runner_unavailable when the output has no
                exit code and no timeout — unparseable never parses
                as clean.
        """
        exit_code = native_output.get("exit_code")
        timed_out = bool(native_output.get("timed_out"))
        if exit_code is None and not timed_out:
            raise AdapterError(
                "runner_unavailable", "Native output has no exit code."
            )
        stages, violations = _evaluate_stages(native_output)
        by_id = {stage["id"]: stage for stage in stages}
        gds = next(
            (
                path
                for path in by_id.get("D24", {}).get("reports", [])
                if path.lower().endswith((".gds", ".gds.gz"))
            ),
            None,
        )
        netlist = next(
            (
                path
                for path in by_id.get("D12", {}).get("evidence", [])
                if path.lower().endswith(".v")
            ),
            None,
        )
        spef = next(
            (
                path
                for path in by_id.get("D21", {}).get("evidence", [])
                if path.lower().endswith(".spef")
            ),
            None,
        )
        drc_reports = by_id.get("D25", {}).get("evidence", [])
        drc_total = _parse_drc_total(_read_text_capped(drc_reports))
        lvs_text = _read_text_capped(by_id.get("D26", {}).get("evidence", []))
        if _LVS_MATCH_RE.search(lvs_text):
            lvs_match = True
        elif any(rx.search(lvs_text) for rx in _LVS_MISMATCH_RES):
            lvs_match = False
        else:
            lvs_match = None if not lvs_text.strip() else False
        if timed_out:
            timeout_s = native_output.get("timeout_s")
            violations = [
                {
                    "rule": "digital_flow_timeout",
                    "severity": "error",
                    "message": f"librelane timed out after {timeout_s}s.",
                }
            ] + violations
        measurements = {
            "flow": native_output.get("flow"),
            "tag": native_output.get("tag"),
            "top": native_output.get("top"),
            "pdk": native_output.get("pdk"),
            "librelane_version": native_output.get("librelane_version"),
            "timeout_s": native_output.get("timeout_s"),
            "timed_out": timed_out,
            "exit_code": exit_code,
            "forced": list(native_output.get("forced") or []),
            "run_dir": native_output.get("run_dir"),
            "config": native_output.get("config"),
            "stages": stages,
            "gds": gds,
            "netlist": netlist,
            "spef": spef,
            "drc_total": drc_total,
            "lvs_match": lvs_match,
        }
        return {
            "total": len(violations),
            "violations": violations,
            "measurements": measurements,
            "stages": stages,
            "gds": gds,
            "netlist": netlist,
            "spef": spef,
            "drc_total": drc_total,
            "lvs_match": lvs_match,
            "librelane_version": native_output.get("librelane_version"),
            "tag": native_output.get("tag"),
            "run_dir": native_output.get("run_dir"),
            "timed_out": timed_out,
        }

    @staticmethod
    def _resolve(job):
        tool_dir = job.get("tool_dir")
        if tool_dir:
            candidate = Path(tool_dir) / _TOOL
            if candidate.is_file():
                return str(candidate)
            raise AdapterError(
                "missing_dependency",
                f"{_TOOL} not found in {tool_dir} — {_MISSING_REMEDY}.",
            )
        found = shutil.which(_TOOL)
        if found is None:
            raise AdapterError(
                "missing_dependency",
                f"{_TOOL} not on PATH — {_MISSING_REMEDY}.",
            )
        return found

    @staticmethod
    def _version(librelane):
        """Assert the binary answers with the pinned 3.0.17 banner.

        Args:
            librelane: Resolved librelane binary path.

        Returns:
            Full `librelane --version` banner line (kept as evidence).

        Raises:
            AdapterError: missing_dependency when the probe fails,
                times out, or answers no pinned banner.
        """
        try:
            proc = subprocess.run(
                [librelane, "--version"],
                capture_output=True,
                text=True,
                timeout=_VERSION_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "missing_dependency",
                f"librelane version probe timed out at {librelane} — "
                f"{_MISSING_REMEDY}.",
            ) from exc
        except OSError as exc:
            raise AdapterError(
                "missing_dependency",
                f"librelane version probe failed at {librelane}: {exc} — "
                f"{_MISSING_REMEDY}.",
            ) from exc
        banner = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip().splitlines()
        versioned = next((line for line in banner if _PIN in line), None)
        if proc.returncode != 0 or versioned is None:
            got = banner[0] if banner else "empty banner"
            raise AdapterError(
                "missing_dependency",
                f"librelane at {librelane} reported {got!r}, want pin {_PIN} — "
                f"{_MISSING_REMEDY}.",
            )
        return versioned.strip()

    def _run(self, argv, workdir, timeout_s, extra_binds=()):
        """(timed_out, proc) for one flow run; expiry kills the tree."""
        if self._runner is not None:
            try:
                proc = self._runner.run(argv, workdir, timeout_s, extra_binds)
            except ExecutionError as exc:
                if exc.code == "runner_unavailable" and "timed out after" in str(exc):
                    return True, None
                raise AdapterError(exc.code, str(exc)) from exc
            return False, proc
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workdir,
            start_new_session=True,
        )
        try:
            out_bytes, err_bytes = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            try:
                proc.kill()
            except (ProcessLookupError, OSError):
                pass
            proc.wait()
            return True, None
        return False, subprocess.CompletedProcess(
            proc.args,
            proc.returncode,
            out_bytes.decode("utf-8", "replace"),
            err_bytes.decode("utf-8", "replace"),
        )
