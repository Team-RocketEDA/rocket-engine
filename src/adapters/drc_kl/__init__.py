"""KLayout DRC solver adapter (I14): batch DRC behind the ToolAdapter port.

Protocol, verified against KLayout 0.28.16: render a pya check script
from the rule table, run `klayout -b -r`, parse VIOL/TOTAL lines. (The
Ruby DRC DSL does not run under -r; see docs/probe-klayout-drc.md.)
KLayout exits 0 regardless, so the verdict always comes from parsed
output, never from the exit code.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...interfaces import ToolAdapter
from ..errors import AdapterError

OPERATION = "run_drc"
_TIMEOUT_S = 120

_TOTAL_RE = re.compile(r"^TOTAL (\d+)$", re.M)
_VIOL_RE = re.compile(
    r"^VIOL rule=(\S+) bbox_um=([0-9.eE+-]+),([0-9.eE+-]+),"
    r"([0-9.eE+-]+),([0-9.eE+-]+)$",
    re.M,
)

_CHECK_SCRIPT = """import json
import pya

SPEC = json.loads({spec!r})
layout = pya.Layout()
layout.read(SPEC["gds_file"])
top = layout.top_cell()
layer = SPEC["rules"]["layer"]
region = pya.Region(top.begin_shapes_rec(layout.layer(layer[0], layer[1])))
total = 0
name = SPEC["rules"].get("name") or "L%d_%d" % (layer[0], layer[1])
checks = (("width", SPEC["rules"]["width_um"]), ("space", SPEC["rules"]["space_um"]))
for rule, dim_um in checks:
    dim_dbu = int(round(dim_um / layout.dbu))
    check = region.width_check if rule == "width" else region.space_check
    for pair in check(dim_dbu).each():
        total += 1
        box = pair.bbox()
        dbu = layout.dbu
        coords = (box.left * dbu, box.bottom * dbu, box.right * dbu, box.top * dbu)
        print("VIOL rule=%s_%s bbox_um=%s,%s,%s,%s" % ((name, rule) + coords))
print("TOTAL %d" % total)
"""


def _rules_or_raise(rules):
    if not isinstance(rules, dict):
        raise AdapterError("invalid_command", "rules must be a mapping.")
    layer = rules.get("layer")
    if (
        not isinstance(layer, (list, tuple))
        or len(layer) != 2
        or not all(isinstance(v, int) and not isinstance(v, bool) for v in layer)
    ):
        raise AdapterError("invalid_command", f"Bad DRC layer: {layer!r}.")
    clean = {"layer": [layer[0], layer[1]]}
    for key in ("width_um", "space_um"):
        value = rules.get(key)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not value > 0
        ):
            raise AdapterError("invalid_command", f"Bad DRC rule {key}: {value!r}.")
        clean[key] = float(value)
    if rules.get("name") is not None:
        clean["name"] = str(rules["name"])
    return clean


class KlayoutDrcAdapter(ToolAdapter):
    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        return {
            "operations": [OPERATION],
            "tool": "klayout",
            "rules": ["width", "space"],
        }

    def preflight(self, job):
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"KLayout DRC handles {OPERATION}, got {job.get('operation')}.",
            )
        if shutil.which("klayout") is None:
            raise AdapterError("missing_dependency", "klayout binary not found.")
        gds_file = job.get("gds_file")
        if not gds_file or not Path(gds_file).is_file():
            raise AdapterError(
                "invalid_reference", f"GDS file not found: {gds_file}."
            )
        return {"gds_file": gds_file, "rules": _rules_or_raise(job.get("rules"))}

    def execute(self, job):
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        spec = json.dumps(
            {"gds_file": checked["gds_file"], "rules": checked["rules"]}
        )
        script = _CHECK_SCRIPT.replace("{spec!r}", repr(spec))
        script_file = Path(workdir) / "kl_drc_check.py"
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        script_file.write_text(script)
        proc = self._run(["klayout", "-b", "-r", str(script_file)], workdir)
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "rules": checked["rules"],
            "gds_file": checked["gds_file"],
        }

    def parse(self, native_output):
        stdout = native_output.get("stdout", "")
        match = _TOTAL_RE.search(stdout)
        if match is None:
            raise AdapterError(
                "runner_unavailable", "klayout output has no TOTAL line."
            )
        violations = [
            {"rule": rule, "bbox_um": [float(c) for c in coords]}
            for rule, *coords in _VIOL_RE.findall(stdout)
        ]
        return {"total": int(match.group(1)), "violations": violations}

    def _run(self, argv, workdir):
        if self._runner is not None:
            try:
                return self._runner.run(argv, workdir, _TIMEOUT_S)
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        try:
            return subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_S,
                cwd=workdir,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "runner_unavailable", f"klayout timed out after {_TIMEOUT_S}s."
            ) from exc
