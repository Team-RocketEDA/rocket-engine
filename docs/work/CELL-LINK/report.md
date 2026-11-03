# CELL-LINK lane report — Symbol↔cell linkage contract

Ticket: `docs/tickets/CELL-LINK.md` · Branch: GREEN-the-tests · No commits, no pushes (integrator commits).

## Files added (new files only — zero edits to existing files)

- `src/interfaces/celllink.py` — CellLink component: schema validation, `resolve_pin` /
  `resolve_cell` / `resolve_link` chokepoints, KiCad filter matching, ERC collection,
  `resolve_run` run/export resolution. Stdlib + `.errors` only (leaf module, no new deps).
- `tests/interfaces/test_celllink.py` — 40 unit tests: schema/edit-freedom, explicit /
  identity / variant-overridden pins, REFERENCE, ordering, filter semantics, ERC.
- `tests/interfaces/test_celllink_run.py` — 5 run/export tests incl. the sky130A
  link → resolve → run round-trip, emit-only-non-empty, unknown-cell run error.
- `tests/interfaces/test_celllink_wiring.py` — 2 post-patch integration tests the
  integrator runs AFTER applying the wiring patch below (skip until then).
- `docs/work/CELL-LINK/report.md` — this file.

## Contract implemented (ticket clause → behavior)

- `cell: "pdklib:cell"` opaque string, no write-time existence check —
  `validate_celllink` accepts any string incl. unknown cells and `""` (unlinked).
- `pinMap: [{symPin, cellPin}]` ordered explicit, identity default for unlisted pins,
  single-target only — duplicate `symPin` rejected (`invalid_celllink`); order preserved.
- `cellFilters: [glob…]`, KiCad chooser semantics — `match_cell_filters`: OR across
  entries, empty matches all, case-insensitive anchored `*`/`?` full-match, `:` splits
  lib from cell (lib-less pattern matches the cell part only), space sanitized to `_`.
- `variantOverrides: {name: {cell?, pinEdits?}}` sparse differentials, one default
  variant, REFERENCE immutable — stored link is the default (`variant=None`); `REFERENCE`
  reserved: selecting it always resolves the base, using it as an override key is
  rejected. Resolution copies — storage is never mutated (tested).
- `resolvePin(block, variant) -> cellPin` chokepoint — `resolve_pin(block, sym_pin,
  variant=None)`; `resolve_cell` / `resolve_link` share the same selector semantics.
- Run/export resolves `(cell, pinMap, variant)` per block, emits only when non-empty —
  `resolve_run` skips unlinked/empty-cell blocks, echoes variant verbatim.
- Unknown/missing cell is a run error, never an edit error — `CellLinkError`
  (`unknown_cell`, names block id + cell) from `resolve_run`; `validate_celllink`
  accepts the same text.
- Filters stored on the link, advisory in picker only; ERC collects `{cell, filters}`
  for checks only — `collect_erc` never enforces.

Error codes: `invalid_celllink`, `unknown_variant`, `invalid_block` (`ContractError`);
`unknown_cell` (`CellLinkError`, same `(code, message, fields)` shape as the other
engine error types; kept in `interfaces` so the leaf module never imports `execution`).

## RED → GREEN evidence

Toolchain: `/tmp/celllink-venv` (scratch, pytest + ruamel only) with a
`site-packages/rocket_engine -> src` symlink. Repo `.venv` untouched, no `uv sync`.

RED (tests written before the module):

    /tmp/celllink-venv/bin/python -m pytest tests/interfaces/test_celllink.py \
      tests/interfaces/test_celllink_run.py tests/interfaces/test_celllink_wiring.py -q
    # 45 failed, 2 skipped — every failure is
    # ImportError: cannot import name 'celllink' from 'rocket_engine.interfaces'

GREEN (after adding `src/interfaces/celllink.py` + two fixes — a `clean["filters"]`
KeyError in `collect_erc`, and a test over-asserting the verbatim variant echo):

    # same command
    # 45 passed, 2 skipped in 0.06s (skips = wiring tests awaiting the patch)

Named neighbors (never the full suite):

    /tmp/celllink-venv/bin/python -m pytest tests/interfaces/test_references.py \
      tests/test_docstrings.py tests/test_no_cloud.py -q
    # 10 passed
    /tmp/celllink-venv/bin/python scripts/check_docstrings.py src/interfaces/celllink.py
    # clean (exit 0)

Style: no line over 100 chars in new/patched files (repo ruff limit).

## Wiring patch for the integrator (exact unified diff)

Verified: `patch -p1 --dry-run` applies cleanly to pristine copies, both files
`py_compile`, `check_docstrings.py` passes on both, and the patched export imports
(`resolve_pin` round-trips). Apply with `patch -p1 < celllink-wiring.patch`, then run
the verification below.

```diff
--- a/src/interfaces/__init__.py
+++ b/src/interfaces/__init__.py
@@ -1,15 +1,35 @@
 """Single source of truth for engine contracts: wire schemas, typed
 commands, events, and outbound ports. No I/O, no logic."""

+from .celllink import (
+    REFERENCE,
+    CellLinkError,
+    collect_erc,
+    match_cell_filters,
+    resolve_cell,
+    resolve_link,
+    resolve_pin,
+    resolve_run,
+    validate_celllink,
+)
 from .documents import validate_document
 from .errors import ContractError
 from .ports import ToolAdapter
 from .references import check_connection, resolve_reference

 __all__ = [
+    "REFERENCE",
+    "CellLinkError",
     "ContractError",
     "ToolAdapter",
     "check_connection",
+    "collect_erc",
+    "match_cell_filters",
+    "resolve_cell",
+    "resolve_link",
+    "resolve_pin",
     "resolve_reference",
+    "resolve_run",
     "validate_document",
+    "validate_celllink",
 ]
--- a/src/composition.py
+++ b/src/composition.py
@@ -44,6 +44,7 @@
 from .adapters.syntax import SyntaxAdapter
 from .execution.errors import ExecutionError
 from .execution.service import ExecutionService
+from .interfaces.celllink import resolve_run as resolve_celllink_run
 from .interfaces.setup import report_capabilities
 from .interfaces.vocabulary import OPERATIONS, QUERIES
 from .library.catalog import Catalog
@@ -700,6 +701,32 @@
         """
         return self._execution.findings(run_id, limit=limit, cursor=cursor)

+    def resolve_celllinks(self, blocks, known_cells, variant=None):
+        """Resolve run/export cell-link records for block instances.
+
+        CELL-LINK seam: resolves (cell, pinMap, variant) per block
+        through interfaces.celllink, emitting only non-empty links.
+        Editing stays free — unknown cells fail here, at run time.
+
+        Args:
+            blocks: Block mappings, each with an id and an optional
+                CellLink component.
+            known_cells: Available cell names the run may target.
+            variant: Variant name applied to every block; None and
+                REFERENCE resolve each stored base link.
+
+        Returns:
+            Emission records in input order, each with block, cell,
+            pinMap, and variant keys.
+
+        Raises:
+            ContractError: invalid_block for a malformed block
+                entry, unknown_variant for an undefined variant.
+            CellLinkError: unknown_cell naming the block and cell
+                when a resolved cell is unavailable to the run.
+        """
+        return resolve_celllink_run(blocks, known_cells, variant=variant)
+
     def _run_queued(self, command):
         """Execute an admitted request by id (phase 2 of submit-then-run).
```

Post-patch verification (integrator, full env):

    python scripts/api_spec.py --write && git diff --stat docs/   # expect no changes: no new ops/queries
    python scripts/contract.py --write && git diff --stat docs/
    python -m pytest tests/interfaces/test_celllink.py tests/interfaces/test_celllink_run.py \
      tests/interfaces/test_celllink_wiring.py -q               # expect 47 passed, 0 skipped
    # then the full suite + gate per ticket acceptance.

## Refusals with reasons

- No edits to any existing file (`src/**`, `scripts/**`, docs, `tests/pdk_*/`,
  `docs/pdk/*/`): ownership allows creates only; all wiring is delivered as the
  patch above.
- No full-suite run: lane rules forbid it on this shared tree; ran only the new
  tests plus the named neighbors (`test_references`, `test_docstrings`, `test_no_cloud`).
- No `api_spec`/`contract` regen run: both rewrite tracked `docs/*` files, which I
  may not edit; the patch adds no operations/queries so regen is expected to be a
  no-op, with the exact commands above for the integrator to confirm.
- No validation-seam patch for `documents.py`/`mutate`: no Block entity or component
  allowlist exists in-tree yet, so there is no anchor to extend; `validate_celllink`
  is the edit-time gate the future Block CRUD calls. Block-scoped run targeting
  belongs to the BLOCK-RUNS ticket; this lane's run seam is `Engine.resolve_celllinks`.
- No use of repo `.venv` or `uv sync`: all runs used the `/tmp/celllink-venv` scratch env.
