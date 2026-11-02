"""Magic DRC solver adapter (I14): batch DRC behind the ToolAdapter port.

Protocol, verified against magic 8.3.685 + scmos tech 8.2.8: Tcl over
stdin, `drc check` + `drc catchup` under an explicit box (`check`
rechecks the box area; `count` needs the catchup), `drc count total`
for the verdict, then `drc find N` + box readout per error area until
"There aren't that many errors". Magic exits 0 even for unknown techs
and broken cells, so the verdict always comes from parsed output,
never from the exit code.
"""

import re
import shutil
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...interfaces import ToolAdapter
from ...interfaces.runparams import MAX_TIMEOUT_S, MIN_TIMEOUT_S
from ..errors import AdapterError

OPERATION = "run_drc"
_TIMEOUT_S = 120
_BOX_MARGIN = 5
_DEFAULT_BOX = (-5, -5, 15, 10)

_TOTAL_RE = re.compile(r"Total DRC errors found: (\d+)")
_AREA_RE = re.compile(r"Error area #(\d+):\n([^\n]+)\n(-?\d+) (-?\d+) (-?\d+) (-?\d+)")


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


def _box_for(cell_file):
    x0 = y0 = x1 = y1 = None
    for line in Path(cell_file).read_text().splitlines():
        parts = line.split()
        if len(parts) == 5 and parts[0] == "rect":
            try:
                coords = tuple(int(v) for v in parts[1:])
            except ValueError:
                continue
            if x0 is None:
                x0, y0, x1, y1 = coords
            else:
                x0 = min(x0, coords[0])
                y0 = min(y0, coords[1])
                x1 = max(x1, coords[2])
                y1 = max(y1, coords[3])
    if x0 is None:
        return _DEFAULT_BOX
    m = _BOX_MARGIN
    return (x0 - m, y0 - m, x1 + m, y1 + m)


class MagicDrcAdapter(ToolAdapter):
    """run_drc via Magic: batch DRC over .mag cells, lambda-unit boxes.

    Serves the run_drc operation with deck.tool `magic` (the
    operation default). Tcl over stdin against a loaded cell; the
    result is {total, violations[]} with rule/message plus
    lambda-unit bbox areas.

    Job keys:
        cell (required): Cell name loaded inside magic.
        cell_file (required): Path to the .mag cell file.
        tech: Magic tech name (default scmos).
        deck: Optional mapping; deck.tool selects the solver
            (magic here, klayout for the KLayout path).
        workdir: Run directory (default ".").
        timeout_s: Sim budget in seconds (default 120).

    Args:
        runner: Optional isolated runner; direct subprocess when None.

    Caution: Magic exits 0 even for broken cells and unknown techs —
        the verdict always comes from parsed output, never the exit
        code. Timeout rides the job budget.
    """

    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        """Report the served operation, tech, and tool name.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one tech per job).

        Returns:
            Capability mapping with operations, tech, and tool.
        """
        return {"operations": [OPERATION], "tech": "scmos", "tool": "magic"}

    def preflight(self, job):
        """Check operation, magic binary, tech probe, and cell file.

        Args:
            job: Solver job with operation run_drc plus cell,
                cell_file, and tech inputs.

        Returns:
            Checked mapping with tech, cell, and cell_file.

        Raises:
            AdapterError: unsupported_operation for another
                operation, missing_dependency for a missing magic
                binary or unloadable tech, invalid_reference for a
                missing cell file.
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"Magic DRC handles {OPERATION}, got {job.get('operation')}.",
            )
        timeout = _budget_or_raise(job)
        if shutil.which("magic") is None:
            raise AdapterError("missing_dependency", "magic binary not found.")
        tech = job.get("tech", "scmos")
        probe = self._run(
            tech, "quit\n", job.get("workdir", "."), timeout=timeout
        )
        if f'Using technology "{tech}"' not in probe.stdout:
            raise AdapterError(
                "missing_dependency", f"Cannot load magic tech: {tech}."
            )
        cell_file = job.get("cell_file")
        if not cell_file or not Path(cell_file).is_file():
            raise AdapterError(
                "invalid_reference", f"Cell file not found: {cell_file}."
            )
        return {
            "tech": tech,
            "cell": job.get("cell"),
            "cell_file": cell_file,
            "timeout_s": timeout,
        }

    def execute(self, job):
        """Run magic DRC: a count pass, then per-area detail.

        Args:
            job: Solver job with operation run_drc plus cell,
                cell_file, and tech inputs.

        Returns:
            Native output with exit_code, combined stdout/stderr,
                tech, and cell.

        Raises:
            AdapterError: missing_dependency when the tech fails
                to load mid-run, runner_unavailable when magic
                output carries no DRC total line, plus the
                preflight codes (execute re-checks first).
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        box = _box_for(checked["cell_file"])
        count_script = (
            "load {cell}\nbox values {x0} {y0} {x1} {y1}\n"
            "drc check\ndrc catchup\ndrc count total\nquit\n"
        ).format(cell=checked["cell"], x0=box[0], y0=box[1], x1=box[2], y1=box[3])
        first = self._run(
            checked["tech"], count_script, workdir,
            timeout=checked["timeout_s"],
        )
        if "Failed to load technology" in first.stdout:
            raise AdapterError(
                "missing_dependency", f"Cannot load magic tech: {checked['tech']}."
            )
        match = _TOTAL_RE.search(first.stdout)
        if match is None:
            raise AdapterError(
                "runner_unavailable", "magic output has no DRC total line."
            )
        total = int(match.group(1))
        # Error areas never outnumber error tiles, so total+1 finds always
        # reach the "aren't that many" terminator.
        finds = "".join(
            f"drc find {n}\nputs [box values]\ndrc why\n"
            for n in range(1, total + 2)
        )
        detail_script = (
            "load {cell}\nbox values {x0} {y0} {x1} {y1}\n"
            "drc check\ndrc catchup\n{finds}quit\n"
        ).format(
            cell=checked["cell"],
            x0=box[0],
            y0=box[1],
            x1=box[2],
            y1=box[3],
            finds=finds,
        )
        if total:
            second = self._run(
                checked["tech"], detail_script, workdir,
                timeout=checked["timeout_s"],
            )
        else:
            second = None
        return {
            "exit_code": first.returncode,
            "stdout": first.stdout + (second.stdout if second else ""),
            "stderr": first.stderr + (second.stderr if second else ""),
            "tech": checked["tech"],
            "cell": checked["cell"],
        }

    def parse(self, native_output):
        """Parse the DRC total plus per-area rule boxes.

        Args:
            native_output: Native output with magic stdout.

        Returns:
            {total, violations[]} with rule plus lambda-unit
                bbox areas.

        Raises:
            AdapterError: runner_unavailable when the output has no
                DRC total line.
        """
        stdout = native_output.get("stdout", "")
        match = _TOTAL_RE.search(stdout)
        if match is None:
            raise AdapterError(
                "runner_unavailable", "magic output has no DRC total line."
            )
        violations = [
            {
                "area": int(area),
                "rule": rule,
                "bbox": [int(x0), int(y0), int(x1), int(y1)],
            }
            for area, rule, x0, y0, x1, y1 in _AREA_RE.findall(stdout)
        ]
        return {"total": int(match.group(1)), "violations": violations}

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
