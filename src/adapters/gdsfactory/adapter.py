"""Gdsfactory layout adapter: generate_views behind the ToolAdapter port.

Protocol, mirroring the SAX adapter: stage the views driver plus a job
JSON into the workdir, run `python gf_views_driver.py
gf_views_job.json` under a timeout, then parse the JSON envelope on
stdout. The verdict always comes from parsed output: an unknown cell,
an unreadable GDS, or an unsupported export format synthesizes an
error violation with file/line, and only a gdsfactory-less (or
PDK-less) interpreter raises missing_dependency.

Generalization law: project inputs in, identity mappings plus
diagnostics out. View specs (PDK, cells, params, export filenames),
project GDS files, and the macro pin map all ride the job — the MZI
smoke (`run_layout_smoke`) is the qualification fixture, and this op
generalizes it to any spec. GDS roundtrip readback is a diagnostic on
the export recipe, never the verdict. Macro pin/obstruction mappings
publish as workdir artifacts with provenance: a bound project pin_map
reconstructs them, otherwise the artifact carries the PRD boundary
note (import alone does not reconstruct them).

Tool resolution: an explicit job `tool_dir` containing a python
wins, else the engine interpreter (gdsfactory arrives via the pip
`layout` group). Where the tools live on disk is B10 scope.
"""

import json
import subprocess
import sys
from pathlib import Path

from ruamel.yaml import YAML

try:
    from ...execution.errors import ExecutionError
except ImportError:
    from rocket_engine.execution.errors import ExecutionError
try:
    from ...execution.runner import tool_roots
except ImportError:
    from rocket_engine.execution.runner import tool_roots
try:
    from ...interfaces import ToolAdapter
except ImportError:
    from rocket_engine.interfaces import ToolAdapter
try:
    from ..errors import AdapterError
except ImportError:
    from rocket_engine.adapters.errors import AdapterError

OPERATION = "generate_views"
RECIPES = {
    "import_gds": "Import project GDS files; map cells, publish pins.",
    "build_cells": "Build PDK cells from a project view spec.",
    "export_gds": "Build cells and stream GDS layouts to the workdir.",
    "export_oasis": "Build cells and stream OASIS layouts to the workdir.",
}
_PDKS = ("generic", "cspdk.si340")
_EXPORT_EXT = {"export_gds": ".gds", "export_oasis": ".oas"}
_RULES = {
    "invalid_cell": "views.unknown_cell",
    "unreadable_source": "views.unreadable_source",
    "unsupported_format": "views.unsupported_format",
}
_TIMEOUT_S = 120
_DRIVER_NAME = "gf_views_driver.py"
_JOB_NAME = "gf_views_job.json"


def _load_yaml(path, what):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise AdapterError(
            "invalid_reference", f"{what} unreadable: {path} ({exc})."
        ) from exc
    try:
        doc = YAML(typ="safe").load(text)
    except Exception as exc:
        mark = getattr(exc, "problem_mark", None) or getattr(
            exc, "context_mark", None
        )
        where = (
            f"{path}:{mark.line + 1}:{mark.column + 1}"
            if mark is not None
            else path
        )
        raise AdapterError(
            "invalid_reference", f"{what} is not YAML: {where} ({exc})."
        ) from exc
    return text, doc


def _check_view_doc(doc, spec):
    if not isinstance(doc, dict):
        raise AdapterError(
            "invalid_command", f"View spec is not a mapping: {spec}."
        )
    pdk = doc.get("pdk", "generic")
    if pdk not in _PDKS:
        raise AdapterError(
            "invalid_command",
            f"View spec pdk must be one of {', '.join(_PDKS)}, "
            f"got {pdk!r}: {spec}.",
        )
    cells = doc.get("cells")
    if not isinstance(cells, list) or not cells:
        raise AdapterError(
            "invalid_command", f"View spec needs a cells list: {spec}."
        )
    for entry in cells:
        if not isinstance(entry, dict) or not entry.get("cell"):
            raise AdapterError(
                "invalid_command",
                f"View spec cell entries need a cell name: {spec}.",
            )
        params = entry.get("params", {})
        if not isinstance(params, dict):
            raise AdapterError(
                "invalid_command",
                f"Cell {entry.get('cell')!r} params must be a "
                f"mapping: {spec}.",
            )
    exports = doc.get("exports", [])
    if not isinstance(exports, list):
        raise AdapterError(
            "invalid_command", f"View spec exports must be a list: {spec}."
        )
    for export in exports:
        if not isinstance(export, dict) or not export.get("filename"):
            raise AdapterError(
                "invalid_command",
                f"View spec exports need a filename: {spec}.",
            )


def _check_pin_map(doc, path):
    if not isinstance(doc, dict):
        raise AdapterError(
            "invalid_command", f"Pin map is not a mapping: {path}."
        )
    cells = doc.get("cells")
    if not isinstance(cells, dict) or not cells:
        raise AdapterError(
            "invalid_command", f"Pin map needs a cells mapping: {path}."
        )
    for cell, binding in cells.items():
        if not isinstance(binding, dict):
            raise AdapterError(
                "invalid_command",
                f"Pin map cell {cell!r} must be a mapping: {path}.",
            )
        pins = binding.get("pins", {})
        if not isinstance(pins, dict):
            raise AdapterError(
                "invalid_command",
                f"Pin map cell {cell!r} pins must be a mapping: {path}.",
            )
        for name, pin in pins.items():
            if not isinstance(pin, dict):
                raise AdapterError(
                    "invalid_command",
                    f"Pin map pin {name!r} must be a mapping: {path}.",
                )
        obstructions = binding.get("obstructions", [])
        if not isinstance(obstructions, list):
            raise AdapterError(
                "invalid_command",
                f"Pin map cell {cell!r} obstructions must be a "
                f"list: {path}.",
            )


def _check_number_list(pair, what, where):
    if (
        not isinstance(pair, list)
        or len(pair) != 2
        or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool)
            for v in pair
        )
    ):
        raise AdapterError(
            "runner_unavailable",
            f"Views driver result has a bad {what}: {where}.",
        )
    return [float(pair[0]), float(pair[1])]


class GdsfactoryViewsAdapter(ToolAdapter):
    """generate_views via gdsfactory: registered layout recipes.

    Serves the generate_views operation with deck.tool `gdsfactory`
    (the only tool). Stages the views driver plus a job JSON, runs
    it under a timeout, and parses the JSON envelope: identity
    mappings (requested source to built/imported component),
    diagnostics (versions, PDK, roundtrip readback), and workdir
    artifacts (layouts plus pin/obstruction mappings).

    Job keys:
        recipe (required): Registered recipe — import_gds,
            build_cells, export_gds, or export_oasis.
        sources (required): Project inputs — exactly one view-spec
            YAML for build/export recipes, one or more .gds files
            for import_gds.
        pin_map: Project macro pin-map YAML (import_gds only);
            binds pins/obstructions with provenance.
        cspdk_path: Vendored cspdk tree when the package is not
            installed.
        timeout_s: Layout budget in seconds (default 120).
        tool_dir: Directory holding the layout python; the engine
            interpreter otherwise.
        deck: Optional mapping; deck.tool must be gdsfactory here.
        workdir: Run directory (default ".").

    Args:
        runner: Optional isolated runner; direct subprocess when None.

    Caution: Unknown cells and unreadable GDS synthesize error
        violations with file/line — the verdict always comes from
        parsed output, never the exit code. GDS roundtrip readback
        is a diagnostic, never the verdict.
    """

    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        """Report the served operation, tool, and recipes.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one spec per job).

        Returns:
            Capability mapping with operations, tool, and recipes.
        """
        return {
            "operations": [OPERATION],
            "tool": "gdsfactory",
            "recipes": sorted(RECIPES),
        }

    def preflight(self, job):
        """Check operation, recipe, sources, spec shape, and python.

        Cheap deterministic checks first, tool resolution last, the
        runner probe closing it out.

        Args:
            job: Solver job with operation generate_views plus the
                recipe, project sources, and timeout inputs.

        Returns:
            Checked mapping with the resolved python, recipe, spec
                (spec/text/doc for build/export, gds_sources plus
                pin map for import), cspdk path, and timeout_s.

        Raises:
            AdapterError: unsupported_operation for another
                operation, invalid_command for a bad recipe,
                timeout, spec shape, pin map, or export filename,
                invalid_reference unless the recipe's project
                sources exist and parse, missing_dependency for an
                unresolvable layout python.
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"Views handles {OPERATION}, got {job.get('operation')}.",
            )
        recipe = job.get("recipe")
        if recipe not in RECIPES:
            raise AdapterError(
                "invalid_command",
                f"Unknown recipe {recipe!r}; want one of "
                f"{', '.join(sorted(RECIPES))}.",
            )
        timeout = job.get("timeout_s", _TIMEOUT_S)
        if (
            not isinstance(timeout, (int, float))
            or isinstance(timeout, bool)
            or not timeout > 0
        ):
            raise AdapterError("invalid_command", f"Bad timeout_s: {timeout!r}.")
        cspdk_path = job.get("cspdk_path")
        if cspdk_path is not None and not Path(cspdk_path).is_dir():
            raise AdapterError(
                "invalid_reference", f"cspdk_path not found: {cspdk_path}."
            )
        pin_map = job.get("pin_map")
        checked = {
            "python": self._resolve(job),
            "recipe": recipe,
            "cspdk_path": cspdk_path,
            "timeout_s": timeout,
        }
        sources = job.get("sources") or []
        if recipe == "import_gds":
            missing = [s for s in sources if not Path(s).is_file()]
            if not sources or missing:
                raise AdapterError(
                    "invalid_reference",
                    "import_gds needs project GDS files, got: "
                    f"{missing or sources}.",
                )
            for source in sources:
                if Path(source).suffix.lower() != ".gds":
                    raise AdapterError(
                        "invalid_command",
                        f"import_gds needs .gds sources: {source}.",
                    )
            checked["gds_sources"] = list(sources)
            checked["spec"] = ""
            checked["text"] = ""
            checked["doc"] = None
            if pin_map is None:
                checked["pin_map_path"] = None
                checked["pin_map_doc"] = None
            else:
                if not Path(pin_map).is_file():
                    raise AdapterError(
                        "invalid_reference",
                        f"Pin map not found: {pin_map}.",
                    )
                pin_text, pin_doc = _load_yaml(pin_map, "Pin map")
                _check_pin_map(pin_doc, pin_map)
                checked["pin_map_path"] = pin_map
                checked["pin_map_doc"] = pin_doc
                checked["pin_map_text"] = pin_text
        else:
            if pin_map is not None:
                raise AdapterError(
                    "invalid_command",
                    f"pin_map applies to import_gds, not {recipe}.",
                )
            missing = [s for s in sources if not Path(s).is_file()]
            if len(sources) != 1 or missing:
                raise AdapterError(
                    "invalid_reference",
                    "generate_views needs one view spec, got: "
                    f"{missing or sources}.",
                )
            spec = sources[0]
            text, doc = _load_yaml(spec, "View spec")
            _check_view_doc(doc, spec)
            if recipe in _EXPORT_EXT:
                want = _EXPORT_EXT[recipe]
                for export in doc.get("exports") or []:
                    if not str(export["filename"]).endswith(want):
                        raise AdapterError(
                            "invalid_command",
                            f"{recipe} needs {want} filenames: "
                            f"{export['filename']}.",
                        )
            checked["spec"] = spec
            checked["text"] = text
            checked["doc"] = doc
            checked["gds_sources"] = []
            checked["pin_map_path"] = None
            checked["pin_map_doc"] = None
        if self._runner is not None:
            try:
                self._runner.preflight()
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        return checked

    def execute(self, job):
        """Stage the driver plus job JSON, then run the recipe.

        Args:
            job: Solver job with operation generate_views plus the
                recipe, project sources, and timeout inputs.

        Returns:
            Native output with exit_code, stdout/stderr, recipe,
                spec, spec_text, and sources.

        Raises:
            AdapterError: invalid_reference for a missing workdir,
                runner_unavailable on a recipe timeout, plus the
                preflight codes (execute re-checks first).
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        workdir_path = Path(workdir)
        driver = Path(__file__).with_name("_driver.py").read_text(
            encoding="utf-8"
        )
        (workdir_path / _DRIVER_NAME).write_text(driver, encoding="utf-8")
        (workdir_path / _JOB_NAME).write_text(
            json.dumps(
                {
                    "recipe": checked["recipe"],
                    "spec": checked["spec"],
                    "text": checked["text"],
                    "doc": checked["doc"],
                    "gds_sources": checked["gds_sources"],
                    "pin_map_path": checked["pin_map_path"],
                    "pin_map_doc": checked["pin_map_doc"],
                    "cspdk_path": checked["cspdk_path"],
                }
            ),
            encoding="utf-8",
        )
        roots = tool_roots([checked["python"]])
        proc = self._run(
            [checked["python"], _DRIVER_NAME, _JOB_NAME],
            workdir,
            checked["timeout_s"],
            roots,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "recipe": checked["recipe"],
            "spec": checked["spec"],
            "spec_text": checked["text"],
            "sources": list(job.get("sources") or []),
        }

    def parse(self, native_output):
        """Parse the driver envelope into mappings and diagnostics.

        Unknown cells, unreadable GDS, and unsupported formats
        synthesize one error violation with file/line rather than
        parsing as clean; roundtrip readback stays a diagnostic.

        Args:
            native_output: Native output with the driver stdout
                envelope, recipe, spec, spec_text, and sources.

        Returns:
            {total, violations[], measurements[], mappings[],
                diagnostics{}, artifacts[],
                gdsfactory_version} with identity mappings, per-cell
                polygon/port/area measurements, and workdir
                artifact paths.

        Raises:
            AdapterError: missing_dependency when the layout python
                has no gdsfactory or PDK, runner_unavailable when
                the driver printed no JSON envelope or no result.
        """
        spec = native_output.get("spec") or ""
        if not spec:
            sources = native_output.get("sources") or []
            spec = sources[0] if sources else ""
        try:
            envelope = json.loads(native_output.get("stdout", ""))
        except (TypeError, ValueError):
            raise AdapterError(
                "runner_unavailable",
                "views driver printed no JSON envelope.",
            ) from None
        if not isinstance(envelope, dict) or not isinstance(
            envelope.get("ok"), bool
        ):
            raise AdapterError(
                "runner_unavailable",
                "views driver printed no JSON envelope.",
            )
        if not envelope["ok"]:
            error = envelope.get("error") or {}
            code = error.get("code")
            message = error.get("message", "views run failed")
            if code == "missing_dependency":
                raise AdapterError("missing_dependency", message)
            violation = {
                "rule": _RULES.get(code, "views.failed"),
                "severity": "error",
                "message": message,
                "file": spec,
            }
            if error.get("line") is not None:
                violation["line"] = error["line"]
            return {
                "total": 1,
                "violations": [violation],
                "measurements": [],
                "mappings": [],
                "diagnostics": {
                    "recipe": native_output.get("recipe", "")
                },
                "artifacts": [],
                "gdsfactory_version": envelope.get("gdsfactory_version"),
            }
        result = envelope.get("result") or {}
        mappings = result.get("mappings")
        artifacts = result.get("artifacts")
        diagnostics = result.get("diagnostics")
        if (
            not isinstance(mappings, list)
            or not mappings
            or not isinstance(artifacts, list)
            or not isinstance(diagnostics, dict)
        ):
            raise AdapterError(
                "runner_unavailable", "views driver envelope has no result."
            )
        measurements = []
        for mapping in mappings:
            if not isinstance(mapping, dict):
                raise AdapterError(
                    "runner_unavailable",
                    "views driver envelope has no result.",
                )
            try:
                cell = mapping["component"]
                ports = mapping["ports"]
                polygons = mapping["n_polygons"]
                bbox = mapping["bbox_um"]
            except KeyError:
                raise AdapterError(
                    "runner_unavailable",
                    "views driver envelope has no result.",
                ) from None
            if (
                not isinstance(cell, str)
                or not isinstance(ports, list)
                or not isinstance(polygons, int)
                or isinstance(polygons, bool)
                or not isinstance(bbox, list)
                or len(bbox) != 2
            ):
                raise AdapterError(
                    "runner_unavailable",
                    "views driver envelope has no result.",
                )
            lower = _check_number_list(bbox[0], "bbox", cell)
            upper = _check_number_list(bbox[1], "bbox", cell)
            area = (upper[0] - lower[0]) * (upper[1] - lower[1])
            measurements.append(
                {
                    "name": f"polygons({cell})",
                    "value": polygons,
                    "unit": "count",
                }
            )
            measurements.append(
                {
                    "name": f"ports({cell})",
                    "value": len(ports),
                    "unit": "count",
                }
            )
            measurements.append(
                {
                    "name": f"bbox_area_um2({cell})",
                    "value": area,
                    "unit": "um2",
                }
            )
        for artifact in artifacts:
            if (
                not isinstance(artifact, dict)
                or not isinstance(artifact.get("kind"), str)
                or not isinstance(artifact.get("path"), str)
            ):
                raise AdapterError(
                    "runner_unavailable",
                    "views driver envelope has no result.",
                )
        return {
            "total": 0,
            "violations": [],
            "measurements": measurements,
            "mappings": mappings,
            "diagnostics": {
                "recipe": result.get("recipe", ""),
                "active_pdk": result.get("active_pdk", ""),
                "cspdk_version": result.get("cspdk_version"),
                "roundtrip_match": diagnostics.get("roundtrip_match"),
                "notes": list(diagnostics.get("notes") or []),
            },
            "artifacts": artifacts,
            "gdsfactory_version": envelope.get("gdsfactory_version"),
        }

    @staticmethod
    def _resolve(job):
        tool_dir = job.get("tool_dir")
        if tool_dir:
            for name in ("python3", "python"):
                candidate = Path(tool_dir) / name
                if candidate.is_file():
                    return str(candidate)
            raise AdapterError(
                "missing_dependency", f"python not found in {tool_dir}."
            )
        return sys.executable

    def _run(self, argv, workdir, timeout_s, extra_binds=()):
        if self._runner is not None:
            try:
                return self._runner.run(argv, workdir, timeout_s, extra_binds)
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        try:
            return subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                cwd=workdir,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "runner_unavailable",
                f"views recipe timed out after {timeout_s}s.",
            ) from exc
