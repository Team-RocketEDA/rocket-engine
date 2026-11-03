# RUN-PARAMS lane report — explicit run.request schema

Ticket: `docs/tickets/RUN-PARAMS.md`. Branch `GREEN-the-tests`.
Nothing committed, nothing pushed (integrator commits).

## Outcome

New module `src/interfaces/runparams.py` implements the explicit
`run.request` schema (netlist type, flat/split shape, `lvs_netlist`,
`top_is_subckt`, deck opts passthrough): validated at submit, frozen
into the run snapshot, unknown fields rejected loudly, identical
shape for IDE/MCP/console callers. All wiring into existing files is
delivered below as an exact unified-diff patch (verified with
`git apply --check` and behaviorally on a `/tmp` stage copy).

## Files added (new files only — no existing file edited)

- `src/interfaces/runparams.py` — the schema module.
- `tests/interfaces/test_runparams.py` — unit tests (defaults,
  enum, bool strictness, unknown-field rejection, deck_opts shape,
  no-mutation, freeze replay-identical, parse round-trip, schema
  constant).
- `tests/interfaces/test_runparams_wiring.py` — integration tests
  the integrator runs AFTER applying the wiring patch (submit
  rejects/freeze, replay-identical through the ledger, run-path and
  MCP-path parity, dispatch shape). Pre-patch the 7 engine tests
  skip via a behavior probe; post-patch they run.
- `docs/work/RUN-PARAMS/report.md` — this file.

## Schema design

`arguments["request"]` is the single seam (verified: no existing
caller uses a `request` argument key). `validate_run_request`:

- `netlist_type`: `spice | spectre | verilog | vhdl`, default
  `spice` (mirrors xschem's `netlist_type` TCL var).
- `flat_netlist`, `lvs_netlist`, `top_is_subckt`: strict bools,
  default `False` (`1`/`"true"` are rejected — the CLI parses
  YAML scalars, so real bools arrive as bools).
- `deck_opts`: mapping with non-empty string keys and flat scalar
  values (`str/int/float/bool/None`), default `{}`. Nested
  mappings/lists are rejected — passthrough must not smuggle
  unvalidated shape into the tool call.
- Missing `request` (or `{}`) normalizes to all defaults, so the
  frozen snapshot shows every knob even for old callers. The
  caller's dict is never mutated.
- Error codes (stable, surfaced through Transports as
  `ProjectError` by the wiring): `unknown_run_param` (message
  names every unknown field plus all known fields),
  `invalid_run_param` (names the field; `netlist_type` also lists
  the allowed values), `invalid_run_request` (non-mapping
  `request`, bad frozen text).

`freeze_run_request` renders canonical `inputs.yaml` text (schema
field order, `deck_opts` sorted): same logical request replays
byte-identically whatever key order the caller sent.
`parse_run_request` reads it back through the same validator.
`RUN_REQUEST_SCHEMA` is the machine seam for api-spec regen
(fully AST-literal — `api_spec.py` parses without importing;
tests pin `enum == list(NETLIST_TYPES)` against drift).

## RED → GREEN evidence

Test runner note: `.venv` holds a non-editable `rocket_engine`
install, so live-tree runs use a `/tmp` shim:
`ln -s <repo>/src /tmp/rpshim/rocket_engine` +
`PYTHONPATH=/tmp/rpshim`. No repo files involved; no `uv sync`.

RED (tests written first, module absent):

    $ PYTHONPATH=/tmp/rpshim .venv/bin/python -m pytest \
        tests/interfaces/test_runparams.py \
        tests/interfaces/test_runparams_wiring.py -q
    ERROR tests/interfaces/test_runparams.py
    ERROR tests/interfaces/test_runparams_wiring.py
    ModuleNotFoundError: No module named
        'rocket_engine.interfaces.runparams'
    2 errors in 0.12s

GREEN (module added, no existing file touched):

    $ PYTHONPATH=/tmp/rpshim .venv/bin/python -m pytest \
        tests/interfaces/test_runparams.py \
        tests/interfaces/test_runparams_wiring.py -q
    43 passed, 7 skipped in 0.08s

The 7 skips are the post-patch wiring tests (probe: submit with
an unknown field must raise `unknown_run_param`; pre-patch the
tree raises `revision_conflict`, so they skip).

Post-patch proof on a `/tmp` stage copy (repo untouched; stage =
repo files + the exact patch below, applied by unique-string
replacement, then also verified via `git apply --check`):

    $ PYTHONPATH=/tmp/rpstage .venv/bin/python -m pytest \
        tests/interfaces/test_runparams.py \
        tests/interfaces/test_runparams_wiring.py -q
    50 passed in 0.08s

api_spec injection verified on stage (`build_schemas(root=stage)`
+ `section_body('run_drc')`): every solver-op schema gains the
full `request` subschema (5 properties, enum, defaults,
`additionalProperties: False`) and the reference mentions
`` `request` ``.

## Test commands + results

| Command (from `rocket-engine/`, `.venv/bin/python`) | Result |
|---|---|
| `PYTHONPATH=/tmp/rpshim python -m pytest tests/interfaces/test_runparams.py tests/interfaces/test_runparams_wiring.py -q` | 43 passed, 7 skipped (skips = pre-patch wiring) |
| Same on `/tmp/rpstage` (patched copy) | 50 passed |
| Neighbors: `... test_setup.py test_dispatch.py test_api_spec.py` + both new files | 79 passed, 7 skipped |
| `python scripts/check_docstrings.py` (full tree) | clean |
| `python scripts/check_docstrings.py src/interfaces/runparams.py` | clean |
| `git apply --check /tmp/runparams.patch` | clean |

Full suite never run (lane rule). No `tests/pdk_*/` or
`docs/pdk/*/` touched. `git log --oneline -3` at start:
`95f39fa / 20239f3 / c83ec9e`; at finish the head is `f68fd69`
(concurrent lane commit — not mine; I committed nothing).

## Integrator instructions

1. Apply the patch: `git apply docs/work/RUN-PARAMS/report.md`?
   No — the patch is the fenced block below; save it to a file
   and `git apply --check` then `git apply` it.
2. Regen the contract artifacts (freshness-pinned):
   `python scripts/api_spec.py --write` then
   `python scripts/contract.py --write`.
3. Run: `python -m pytest tests/interfaces/test_runparams.py
   tests/interfaces/test_runparams_wiring.py -q` — expect
   50 passed, 0 skipped — plus the gate suite.

## Wiring patch (exact — `git apply` this block)

Covers `src/composition.py` (validate + freeze in `submit` and
`run`, the choke points all three caller families traverse),
`src/interfaces/__init__.py` (surface export), and
`scripts/api_spec.py` (`request` injection into solver-op schemas
and reference sections, mirroring `expected_revision`).
Generated docs (`engine-api.md`, `api-schema.json`,
`api-help.json`, `contract.json`) are NOT in the patch — the
integrator regenerates them per step 2.

```diff
--- a/src/composition.py
+++ b/src/composition.py
@@ -44,6 +44,7 @@
 from .adapters.syntax import SyntaxAdapter
 from .execution.errors import ExecutionError
 from .execution.service import ExecutionService
+from .interfaces.runparams import RunParamsError, validate_run_request
 from .interfaces.setup import report_capabilities
 from .interfaces.vocabulary import OPERATIONS, QUERIES
 from .library.catalog import Catalog
@@ -263,8 +264,12 @@
         Raises:
             ProjectError: cross_project_denied for a foreign
                 envelope, unsupported_operation for an unwired or
-                unknown name, invalid_command for caller-supplied
-                run_spice targets, revision_conflict for a stale
+                unknown name, unknown_run_param for an unknown
+                run.request field, invalid_run_param for a
+                mistyped run.request knob, invalid_run_request
+                for a non-mapping run.request, invalid_command
+                for caller-supplied run_spice targets,
+                revision_conflict for a stale
                 expected_revision, invalid_command for a malformed
                 get_events_since cursor, a malformed mutation, or
                 a rewind that lacks a target or targets the live
@@ -290,6 +295,7 @@
         name = command.get("operation")
         arguments = dict(command.get("arguments") or {})
         arguments = self._apply_targets(name, arguments)
+        arguments = self._apply_run_request(arguments)
         if name == "get_capabilities":
             return self.capabilities(
@@ -514,6 +520,33 @@
             updated["analyses"] = list(arguments.get("analyses") or []) + control
         return updated

+    def _apply_run_request(self, arguments):
+        """Validate and freeze the explicit run.request knobs (RUN-PARAMS).
+
+        Every submit carries its knobs explicitly: a missing
+        `request` freezes to all defaults, a partial one fills
+        defaults, and unknown fields fail loudly — never
+        ignored. All callers (IDE, MCP, console) share this one
+        path, so the shape is identical whoever submits.
+
+        Args:
+            arguments: Submitted arguments, maybe with `request`.
+
+        Returns:
+            Arguments with `request` normalized to every knob.
+
+        Raises:
+            ProjectError: unknown_run_param for an unknown
+                field, invalid_run_param for a mistyped knob,
+                invalid_run_request for a non-mapping
+                `request`.
+        """
+        try:
+            normalized = validate_run_request(arguments.get("request"))
+        except RunParamsError as exc:
+            raise ProjectError(exc.code, str(exc), fields=exc.fields) from exc
+        return {**arguments, "request": normalized}
+
     def job_status(self, run_id=None):
         """Read one run's state, verdict, and evidence links.

@@ -897,7 +930,10 @@
         Raises:
             ProjectError: cross_project_denied for a foreign
                 envelope, unsupported_operation for an unregistered
-                operation or unknown deck tool, invalid_command
+                operation or unknown deck tool, unknown_run_param
+                for an unknown run.request field, invalid_run_param
+                for a mistyped run.request knob, invalid_run_request
+                for a non-mapping run.request, invalid_command
                 when run_job lacks a run_id/request_id argument,
                 for caller-supplied run_spice targets, when a CRUD
                 mutation is malformed, or a rewind lacks a target
@@ -923,6 +959,7 @@
         if name in _CRUD_OPERATIONS:
             return self.submit(command)
         arguments = self._apply_targets(name, dict(command.get("arguments") or {}))
+        arguments = self._apply_run_request(arguments)
         return self._run_operation(
             name,
             arguments,
--- a/src/interfaces/__init__.py
+++ b/src/interfaces/__init__.py
@@ -5,11 +5,29 @@
 from .errors import ContractError
 from .ports import ToolAdapter
 from .references import check_connection, resolve_reference
+from .runparams import (
+    NETLIST_TYPES,
+    RUN_REQUEST_DEFAULTS,
+    RUN_REQUEST_FIELDS,
+    RUN_REQUEST_SCHEMA,
+    RunParamsError,
+    freeze_run_request,
+    parse_run_request,
+    validate_run_request,
+)

 __all__ = [
+    "NETLIST_TYPES",
+    "RUN_REQUEST_DEFAULTS",
+    "RUN_REQUEST_FIELDS",
+    "RUN_REQUEST_SCHEMA",
     "ContractError",
+    "RunParamsError",
     "ToolAdapter",
     "check_connection",
+    "freeze_run_request",
+    "parse_run_request",
     "resolve_reference",
     "validate_document",
+    "validate_run_request",
 ]
--- a/scripts/api_spec.py
+++ b/scripts/api_spec.py
@@ -26,7 +26,8 @@
 `name:` or `name (required):` items; envelope plumbing
 (request_id/command_text) is excluded from CRUD/query schemas;
 expected_revision is injected into solver-op schemas from
-ProjectService.submit's own arg text.
+ProjectService.submit's own arg text; `request` is injected
+from interfaces/runparams.py RUN_REQUEST_SCHEMA.

 Usage: python scripts/api_spec.py [--write|--check] (default --check).
 """
@@ -341,6 +342,18 @@
     return "Revision the writer read."


+def _run_request_schema(root):
+    """RUN-PARAMS `request` subschema from RUN_REQUEST_SCHEMA (AST-only)."""
+    tree = ast.parse(
+        (root / "interfaces" / "runparams.py").read_text(encoding="utf-8")
+    )
+    node = _module_assign(tree, "RUN_REQUEST_SCHEMA")
+    try:
+        return ast.literal_eval(node) if node is not None else {}
+    except (ValueError, SyntaxError):
+        return {}
+
+
 def endpoint_spec(name, root=None):
     """Contract record for one cataloged operation/query name."""
     root = root if root is not None else SRC
@@ -485,6 +498,9 @@
         f"Handlers: {handlers}.",
     ]
     revision_text = _expected_revision_text(root)
+    request_text = _run_request_schema(root).get(
+        "description", "Explicit run.request knobs."
+    )
     for tool, cls, rel in entries:
         parsed = parse_docstring(doc_of(rel, cls, root=root))
         preflight = parse_docstring(doc_of(
@@ -495,7 +511,8 @@
         ))
         parse = parse_docstring(doc_of(rel, f"{cls}.parse", root=root))
         args = list(parsed["job_keys"]) + [
-            ("expected_revision", False, revision_text)
+            ("expected_revision", False, revision_text),
+            ("request", False, request_text),
         ]
         raises = "\n\n".join(
             t for t in (
@@ -601,6 +618,9 @@
                 n: {"description": d} for n, _r, d in parsed["job_keys"]
             }
             props["expected_revision"] = {"description": revision_text}
+            request_schema = _run_request_schema(root)
+            if request_schema:
+                props["request"] = request_schema
             tools[tool] = {
                 "adapter": _handler_ref(rel, cls),
                 "properties": props,
```

## Refused / deliberately not changed (with reasons)

- `src/adapters/mcp/server.py`: no change needed. MCP routes
  through `engine.submit`, and `make_handlers` already catches
  `ProjectError` (via `_ENGINE_ERRORS`) into error results — the
  new `unknown_run_param` / `invalid_run_param` /
  `invalid_run_request` codes surface without transport edits.
  Covered by `test_mcp_shape_validates_identically_to_submit`.
- `src/interfaces/vocabulary.py`: no change needed. The schema
  rides inside `arguments["request"]`; no new operation or query
  is introduced.
- `scripts/contract.py`: no code change needed. It probes live
  ack/completion/event envelope shapes, which the patch does not
  alter (it only normalizes stored arguments); regen picks up the
  new api-schema and re-pins the hash.
- MCP evidence records (`results/engine-runs/*.json`): not
  extended. The ticket freezes knobs into the run snapshot (the
  ledger command, readable via `command_for`); evidence records
  carry verdicts, not inputs. `freeze_run_request` is the
  canonical-bytes seam if evidence ever needs inputs.
- Bare filenames (`runparams.py`, `test_runparams*.py`) instead
  of ticket-prefixed ones: the ticket names `runparams.py`, and
  no other lane uses these paths (verified in `git status`). If
  the integrator hits a collision, rename is mechanical.
- No `inputs.yaml` file sink was added: the tree has no such
  sink (only the ticket names it). The freeze point is the
  stored submit command (the snapshot); `freeze_run_request`
  provides deterministic `inputs.yaml` bytes for any future
  file sink or export.
