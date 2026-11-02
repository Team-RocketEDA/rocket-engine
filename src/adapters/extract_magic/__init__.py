"""Magic extraction solver adapter (EXTRACT-SKY130): .mag to .ext/.spice.

Protocol, verified against magic 8.3.685 + sky130A tech 1.0.588:
Tcl over stdin (`load`, `select top cell`, `extract all`,
`ext2spice lvs`, `ext2spice`), then the `<cell>.ext` + `<cell>.spice`
artifacts are read back from the workdir. The tech may be a store
deck path (`tech_file`, hash-checked via resolve_deck by the caller)
or a plain magic tech name. Magic exits 0 even for broken cells, so
the verdict always comes from parsed output, never the exit code.
"""

import re
import shutil
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...interfaces import ToolAdapter
from ...interfaces.runparams import MAX_TIMEOUT_S, MIN_TIMEOUT_S
from ..errors import AdapterError

OPERATION = "run_extraction"
_TIMEOUT_S = 120


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
_MARKER = "exttospice finished"
_SUBCKT_RE = re.compile(r"^\s*\.subckt\b", re.IGNORECASE | re.MULTILINE)
_DEVICE_RE = re.compile(
    r"^X(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)(.*)$",
    re.IGNORECASE,
)
_PARAM_RE = re.compile(r"\b([wl])=([0-9.eE+-]+)", re.IGNORECASE)
# The cell name is embedded in a Tcl script under braces: braces stop
# substitution, but `}` breaks out and backslash-newline still folds,
# so every Tcl-active character is rejected up front.
_CELL_BAD_RE = re.compile(r"[{}\[\]$\\;\"\n\r]")

_SCRIPT = (
    "load {cell}\nselect top cell\nextract all\n"
    "ext2spice lvs\next2spice\nquit\n"
)


def _tech_arg_or_raise(job):
    deck = job.get("deck") if isinstance(job.get("deck"), dict) else {}
    for candidate in (
        job.get("tech_file"),
        deck.get("path"),
        deck.get("tech_file"),
        deck.get("file"),
    ):
        if candidate is not None:
            if not candidate or not Path(candidate).is_file():
                raise AdapterError(
                    "invalid_reference", f"Magic tech file not found: {candidate}."
                )
            return str(candidate)
    tech = job.get("tech")
    if tech is None:
        raise AdapterError(
            "invalid_command", "Extraction needs a tech_file or tech name."
        )
    if not isinstance(tech, str) or not tech:
        raise AdapterError("invalid_command", f"Bad magic tech name: {tech!r}.")
    return tech


class MagicExtractAdapter(ToolAdapter):
    """run_extraction via Magic: .mag cells to .ext/.spice netlists.

    Serves the run_extraction operation with deck.tool `magic` (the
    only tool). Loads the cell, extracts all, and converts with
    ext2spice; the result carries the netlist artifact paths plus
    device counts.

    Job keys:
        cell (required): Cell name loaded and extracted.
        cell_file (required): Path to the .mag cell file.
        tech (required): Magic tech name — one tech form is
            required (tech, tech_file, or deck.path/tech_file/file).
        tech_file: Magic tech file path (a hash-checked store deck
            by the caller).
        deck: Optional mapping naming the tech file
            (deck.path/tech_file/file).
        workdir: Run directory (default ".").

    Args:
        runner: Optional isolated runner; direct subprocess when None.

    Caution: Magic exits 0 even for broken cells — the verdict
        always comes from parsed output, never the exit code.
    """

    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        """Report the served operation and tool name.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one cell per job).

        Returns:
            Capability mapping with operations and tool.
        """
        return {"operations": [OPERATION], "tool": "magic"}

    def preflight(self, job):
        """Check operation, cell, tech, binary, and cell file.

        Cheap deterministic checks first, machine-dependent ones
        last.

        Args:
            job: Solver job with operation run_extraction plus
                cell, cell_file, and tech inputs.

        Returns:
            Checked mapping with tech_arg, cell, and cell_file.

        Raises:
            AdapterError: unsupported_operation for another
                operation, invalid_command for a missing cell, a
                Tcl-unsafe cell name, or no tech form,
                missing_dependency for a missing magic binary or
                unloadable tech, invalid_reference for a missing
                cell or tech file.
        """
        # Cheap deterministic checks first (operation, cell, tech),
        # machine-dependent ones last (binary, tech probe).
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"Magic extraction handles {OPERATION}, got {job.get('operation')}.",
            )
        cell = job.get("cell")
        if not cell or not isinstance(cell, str):
            raise AdapterError("invalid_command", "Extraction needs a cell name.")
        timeout = _budget_or_raise(job)
        if _CELL_BAD_RE.search(cell):
            raise AdapterError(
                "invalid_command",
                f"Bad cell name (Tcl-unsafe characters): {cell!r}.",
            )
        tech_arg = _tech_arg_or_raise(job)
        if shutil.which("magic") is None:
            raise AdapterError("missing_dependency", "magic binary not found.")
        probe = self._run(
            tech_arg, "quit\n", job.get("workdir", "."), timeout=timeout
        )
        if Path(tech_arg).is_file():
            if 'Using technology "' not in probe.stdout:
                raise AdapterError(
                    "missing_dependency", f"Cannot load magic tech: {tech_arg}."
                )
        elif f'Using technology "{tech_arg}"' not in probe.stdout:
            raise AdapterError(
                "missing_dependency", f"Cannot load magic tech: {tech_arg}."
            )
        cell_file = job.get("cell_file")
        if not cell_file or not Path(cell_file).is_file():
            raise AdapterError(
                "invalid_reference", f"Cell file not found: {cell_file}."
            )
        return {
            "tech_arg": tech_arg,
            "cell": cell,
            "cell_file": cell_file,
            "timeout_s": timeout,
        }

    def execute(self, job):
        """Stage the cell, extract all, and convert with ext2spice.

        Args:
            job: Solver job with operation run_extraction plus
                cell, cell_file, and tech inputs.

        Returns:
            Native output with exit_code, stdout/stderr, tech,
                cell, and the .ext/.spice artifact paths and text.

        Raises:
            AdapterError: invalid_reference for a missing workdir,
                missing_dependency when the tech fails to load
                mid-run, runner_unavailable when the output has no
                ext2spice marker or no .ext/.spice pair, plus the
                preflight codes (execute re-checks first).
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        staged = Path(workdir) / Path(checked["cell_file"]).name
        if Path(checked["cell_file"]).resolve() != staged.resolve():
            shutil.copy(checked["cell_file"], staged)
        proc = self._run(
            checked["tech_arg"], _SCRIPT.format(cell=checked["cell"]), workdir,
            timeout=checked["timeout_s"],
        )
        if "Failed to load technology" in proc.stdout:
            raise AdapterError(
                "missing_dependency",
                f"Cannot load magic tech: {checked['tech_arg']}.",
            )
        if _MARKER not in proc.stdout:
            raise AdapterError(
                "runner_unavailable", "magic output has no ext2spice marker."
            )
        ext_file = Path(workdir) / f"{checked['cell']}.ext"
        spice_file = Path(workdir) / f"{checked['cell']}.spice"
        if not ext_file.is_file() or not spice_file.is_file():
            raise AdapterError(
                "runner_unavailable", "magic produced no .ext/.spice pair."
            )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "tech": checked["tech_arg"],
            "cell": checked["cell"],
            "ext_file": str(ext_file),
            "spice_file": str(spice_file),
            "spice_text": spice_file.read_text(encoding="utf-8"),
        }

    def parse(self, native_output):
        """Parse the ext2spice marker plus the device table.

        Args:
            native_output: Native output with magic stdout and the
                spice text or file.

        Returns:
            Result with cell, artifact paths, device_count,
                devices, and no violations.

        Raises:
            AdapterError: runner_unavailable when the output has no
                ext2spice marker, no spice text, or no subckt block.
        """
        stdout = native_output.get("stdout", "")
        if _MARKER not in stdout:
            raise AdapterError(
                "runner_unavailable", "magic output has no ext2spice marker."
            )
        spice_text = native_output.get("spice_text")
        if spice_text is None:
            spice_file = native_output.get("spice_file")
            if not spice_file or not Path(spice_file).is_file():
                raise AdapterError(
                    "runner_unavailable", "magic extraction has no spice text."
                )
            spice_text = Path(spice_file).read_text(encoding="utf-8")
        if _SUBCKT_RE.search(spice_text) is None:
            raise AdapterError(
                "runner_unavailable", "extracted spice has no subckt block."
            )
        devices = []
        for line in spice_text.splitlines():
            match = _DEVICE_RE.match(line.strip())
            if match is None:
                continue
            name, *nets, cls, params = match.groups()
            numbers = {
                key.lower(): float(value)
                for key, value in _PARAM_RE.findall(params)
            }
            devices.append(
                {
                    "name": f"X{name}",
                    "nets": nets,
                    "class": cls,
                    "w": numbers.get("w"),
                    "l": numbers.get("l"),
                }
            )
        return {
            "cell": native_output.get("cell"),
            "ext_file": native_output.get("ext_file"),
            "spice_file": native_output.get("spice_file"),
            "device_count": len(devices),
            "devices": devices,
            "violations": [],
        }

    def _run(self, tech, script, workdir, timeout=_TIMEOUT_S):
        argv = ["magic", "-dnull", "-noconsole", "-T", tech]
        if self._runner is not None:
            try:
                return self._runner.run(
                    argv, workdir, timeout, (), input_text=script
                )
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        try:
            return subprocess.run(
                argv,
                input=script,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workdir,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "runner_unavailable", f"magic timed out after {timeout}s."
            ) from exc
