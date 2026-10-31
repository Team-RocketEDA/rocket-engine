"""Sby formal solver adapter: run_formal behind the ToolAdapter port.

Protocol, verified against sby v0.70 (pinned oss-cad-suite,
bundled boolector engine): generate a `formal.sby` task from the
job (mode/depth/engines plus project sources, `prep -top`), run
`sby -f` under a timeout in its own process group, and parse the
machine-readable status file plus the DONE summary line
(PASS rc 0, FAIL rc 2, UNKNOWN rc 4, ERROR rc 16). Verdicts always
carry scope (proven/bounded/unknown/timeout) with assumptions and
counterexamples — never a bare PASS.

Tool resolution: an explicit job `tool_dir` wins, else PATH. The
sby banner is version-asserted (an impostor binary refuses as
missing_dependency); where the suite lives on disk is PROV/B10
integration scope — this adapter only requires it resolvable.
"""

import os
import re
import shutil
import signal
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...execution.runner import clean_stream, tool_roots
from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_formal"
_TIMEOUT_S = 300
_DEPTH = 20
_MODES = ("bmc", "prove", "cover")
_ENGINES = ["smtbmc boolector"]
_SBY_JOB = "formal"
_SBY_FILE = _SBY_JOB + ".sby"
_VERSION_PREFIX = "SBY "
_VERSION_TIMEOUT_S = 30
_MISSING_REMEDY = (
    "PROV bundle: install the pinned oss-cad-suite tarball per "
    "docs/provision-plan.md, or pass tool_dir."
)

_TOP_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
_ENGINE_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_. \-]*")
_DONE_RE = re.compile(r"DONE \((PASS|FAIL|UNKNOWN|ERROR), rc=(\d+)\)")
_ENGINE_STATUS_RE = re.compile(
    r"summary:\s+(engine_\d+)\s+\(([^)]+)\)\s+returned\s+(\S+)(?:\s+for\s+(\S+))?"
)
_ENGINE_NOSTATUS_RE = re.compile(r"summary:\s+(engine_\d+).*did not return a status")
_TRACE_RE = re.compile(
    r"summary:\s+(counterexample trace(?:\s+\[([^\]]+)\])?|cover trace):\s+(\S+)"
)
_ASSERT_FAIL_RE = re.compile(
    r"summary:\s+failed assertion\s+(\S+)\s+at\s+(\S+?)(?:\s+step\s+(\d+))?\s*$",
    re.M,
)
_COVER_HIT_RE = re.compile(
    r"summary:\s+reached cover statement\s+(\S+)\s+at\s+(\S+?)(?:\s+step\s+(\d+))?"
    r"\s*$",
    re.M,
)
_UNREACHED_HDR = "unreached cover statements:"
_UNREACHED_RE = re.compile(r"summary:\s+(\S+)\s+at\s+(\S+)\s*$")
_AT_RE = re.compile(r"([^:\s]+):(\d+)\.")
_YOSYS_ERR_RE = re.compile(r"(\S+?):(\d+):\s*ERROR:\s*(.+?)\s*$", re.M)
_BARE_ERR_RE = re.compile(r"ERROR:\s*(.+?)\s*$", re.M)
_PROP_RE = re.compile(r"\b(assert|assume|cover)\s*\(")


def _property_sites(sources):
    """Assume/assert/cover sites by file and line (evidence-grade).

    Line comments are stripped before matching; a site is one
    matched keyword per line. Unreadable sources are skipped, never
    fatal — the sites annotate the verdict, they are not the verdict.
    """
    assumptions, properties = [], []
    for source in sources:
        try:
            text = Path(source).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in _PROP_RE.finditer(line.split("//", 1)[0]):
                entry = {"file": str(source), "line": lineno}
                if match.group(1) == "assume":
                    assumptions.append(entry)
                else:
                    properties.append({**entry, "kind": match.group(1)})
    return assumptions, properties


def _split_at(token):
    """(file, line) from an sby `file:line.col-span` token."""
    match = _AT_RE.search(token or "")
    if match is None:
        return token, None
    return match.group(1), int(match.group(2))


def _locate(name, by_basename):
    """Staged path for an sby-reported basename, else the name as-is."""
    return by_basename.get(Path(name).name, name) if name else None


def _read_status(workdir):
    """(status, rc) from the sby status file, or (None, None)."""
    try:
        parts = (Path(workdir) / _SBY_JOB / "status").read_text().split()
    except OSError:
        return None, None
    if len(parts) >= 2 and parts[0] in ("PASS", "FAIL", "UNKNOWN", "ERROR"):
        try:
            return parts[0], int(parts[1])
        except ValueError:
            return None, None
    return None, None


def _engine_status(stdout):
    """Per-engine `returned ...` notes plus no-status notes."""
    notes = []
    for match in _ENGINE_STATUS_RE.finditer(stdout):
        engine, config, verdict, step = match.groups()
        note = f"{engine} ({config}) returned {verdict}"
        if step:
            note += f" for {step}"
        notes.append(note)
    for match in _ENGINE_NOSTATUS_RE.finditer(stdout):
        notes.append(f"{match.group(1)} did not return a status")
    return notes


def _trace_reports(stdout):
    """(kind, label, relpath) for each summary trace line."""
    reports = []
    for match in _TRACE_RE.finditer(stdout):
        kind, label, relpath = match.groups()
        reports.append(
            (
                "cover" if kind == "cover trace" else "counterexample",
                label,
                relpath,
            )
        )
    return reports


def _failure_reports(stdout):
    """Failure entries from failed-assertion and unreached-cover lines."""
    failures = []
    for match in _ASSERT_FAIL_RE.finditer(stdout):
        name, token, step = match.groups()
        file, line = _split_at(token)
        failures.append(
            {
                "property": name,
                "kind": "assert",
                "file": file,
                "line": line,
                "step": int(step) if step is not None else None,
            }
        )
    unreached = False
    for line in stdout.splitlines():
        if _UNREACHED_HDR in line:
            unreached = True
            continue
        if not unreached or "summary:" not in line:
            continue
        match = _UNREACHED_RE.search(line)
        if match is None:
            unreached = False
            continue
        name, token = match.groups()
        file, lineno = _split_at(token)
        failures.append(
            {
                "property": name,
                "kind": "cover",
                "file": file,
                "line": lineno,
                "step": None,
            }
        )
    return failures


def _cover_hits(stdout):
    """Reached-cover entries from `reached cover statement` lines."""
    hits = []
    for match in _COVER_HIT_RE.finditer(stdout):
        name, token, step = match.groups()
        file, line = _split_at(token)
        hits.append(
            {
                "property": name,
                "file": file,
                "line": line,
                "step": int(step) if step is not None else None,
            }
        )
    return hits


def _pair_traces(entries, traces, workdir, by_basename):
    """Pair failure/hit entries with trace artifacts, in order.

    Unpaired entries keep path None with present False; unpaired
    traces surface with property None — nothing silently dropped.
    """
    paired = []
    for index, entry in enumerate(entries):
        path, present, label = None, False, None
        if index < len(traces):
            label, relpath = traces[index][1], traces[index][2]
            candidate = Path(workdir) / relpath
            path, present = str(candidate), candidate.is_file()
        paired.append(
            {
                **entry,
                "file": _locate(entry.get("file"), by_basename),
                "path": path,
                "present": present,
                **({"label": label} if label else {}),
            }
        )
    for label, relpath in [t[1:] for t in traces[len(entries):]]:
        candidate = Path(workdir) / relpath
        paired.append(
            {
                "property": None,
                "path": str(candidate),
                "present": candidate.is_file(),
                **({"label": label} if label else {}),
            }
        )
    return paired


class FormalSbyAdapter(ToolAdapter):
    """run_formal via sby: bounded proof with honestly scoped verdicts.

    Serves the run_formal operation with deck.tool `sby` (the only
    tool). Generates a formal.sby task from the job's project
    sources, runs it bounded and cancellable, and parses the sby
    status plus the DONE summary into a scoped verdict: prove PASS
    is proven, bmc/cover PASS is bounded to the depth, FAIL carries
    counterexamples, inconclusive runs are unknown, and wall-clock
    exhaustion is timeout — never a bare PASS.

    Job keys:
        sources (required): RTL source paths carrying the design
            plus its assume/assert/cover properties.
        top (required): Top module name for prep -top.
        mode: bmc, prove, or cover (default bmc).
        depth: Proof bound in steps (default 20).
        engines: sby engine lines (default [smtbmc boolector]).
        timeout_s: Proof budget in seconds (default 300).
        tool_dir: Directory holding sby; PATH otherwise.
        deck: Optional mapping; deck.tool must be sby here.
        workdir: Run directory (default ".").

    Args:
        runner: Optional isolated runner; direct subprocess when None.

    Caution: Overwrites formal.sby plus the formal/ output dir in
        the workdir; exit zero is not PASS — the scope lives in
        the measurements, and unknown/timeout fail loudly.
    """

    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        """Report the served operation, tool, and proof modes.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one proof task per job).

        Returns:
            Capability mapping with operations, tool, and modes.
        """
        return {"operations": [OPERATION], "tool": "sby", "modes": list(_MODES)}

    def preflight(self, job):
        """Check operation, deck, proof inputs, sources, and sby.

        Cheap deterministic checks first, sby resolution and its
        version probe last.

        Args:
            job: Solver job with operation run_formal plus
                sources, top, mode, depth, and engines inputs.

        Returns:
            Checked mapping with the resolved sby path, banner,
                sources, top, mode, depth, engines, and timeout_s.

        Raises:
            AdapterError: unsupported_operation for another
                operation or a foreign deck.tool, invalid_command
                for bad proof inputs or deck shape, invalid_reference
                for missing sources, missing_dependency for an
                unresolvable or impostor sby.
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"Formal sby handles {OPERATION}, got {job.get('operation')}.",
            )
        deck = job.get("deck")
        if deck is not None:
            if not isinstance(deck, dict):
                raise AdapterError(
                    "invalid_command", f"Bad deck: {deck!r}."
                )
            if deck.get("tool", "sby") != "sby":
                raise AdapterError(
                    "unsupported_operation",
                    f"Formal sby handles deck.tool sby, got {deck.get('tool')}.",
                )
        timeout = job.get("timeout_s", _TIMEOUT_S)
        if (
            not isinstance(timeout, (int, float))
            or isinstance(timeout, bool)
            or not timeout > 0
        ):
            raise AdapterError("invalid_command", f"Bad timeout_s: {timeout!r}.")
        mode = job.get("mode", "bmc")
        if mode not in _MODES:
            raise AdapterError("invalid_command", f"Bad mode: {mode!r}.")
        depth = job.get("depth", _DEPTH)
        if not isinstance(depth, int) or isinstance(depth, bool) or depth <= 0:
            raise AdapterError("invalid_command", f"Bad depth: {depth!r}.")
        top = job.get("top")
        if not isinstance(top, str) or not _TOP_RE.fullmatch(top):
            raise AdapterError("invalid_command", f"Bad top: {top!r}.")
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
                f"Duplicate source basenames collide in sby src/: {dupes}.",
            )
        engines = job.get("engines", list(_ENGINES))
        if (
            not isinstance(engines, list)
            or not engines
            or any(
                not isinstance(e, str)
                or not e
                or e != e.strip()
                or not _ENGINE_RE.fullmatch(e)
                for e in engines
            )
        ):
            raise AdapterError("invalid_command", f"Bad engines: {engines!r}.")
        sby = self._resolve(job, "sby")
        if self._runner is not None:
            try:
                self._runner.preflight()
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        return {
            "sby": sby,
            "sby_version": self._probe_version(sby),
            "sources": list(sources),
            "top": top,
            "mode": mode,
            "depth": depth,
            "engines": list(engines),
            "timeout_s": timeout,
        }

    def execute(self, job):
        """Generate the sby task and run it bounded and cancellable.

        The sby run lives in its own process group under timeout_s;
        expiry SIGKILLs the whole tree and reports a timeout native
        block instead of hanging the engine.

        Args:
            job: Solver job with operation run_formal plus
                sources, top, mode, depth, and engines inputs.

        Returns:
            Native output with exit_code, streams, sby status
                inputs (workdir, sby_file), proof inputs echoed,
                the sby banner, and the timed_out flag.

        Raises:
            AdapterError: invalid_reference for a missing or
                unwritable workdir, runner_unavailable on a
                runner failure, plus the preflight codes (execute
                re-checks first).
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        sby_file = Path(workdir) / _SBY_FILE
        try:
            sby_file.write_text(
                self._sby_text(
                    checked["sources"],
                    checked["top"],
                    checked["mode"],
                    checked["depth"],
                    checked["engines"],
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            raise AdapterError(
                "invalid_reference", f"Cannot write sby task: {exc}."
            ) from exc
        timed_out, proc = self._run(
            [checked["sby"], "-f", _SBY_FILE],
            workdir,
            checked["timeout_s"],
            tool_roots([checked["sby"]]),
        )
        stdout = proc.stdout if proc is not None else ""
        stderr = proc.stderr if proc is not None else ""
        return {
            "exit_code": proc.returncode if proc is not None else None,
            "stdout": stdout,
            "stderr": stderr,
            "log": stdout,
            "timed_out": timed_out,
            "workdir": str(workdir),
            "sby_file": str(sby_file),
            "sources": checked["sources"],
            "top": checked["top"],
            "mode": checked["mode"],
            "depth": checked["depth"],
            "engines": checked["engines"],
            "sby_version": checked["sby_version"],
            "timeout_s": checked["timeout_s"],
        }

    def parse(self, native_output):
        """Parse the sby status into a scoped verdict with evidence.

        The status file wins, the DONE summary line is the fallback;
        with neither the output refuses as runner_unavailable —
        unparseable never parses as clean. Timeout natives report
        scope timeout; FAIL/UNKNOWN/ERROR always carry error
        findings, so PASS always means some scope was earned.

        Args:
            native_output: Native output from execute with the
                sby streams, workdir, proof inputs, and timed_out.

        Returns:
            {total, violations[], measurements} with scope,
                sby_status, assumptions, properties, failures,
                counterexamples, and cover witnesses.

        Raises:
            AdapterError: runner_unavailable when the output has
                no sby status and no DONE summary line.
        """
        sources = native_output.get("sources") or []
        assumptions, properties = _property_sites(sources)
        by_basename = {Path(s).name: str(s) for s in sources}
        measures = {
            "mode": native_output.get("mode"),
            "depth": native_output.get("depth"),
            "top": native_output.get("top"),
            "sby_version": native_output.get("sby_version"),
            "timeout_s": native_output.get("timeout_s"),
            "assumptions": assumptions,
            "properties": properties,
        }
        if native_output.get("timed_out"):
            timeout_s = native_output.get("timeout_s")
            measures.update(
                {
                    "scope": "timeout",
                    "sby_status": "timeout",
                    "sby_rc": None,
                    "engine_status": [],
                    "failures": [],
                    "counterexamples": [],
                    "cover_witnesses": [],
                }
            )
            violation = {
                "rule": "formal_timeout",
                "severity": "error",
                "message": f"sby timed out after {timeout_s}s.",
            }
            return {"total": 1, "violations": [violation],
                    "measurements": measures}
        workdir = native_output.get("workdir", ".")
        stdout = native_output.get("stdout", "")
        status, rc = _read_status(workdir)
        if status is None:
            done = _DONE_RE.search(stdout)
            if done is None:
                raise AdapterError(
                    "runner_unavailable",
                    "sby output has no status file and no DONE summary line.",
                )
            status, rc = done.group(1), int(done.group(2))
        engine_notes = _engine_status(stdout)
        failures = _failure_reports(stdout)
        traces = _trace_reports(stdout)
        cex_traces = [t for t in traces if t[0] == "counterexample"]
        cover_traces = [t for t in traces if t[0] == "cover"]
        counterexamples = _pair_traces(failures, cex_traces, workdir, by_basename)
        witnesses = _pair_traces(
            _cover_hits(stdout), cover_traces, workdir, by_basename
        )
        measures.update(
            {
                "sby_status": status,
                "sby_rc": rc,
                "engine_status": engine_notes,
                "failures": [
                    {**f, "file": _locate(f["file"], by_basename)}
                    for f in failures
                ],
                "counterexamples": counterexamples,
                "cover_witnesses": witnesses,
            }
        )
        if status == "PASS":
            scope = "proven" if native_output.get("mode") == "prove" else "bounded"
            measures["scope"] = scope
            return {"total": 0, "violations": [], "measurements": measures}
        if status == "FAIL":
            measures["scope"] = "bounded"
            violations = []
            for failure in failures:
                rule = "assert_fail" if failure["kind"] == "assert" else "cover_missed"
                message = f"property {failure['property']} failed"
                if failure["step"] is not None:
                    message += f" at step {failure['step']}"
                violation = {
                    "rule": rule,
                    "severity": "error",
                    "message": message,
                }
                located = _locate(failure["file"], by_basename)
                if located is not None:
                    violation["file"] = located
                if failure["line"] is not None:
                    violation["line"] = failure["line"]
                violations.append(violation)
            if not violations:
                # Defensive: an sby FAIL must never parse as clean.
                violations.append(
                    {
                        "rule": "assert_fail",
                        "severity": "error",
                        "message": f"sby reported FAIL (rc={rc}) with no "
                        "failed assertion.",
                    }
                )
            return {
                "total": len(violations),
                "violations": violations,
                "measurements": measures,
            }
        if status == "UNKNOWN":
            measures["scope"] = "unknown"
            detail = "; ".join(engine_notes) if engine_notes else "no engine status"
            violations = [
                {
                    "rule": "formal_unknown",
                    "severity": "error",
                    "message": f"sby inconclusive (rc={rc}): {detail}.",
                }
            ]
            for failure in failures:
                violation = {
                    "rule": "assert_fail",
                    "severity": "error",
                    "message": f"property {failure['property']} unproven",
                }
                located = _locate(failure["file"], by_basename)
                if located is not None:
                    violation["file"] = located
                if failure["line"] is not None:
                    violation["line"] = failure["line"]
                violations.append(violation)
            return {
                "total": len(violations),
                "violations": violations,
                "measurements": measures,
            }
        measures["scope"] = "unknown"
        violation = self._error_violation(stdout, rc, by_basename)
        measures["error"] = violation["message"]
        return {"total": 1, "violations": [violation],
                "measurements": measures}

    @staticmethod
    def _sby_text(sources, top, mode, depth, engines):
        """Render the formal.sby task for one proof job."""
        basenames = " ".join(Path(s).name for s in sources)
        lines = [
            "# Generated by FormalSbyAdapter (run_formal); do not hand-edit.",
            "[options]",
            f"mode {mode}",
            f"depth {depth}",
            "",
            "[engines]",
            *engines,
            "",
            "[script]",
            f"read -formal {basenames}",
            f"prep -top {top}",
            "",
            "[files]",
            *sources,
        ]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _error_violation(stdout, rc, by_basename):
        """The sby ERROR detail as one error violation, located when possible."""
        match = _YOSYS_ERR_RE.search(stdout)
        if match is not None:
            file, line, message = match.groups()
            return {
                "rule": "formal_error",
                "severity": "error",
                "message": message,
                "file": _locate(file, by_basename),
                "line": int(line),
            }
        bare = _BARE_ERR_RE.search(stdout)
        detail = bare.group(1) if bare else f"sby errored (rc={rc})"
        return {"rule": "formal_error", "severity": "error", "message": detail}

    @staticmethod
    def _resolve(job, binary):
        tool_dir = job.get("tool_dir")
        if tool_dir:
            candidate = Path(tool_dir) / binary
            if candidate.is_file():
                return str(candidate)
            raise AdapterError(
                "missing_dependency",
                f"{binary} not found in {tool_dir} ({_MISSING_REMEDY}).",
            )
        found = shutil.which(binary)
        if found is None:
            raise AdapterError(
                "missing_dependency",
                f"{binary} not on PATH ({_MISSING_REMEDY}).",
            )
        return found

    @staticmethod
    def _probe_version(sby):
        try:
            proc = subprocess.run(
                [sby, "--version"],
                capture_output=True,
                text=True,
                timeout=_VERSION_TIMEOUT_S,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AdapterError(
                "missing_dependency",
                f"sby version probe failed for {sby}: {exc} ({_MISSING_REMEDY}).",
            ) from exc
        banner = (proc.stdout or "").strip() or (proc.stderr or "").strip()
        if proc.returncode != 0 or not banner.startswith(_VERSION_PREFIX):
            raise AdapterError(
                "missing_dependency",
                f"sby at {sby} failed its version probe: {banner!r} "
                f"({_MISSING_REMEDY}).",
            )
        return banner

    def _run(self, argv, workdir, timeout_s, extra_binds=()):
        """(timed_out, proc) for one sby run; expiry kills the tree."""
        if self._runner is not None:
            try:
                proc = self._runner.run(argv, workdir, timeout_s, extra_binds)
            except ExecutionError as exc:
                if (
                    exc.code == "runner_unavailable"
                    and "timed out after" in str(exc)
                ):
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
        return (
            False,
            subprocess.CompletedProcess(
                proc.args,
                proc.returncode,
                clean_stream(out_bytes),
                clean_stream(err_bytes),
            ),
        )
