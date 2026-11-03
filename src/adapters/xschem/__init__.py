"""Xschem schematic deck adapter (DECK-XSCHEM): netlist, then sim.

Protocol, verified against XSCHEM V3.4.8 on this host: batch
netlist is `xschem -x -q --rcfile <rc> -s -n <sch> -o <dir>
-N <name>` (add `-f` for a flat netlist, `-S` when the schematic
owns the sim, `--command/--script` for scripted flows). Project
rcfiles may hardcode `XSCHEM_SHAREDIR` to a path that does not
exist on the run host (a fixture xschemrc pointed at
`/usr/share/xschem` while the install lives under
`/usr/local`); the batch then exits 0 with no output and only a
`Tcl_AppInit() err` line in the log — silent-fail. The adapter
wraps the project rcfile: it pins `XSCHEM_SHAREDIR` to the real
install around the project source and re-pins after it, detects
the init error loudly, and refuses a missing netlist output
instead of fake-greening. `DISPLAY` is scrubbed so a dead remote
display can never pop (or hang) a GUI. Netgen-style: the verdict
always comes from artifacts and logs, never the exit code; a
missing binary fails with the PROV remedy. `** sch_path` /
`** sym_path` headers embed the checkout path, so netlists
normalize to basenames before any byte-compare.

Engine wiring (vocabulary operation, composition/MCP
registration) belongs to the owning surface; this file staffs
the solver with operation `run_xschem`.
"""

import re
import shutil
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...interfaces import ToolAdapter
from ...interfaces.runparams import MAX_TIMEOUT_S, MIN_TIMEOUT_S
from ..errors import AdapterError

OPERATION = "run_xschem"
_TIMEOUT_S = 120
_INIT_ERR_RE = re.compile(r"Tcl_AppInit\(\) err|cannot find .*xschem\.tcl")
_VERSION_RE = re.compile(r"XSCHEM V3")
_SCH_PATH_RE = re.compile(r"^(\*\* (?:sch_path|sym_path):\s*).*[/\\]([^/\\\s]+)\s*$", re.M)


def _budget_or_raise(job):
    """Job solver budget: validated, or the adapter default.

    Args:
        job: Solver job, maybe with a `timeout_s`.

    Returns:
        Budget seconds for every `_run` call.

    Raises:
        AdapterError: invalid_command for a boolean,
            non-number, or out-of-bounds budget.
    """
    timeout = job.get("timeout_s", _TIMEOUT_S)
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not MIN_TIMEOUT_S <= timeout <= MAX_TIMEOUT_S
    ):
        raise AdapterError(
            "invalid_command", f"Bad timeout_s: {timeout!r}."
        )
    return timeout


def normalize_netlist(text):
    """Strip checkout paths from xschem path headers.

    Args:
        text: Raw netlist text with `** sch_path` / `** sym_path`
            headers carrying absolute checkout paths.

    Returns:
        Netlist text with those headers reduced to basenames,
            byte-comparable across checkouts.
    """
    return _SCH_PATH_RE.sub(r"\1\2", text)


def resolve_xschem(xschem_bin=None):
    """Path to a usable xschem binary, or None.

    Args:
        xschem_bin: Explicit binary path, or None for PATH.

    Returns:
        Binary path, or None when missing or not a file.
    """
    if xschem_bin is not None:
        return xschem_bin if Path(xschem_bin).is_file() else None
    return shutil.which("xschem")


def sharedir_for(binary):
    """Install sharedir next to the binary, or None when absent.

    Args:
        binary: Resolved xschem binary path.

    Returns:
        `<bindir>/../share/xschem` when it holds `xschem.tcl`,
            else None.
    """
    candidate = Path(binary).resolve().parent.parent / "share" / "xschem"
    if (candidate / "xschem.tcl").is_file():
        return str(candidate)
    return None


class XschemAdapter(ToolAdapter):
    """run_xschem via the xschem batch netlister.

    Serves the run_xschem operation with deck.tool `xschem` (the
    only tool). Netlists a schematic to SPICE with a pinned
    rcfile and explicit outputs; optional `-f` flat mode, `-S`
    schematic-owned sim, and `--command`/`--script` seams.

    Job keys:
        sch_file (required): Schematic file under netlist.
        rcfile: Project rcfile path (wrapped to pin
            XSCHEM_SHAREDIR; absent means the install default).
        output_name: Netlist file name (default
            `<stem>.spice`).
        flat: Flat netlist (`-f`) when true.
        sim: Run the schematic-owned sim (`-S`) when true.
        command: Extra `--command` Tcl snippet.
        script: Extra `--script` Tcl file path.
        workdir: Run directory (default ".").

    Args:
        runner: Optional isolated runner; direct subprocess when None.
        xschem_bin: Explicit xschem binary; PATH when None.

    Caution: xschem exits 0 on silent init failure and on
        netlist errors alike — the verdict always comes from the
        output file and the log, never the exit code.
    """

    def __init__(self, runner=None, xschem_bin=None):
        self._runner = runner
        self._xschem_bin = xschem_bin

    def capabilities(self, target):
        """Report the served operation, tool, and modes.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one schematic per job).

        Returns:
            Capability mapping with operations, tool, and modes.
        """
        return {
            "operations": [OPERATION],
            "tool": "xschem",
            "modes": ["netlist", "sim"],
        }

    def _assert_version(self, banner):
        """Reject non-V3 xschem banners loudly.

        Args:
            banner: Combined stdout/stderr of `xschem -v`.

        Raises:
            AdapterError: missing_dependency when the banner is
                not the V3 family this adapter is verified on.
        """
        if not _VERSION_RE.search(banner or ""):
            raise AdapterError(
                "missing_dependency",
                f"xschem V3 required, got banner: {(banner or '').strip()[:200]!r} "
                "(PROV: install xschem V3, see docs/tickets/PROV-DEFERRED.md).",
            )

    def preflight(self, job):
        """Check operation, files, binary, version, and sharedir.

        Cheap deterministic checks first (operation, files),
        machine-dependent ones last (binary, version, sharedir).

        Args:
            job: Solver job with operation run_xschem plus
                sch_file and deck inputs.

        Returns:
            Checked mapping with sch_file, binary, sharedir,
                output_name, flags, and timeout.

        Raises:
            AdapterError: unsupported_operation for another
                operation, invalid_reference for a missing
                schematic/rcfile/script, missing_dependency for
                a missing binary, a non-V3 banner, or an
                unresolvable sharedir.
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"xschem handles {OPERATION}, got {job.get('operation')}.",
            )
        timeout = _budget_or_raise(job)
        sch_file = job.get("sch_file")
        if not sch_file or not Path(sch_file).is_file():
            raise AdapterError(
                "invalid_reference", f"Schematic file not found: {sch_file}."
            )
        for key in ("rcfile", "script"):
            path = job.get(key)
            if path is not None and not Path(path).is_file():
                raise AdapterError(
                    "invalid_reference", f"xschem {key} not found: {path}."
                )
        binary = resolve_xschem(self._xschem_bin)
        if binary is None:
            raise AdapterError(
                "missing_dependency",
                "xschem binary not found "
                "(PROV: install xschem V3, see docs/tickets/PROV-DEFERRED.md).",
            )
        banner = self._version_banner(binary, timeout)
        self._assert_version(banner)
        sharedir = sharedir_for(binary)
        if sharedir is None:
            raise AdapterError(
                "missing_dependency",
                f"xschem sharedir unresolvable next to {binary} "
                "(expected <bindir>/../share/xschem/xschem.tcl).",
            )
        output_name = job.get("output_name") or (Path(sch_file).stem + ".spice")
        if not isinstance(output_name, str) or not output_name or "/" in output_name:
            raise AdapterError(
                "invalid_command", f"Bad xschem output_name: {output_name!r}."
            )
        return {
            "sch_file": sch_file,
            "rcfile": job.get("rcfile"),
            "script": job.get("script"),
            "command": job.get("command"),
            "binary": binary,
            "sharedir": sharedir,
            "output_name": output_name,
            "flat": bool(job.get("flat")),
            "sim": bool(job.get("sim")),
            "timeout_s": timeout,
        }

    def execute(self, job):
        """Wrap the rcfile, netlist, and read back the output.

        Args:
            job: Solver job with operation run_xschem plus
                sch_file and deck inputs.

        Returns:
            Native output with exit_code, stdout/stderr/log,
                netlist file/text (raw and normalized), and flags.

        Raises:
            AdapterError: invalid_reference for a missing
                workdir, invalid_command for a bad command
                snippet, missing_dependency on silent init
                failure, runner_unavailable when no netlist
                output appears, plus the preflight codes
                (execute re-checks first).
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        command = checked.get("command")
        if command is not None and not isinstance(command, str):
            raise AdapterError(
                "invalid_command", f"Bad xschem command: {command!r}."
            )
        outdir = Path(workdir) / "xschem_out"
        outdir.mkdir(exist_ok=True)
        wrapper = Path(workdir) / "xschem_wrapper.rc"
        lines = [f"set XSCHEM_SHAREDIR {{{checked['sharedir']}}}"]
        if checked.get("rcfile") is not None:
            lines.append(f"source {{{checked['rcfile']}}}")
            lines.append(f"set XSCHEM_SHAREDIR {{{checked['sharedir']}}}")
        wrapper.write_text("\n".join(lines) + "\n", encoding="utf-8")
        argv = [
            checked["binary"],
            "-x",
            "-q",
            "--rcfile",
            str(wrapper),
            "-s",
            "-n",
            checked["sch_file"],
            "-o",
            str(outdir),
            "-N",
            checked["output_name"],
        ]
        if checked["flat"]:
            argv.append("-f")
        if checked["sim"]:
            argv.append("-S")
        if command:
            argv.extend(["--command", command])
        if checked.get("script") is not None:
            argv.extend(["--script", checked["script"]])
        log_file = Path(workdir) / "xschem.log"
        proc = self._run(argv, workdir, timeout=checked["timeout_s"])
        log_file.write_text(
            (proc.stdout or "") + (proc.stderr or ""), encoding="utf-8"
        )
        log_text = log_file.read_text(encoding="utf-8")
        if _INIT_ERR_RE.search(log_text):
            raise AdapterError(
                "missing_dependency",
                "xschem init failed (xschem.tcl unloadable; sharedir "
                f"{checked['sharedir']!r}); see xschem.log "
                "(PROV: install xschem V3, see docs/tickets/PROV-DEFERRED.md).",
            )
        netlist_file = outdir / checked["output_name"]
        if not netlist_file.is_file():
            raise AdapterError(
                "runner_unavailable",
                f"xschem produced no netlist: {(proc.stderr or '')[:500]}.",
            )
        raw = netlist_file.read_text(encoding="utf-8")
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "log_file": str(log_file),
            "log_text": log_text,
            "netlist_file": str(netlist_file),
            "netlist_text": raw,
            "normalized_text": normalize_netlist(raw),
            "flat": checked["flat"],
            "sim": checked["sim"],
        }

    def parse(self, native_output):
        """Count netlist elements; sim mode surfaces sim failures.

        Args:
            native_output: Native output with the netlist text
                and log from execute.

        Returns:
            {total, violations[]} with element count and any
                xschem/sim failures as violations.

        Raises:
            AdapterError: runner_unavailable when the output has
                no netlist text.
        """
        raw = native_output.get("netlist_text")
        if raw is None:
            netlist_file = native_output.get("netlist_file")
            if not netlist_file or not Path(netlist_file).is_file():
                raise AdapterError(
                    "runner_unavailable", "xschem run has no netlist."
                )
            raw = Path(netlist_file).read_text(encoding="utf-8")
        elements = [
            line
            for line in raw.splitlines()
            if line.strip() and not line.strip().startswith("*")
        ]
        violations = []
        if native_output.get("sim"):
            log_text = native_output.get("log_text", "")
            for line in log_text.splitlines():
                if re.search(r"error|failed|no simulation", line, re.IGNORECASE):
                    violations.append(
                        {
                            "rule": "xschem_sim_fail",
                            "message": line.strip()[:300],
                            "severity": "error",
                        }
                    )
                    break
        return {"total": len(elements), "violations": violations}

    def _version_banner(self, binary, timeout):
        """Combined stdout/stderr of `xschem -v` for the V3 assert.

        Args:
            binary: Resolved xschem binary path.
            timeout: Budget seconds for the probe.

        Returns:
            Banner text (empty when the probe cannot run — the
                version assert then refuses).
        """
        try:
            proc = self._run([binary, "-v"], ".", timeout=timeout)
        except AdapterError:
            return ""
        return (proc.stdout or "") + (proc.stderr or "")

    def _run(self, argv, workdir, timeout=_TIMEOUT_S):
        """Run xschem with DISPLAY scrubbed (forced text mode).

        Args:
            argv: xschem argument vector.
            workdir: Run directory.
            timeout: Budget seconds for the run.

        Returns:
            Completed process with xschem stdout/stderr.

        Raises:
            AdapterError: runner_unavailable on timeout, plus
                converted runner errors when injected.
        """
        if self._runner is not None:
            try:
                return self._runner.run(argv, workdir, timeout)
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        import os

        env = dict(os.environ)
        env.pop("DISPLAY", None)
        try:
            return subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workdir,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "runner_unavailable", f"xschem timed out after {timeout}s."
            ) from exc
