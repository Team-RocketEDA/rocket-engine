"""KLayout DRC solver adapter (I14 + DRC-SKY130): batch DRC behind the port.

Two modes, verified against KLayout 0.28.16:
- Synthetic: render a pya check script from the rule table, run
  `klayout -b -r`, parse VIOL/TOTAL lines.
- Deck: run a foundry `.lydrc` (e.g. sky130A.lydrc) via
  `klayout -b -rd input=<gds> -rd report=<lyrdb> -r <deck>`,
  parse the report database XML into violations.
(The plain-Ruby DSL note in docs/probe-klayout-drc.md predates the
.lydrc batch recipe; XML-macro decks run fine under -r with -rd.)
KLayout exits 0 regardless, so the verdict always comes from parsed
output, never from the exit code.
"""

import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from ...execution.errors import ExecutionError
from ...interfaces import ToolAdapter
from ...interfaces.runparams import MAX_TIMEOUT_S, MIN_TIMEOUT_S
from ..errors import AdapterError

OPERATION = "run_drc"
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


def _load_layout(gds_file):
    """Read-only layout handle for cell inspection (no binary gate).

    Args:
        gds_file: GDSII file to open.

    Returns:
        Opened layout database object.

    Raises:
        AdapterError: runner_unavailable when no layout API is
            importable on this host.
    """
    try:
        import pya

        layout = pya.Layout()
    except ImportError:
        try:
            from klayout import db as klayout_db

            layout = klayout_db.Layout()
        except ImportError as exc:
            raise AdapterError(
                "runner_unavailable",
                "No KLayout layout API (pya/klayout.db) on this host.",
            ) from exc
    layout.read(gds_file)
    return layout


def _cell_inventory(gds_file):
    """Top-cell and all-cell names of a GDS file, read-only.

    Args:
        gds_file: GDSII file to inspect.

    Returns:
        (tops, all_names): sorted top-cell names and sorted
            every-cell names from one read-only load.
    """
    layout = _load_layout(gds_file)
    tops = sorted(cell.name for cell in layout.top_cells())
    all_names = sorted(cell.name for cell in layout.each_cell())
    return tops, all_names


def _resolve_cell_or_raise(gds_file, cell):
    """Honor the job cell against the GDS topology, or refuse loudly.

    Deck mode runs the foundry recipe over the whole GDS (the
    recipe has no top-cell selection) and the synthetic path
    checks `top_cell()` — so a job cell must name a top cell that
    exists, and a multi-top GDS needs an explicit cell instead of
    silently checking whatever `top_cell()` returns (MIXED-TOP
    F3). A missing cell refuses as invalid_reference; a present
    but non-top cell, or several tops without a cell, refuse as
    invalid_command.

    Args:
        gds_file: GDSII file under check.
        cell: Job cell name, or None.

    Returns:
        The honored top-cell name (the job cell, or the single
            top cell when the job names none).

    Raises:
        AdapterError: invalid_reference for a cell absent from
            the GDS; invalid_command for a non-top cell or for
            several top cells without a cell.
    """
    tops, all_names = _cell_inventory(gds_file)
    if cell is not None:
        if cell not in all_names:
            raise AdapterError(
                "invalid_reference", f"DRC cell not in GDS: {cell}."
            )
        if cell not in tops:
            raise AdapterError(
                "invalid_command",
                f"DRC cell {cell!r} is not a top cell "
                f"(tops: {', '.join(tops)}); deck mode checks the "
                "whole GDS and cannot scope to an inner cell.",
            )
        return cell
    if len(tops) != 1:
        raise AdapterError(
            "invalid_command",
            f"GDS has {len(tops)} top cells ({', '.join(tops)}); "
            "pass cell to select one.",
        )
    return tops[0]


_TOTAL_RE = re.compile(r"^TOTAL (\d+)$", re.M)
_VIOL_RE = re.compile(
    r"^VIOL rule=(\S+) bbox_um=([0-9.eE+-]+),([0-9.eE+-]+),"
    r"([0-9.eE+-]+),([0-9.eE+-]+)$",
    re.M,
)
_NUM_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

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


def _deck_file_or_raise(job):
    deck = job.get("deck") if isinstance(job.get("deck"), dict) else {}
    for candidate in (
        job.get("deck_file"),
        deck.get("path"),
        deck.get("deck_file"),
        deck.get("file"),
    ):
        if candidate is not None:
            if not candidate or not Path(candidate).is_file():
                raise AdapterError(
                    "invalid_reference", f"DRC deck not found: {candidate}."
                )
            return str(candidate)
    return None


def _bbox_from_value(text):
    nums = [float(v) for v in _NUM_RE.findall(text or "")]
    if len(nums) < 4 or len(nums) % 2:
        return None
    xs = nums[0::2]
    ys = nums[1::2]
    return [min(xs), min(ys), max(xs), max(ys)]


def _parse_lyrdb(xml_text):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise AdapterError(
            "runner_unavailable", f"klayout report is not valid XML: {exc}."
        ) from exc
    descriptions = {}
    for cat in root.findall("./categories/category"):
        name = (cat.findtext("name") or "").strip()
        desc = (cat.findtext("description") or "").strip()
        if name:
            descriptions[name] = desc or name
    violations = []
    total = 0
    for item in root.findall("./items/item"):
        raw_rule = (item.findtext("category") or "").strip().strip("'\"")
        rule = raw_rule or "unknown"
        try:
            mult = int((item.findtext("multiplicity") or "1").strip())
        except ValueError:
            mult = 1
        total += max(mult, 1)
        texts = [
            (v.text or "")
            for v in item.findall("./values/value")
            if (v.text or "").strip()
        ]
        joined = "; ".join(texts)
        violation = {
            "rule": rule,
            "message": descriptions.get(rule, rule),
        }
        if joined:
            violation["message"] = f"{violation['message']}: {joined}"
        bbox = _bbox_from_value(joined)
        if bbox is not None:
            violation["bbox_um"] = bbox
        violations.append(violation)
    return {"total": total, "violations": violations}


class KlayoutDrcAdapter(ToolAdapter):
    """run_drc via KLayout: synthetic checks or foundry .lydrc decks.

    Serves the run_drc operation with deck.tool `klayout`. Two
    modes: synthetic width/space checks over one layer from
    `rules`, or a foundry .lydrc deck over `gds_file` with
    violations parsed from the report database. Locations are
    metric bbox_um.

    Job keys:
        gds_file (required): GDS layout under check.
        rules: Synthetic check {layer [l, d], width_um, space_um,
            name?} — one check form is required (rules or a deck
            file).
        deck_file: Foundry .lydrc deck path (deck mode).
        deck: Optional mapping; deck.tool selects the solver
            (klayout here), deck.path/deck_file/file names the
            deck in deck mode.
        cell: Optional top-cell claim, honored in both modes:
            must name an existing top cell (multi-top GDS
            without a cell refuses loudly).
        workdir: Run directory (default ".").

    Args:
        runner: Optional isolated runner; direct subprocess when None.

    Caution: KLayout exits 0 regardless — the verdict always comes
        from parsed output, never the exit code.
    """

    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        """Report the served operation, tool, rules, and deck kinds.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one GDS per job).

        Returns:
            Capability mapping with operations, tool, rules, and
                decks.
        """
        return {
            "operations": [OPERATION],
            "tool": "klayout",
            "rules": ["width", "space"],
            "decks": ["lydrc"],
        }

    def preflight(self, job):
        """Check operation, klayout binary, GDS, and one check form.

        Args:
            job: Solver job with operation run_drc plus gds_file
                and rules or deck inputs.

        Returns:
            Checked mapping with gds_file plus deck_file (deck
                mode) or rules (synthetic mode).

        Raises:
            AdapterError: unsupported_operation for another
                operation, missing_dependency for a missing klayout
                binary, invalid_reference for a missing GDS or deck
                file, invalid_command for a malformed rules mapping.
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"KLayout DRC handles {OPERATION}, got {job.get('operation')}.",
            )
        timeout = _budget_or_raise(job)
        if shutil.which("klayout") is None:
            raise AdapterError("missing_dependency", "klayout binary not found.")
        gds_file = job.get("gds_file")
        if not gds_file or not Path(gds_file).is_file():
            raise AdapterError(
                "invalid_reference", f"GDS file not found: {gds_file}."
            )
        top = _resolve_cell_or_raise(gds_file, job.get("cell"))
        deck_file = _deck_file_or_raise(job)
        if deck_file is not None:
            checked = {
                "gds_file": gds_file,
                "deck_file": deck_file,
                "timeout_s": timeout,
            }
        else:
            checked = {
                "gds_file": gds_file,
                "rules": _rules_or_raise(job.get("rules")),
                "timeout_s": timeout,
            }
        if job.get("cell") is not None:
            checked["cell"] = top
        return checked

    def execute(self, job):
        """Run the deck batch or render and run the check script.

        Args:
            job: Solver job with operation run_drc plus gds_file
                and rules or deck inputs.

        Returns:
            Native output with exit_code, stdout/stderr, plus the
                report XML (deck mode) or rules (synthetic mode).

        Raises:
            AdapterError: invalid_reference for a missing workdir,
                runner_unavailable when klayout produces no report,
                plus the preflight codes (execute re-checks first).
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        if "deck_file" in checked:
            report_file = Path(workdir) / "drc_report.lyrdb"
            proc = self._run(
                [
                    "klayout",
                    "-b",
                    "-rd",
                    f"input={checked['gds_file']}",
                    "-rd",
                    f"report={report_file}",
                    "-r",
                    checked["deck_file"],
                ],
                workdir,
                timeout=checked["timeout_s"],
            )
            if not report_file.is_file():
                raise AdapterError(
                    "runner_unavailable",
                    f"klayout produced no report: {proc.stderr[:500]}.",
                )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "report_file": str(report_file),
                "report_xml": report_file.read_text(),
                "deck_file": checked["deck_file"],
                "gds_file": checked["gds_file"],
            }
        spec = json.dumps(
            {"gds_file": checked["gds_file"], "rules": checked["rules"]}
        )
        script = _CHECK_SCRIPT.replace("{spec!r}", repr(spec))
        script_file = Path(workdir) / "kl_drc_check.py"
        script_file.write_text(script)
        proc = self._run(
            ["klayout", "-b", "-r", str(script_file)],
            workdir,
            timeout=checked["timeout_s"],
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "rules": checked["rules"],
            "gds_file": checked["gds_file"],
        }

    def parse(self, native_output):
        """Parse the lyrdb report or the synthetic TOTAL/VIOL lines.

        Args:
            native_output: Native output with the report XML/file
                (deck mode) or klayout stdout (synthetic mode).

        Returns:
            {total, violations[]} with rule, message, and metric
                bbox_um where the deck reports geometry.

        Raises:
            AdapterError: runner_unavailable when the deck run has
                no report, the report is not valid XML, or the
                synthetic output has no TOTAL line.
        """
        if "report_xml" in native_output or "report_file" in native_output:
            xml_text = native_output.get("report_xml")
            if xml_text is None:
                report_file = native_output.get("report_file")
                if not report_file or not Path(report_file).is_file():
                    raise AdapterError(
                        "runner_unavailable", "klayout deck run has no report."
                    )
                xml_text = Path(report_file).read_text()
            return _parse_lyrdb(xml_text)
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

    def _run(self, argv, workdir, timeout=_TIMEOUT_S):
        if self._runner is not None:
            try:
                return self._runner.run(argv, workdir, timeout)
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        try:
            return subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workdir,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "runner_unavailable", f"klayout timed out after {timeout}s."
            ) from exc


OPERATION_ANTENNA = "run_antenna"


def _antenna_rules_or_raise(rules):
    """Antenna check rules: metal/gate layers plus the ratio cap.

    Args:
        rules: Mapping with metal_layer [l, d], gate_layer
            [l, d], and max_ratio > 0.

    Returns:
        Cleaned rules mapping with float max_ratio.

    Raises:
        AdapterError: invalid_command for a non-mapping, a
            malformed layer, or a non-positive ratio.
    """
    if not isinstance(rules, dict):
        raise AdapterError("invalid_command", "rules must be a mapping.")
    clean = {}
    for key in ("metal_layer", "gate_layer"):
        layer = rules.get(key)
        if (
            not isinstance(layer, (list, tuple))
            or len(layer) != 2
            or not all(isinstance(v, int) and not isinstance(v, bool) for v in layer)
        ):
            raise AdapterError("invalid_command", f"Bad antenna layer {key}: {layer!r}.")
        clean[key] = [layer[0], layer[1]]
    ratio = rules.get("max_ratio")
    if not isinstance(ratio, (int, float)) or isinstance(ratio, bool) or not ratio > 0:
        raise AdapterError("invalid_command", f"Bad antenna max_ratio: {ratio!r}.")
    clean["max_ratio"] = float(ratio)
    return clean


class AntennaKlayoutAdapter(ToolAdapter):
    """run_antenna via KLayout's layout database (ANTENNA-KLAYOUT).

    Serves the check.antenna surface without a foundry deck or an
    openroad-standalone path (demoted by ticket): per-metal-island
    cumulative metal-to-gate area ratio over the resolved cell,
    computed with the KLayout DB region API. An island with no
    gate overlap cannot discharge and fails as antenna_floating;
    an island over max_ratio fails as antenna_ratio with its
    metric bbox. Openroad-standalone is deliberately not staffed.

    Job keys:
        gds_file (required): GDS layout under check.
        rules (required): {metal_layer [l, d], gate_layer [l, d],
            max_ratio} with max_ratio > 0.
        cell: Optional top-cell claim, honored by scoping the
            island walk (defaults to the single top cell; a
            multi-top GDS without a cell refuses loudly).
        workdir: Run directory (default ".", unused — the check
            is in-process and writes no artifacts).

    Caution: a heuristic ratio check, not a signoff antenna
        rule; it names suspect islands for the foundry deck to
        confirm. Engine wiring (vocabulary/composition) belongs
        to the owning surface; this file staffs the solver only.
    """

    def capabilities(self, target):
        """Report the served operation, tool, and rule kind.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one GDS per job).

        Returns:
            Capability mapping with operations, tool, and rules.
        """
        return {
            "operations": [OPERATION_ANTENNA],
            "tool": "klayout",
            "rules": ["ratio"],
        }

    def preflight(self, job):
        """Check operation, GDS, cell scope, and ratio rules.

        Args:
            job: Solver job with operation run_antenna plus
                gds_file, rules, and an optional cell.

        Returns:
            Checked mapping with gds_file, rules, and cell.

        Raises:
            AdapterError: unsupported_operation for another
                operation, invalid_reference for a missing GDS
                or an unknown cell, invalid_command for a
                non-top cell, a multi-top GDS without a cell,
                or malformed rules.
        """
        if job.get("operation") != OPERATION_ANTENNA:
            raise AdapterError(
                "unsupported_operation",
                f"KLayout antenna handles {OPERATION_ANTENNA}, got {job.get('operation')}.",
            )
        timeout = _budget_or_raise(job)
        gds_file = job.get("gds_file")
        if not gds_file or not Path(gds_file).is_file():
            raise AdapterError(
                "invalid_reference", f"GDS file not found: {gds_file}."
            )
        cell = _resolve_cell_or_raise(gds_file, job.get("cell"))
        return {
            "gds_file": gds_file,
            "rules": _antenna_rules_or_raise(job.get("rules")),
            "cell": cell,
            "timeout_s": timeout,
        }

    def execute(self, job):
        """Walk metal islands over the cell and ratio them to gate.

        Args:
            job: Solver job with operation run_antenna plus
                gds_file, rules, and an optional cell.

        Returns:
            Native output with cell, gds_file, and violations
                carrying rule, ratio, and metric bbox_um.

        Raises:
            AdapterError: plus the preflight codes (execute
                re-checks first).
        """
        checked = self.preflight(job)
        layout = _load_layout(checked["gds_file"])
        dbu = layout.dbu
        top = layout.cell(checked["cell"])
        if top is None:
            raise AdapterError(
                "invalid_reference", f"DRC cell not in GDS: {checked['cell']}."
            )
        metal_layer = layout.layer(*checked["rules"]["metal_layer"])
        gate_layer = layout.layer(*checked["rules"]["gate_layer"])
        try:
            from pya import Region as _Region
        except ImportError:  # pragma: no cover - venv always ships pya here
            from klayout.db import Region as _Region
        gate = _Region(top.begin_shapes_rec(gate_layer))
        violations = []
        for island in _Region(top.begin_shapes_rec(metal_layer)).merged().each():
            island_region = _Region(island.to_simple_polygon())
            overlap = (island_region & gate).area()
            area = island_region.area()
            box = island.bbox()
            bbox_um = [box.left * dbu, box.bottom * dbu, box.right * dbu, box.top * dbu]
            if overlap <= 0:
                violations.append(
                    {
                        "rule": "antenna_floating",
                        "message": (
                            f"Metal island over cell {checked['cell']} has "
                            "no gate overlap"
                        ),
                        "ratio": None,
                        "bbox_um": bbox_um,
                    }
                )
            else:
                ratio = area / overlap
                if ratio > checked["rules"]["max_ratio"]:
                    violations.append(
                        {
                            "rule": "antenna_ratio",
                            "message": (
                                f"Metal-to-gate ratio {ratio:.1f} over "
                                f"{checked['rules']['max_ratio']:.1f}"
                            ),
                            "ratio": ratio,
                            "bbox_um": bbox_um,
                        }
                    )
        return {
            "cell": checked["cell"],
            "gds_file": checked["gds_file"],
            "violations": violations,
        }

    def parse(self, native_output):
        """Count the island violations carried by execute.

        Args:
            native_output: Native output with the violations
                list from execute.

        Returns:
            {total, violations[]} with rule, message, ratio,
                and metric bbox_um.

        Raises:
            AdapterError: runner_unavailable when the output
                carries no violations list.
        """
        violations = native_output.get("violations")
        if not isinstance(violations, list):
            raise AdapterError(
                "runner_unavailable", "antenna run has no violations."
            )
        return {"total": len(violations), "violations": violations}
