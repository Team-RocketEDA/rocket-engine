# SETUP-HONESTY lane report — no false-ready probes, fresh tests, capable readiness

Ticket: `docs/tickets/SETUP-HONESTY.md` · Branch: `GREEN-the-tests`
Findings in: `docs/work/E2E-REREVIEW/journey-photonic.md` (F3),
`docs/work/E2E-REREVIEW/journey-mixed.md` (F5),
`docs/work/E2E-REREVIEW/invariant-map.md` (F2).
Lane constraint: new files + wiring patch only — no tracked file
edited, nothing committed, `tests/pdk_*/` and `docs/pdk/*/` untouched.

## Outcome

All three faces fixed (RED-first, each proven RED→GREEN):

1. Shadow-proof spec detection — `src/interfaces/setup_probes.py`
   (`detect_python` requires a real loader plus installed
   distribution metadata; namespace shadows and dist-less
   directories report missing). Tracked `setup.py:195` false-readies
   today (`found: True` on a loader-less spec).
2. Refreshed stale mask — wiring patch #2 replaces tracked
   `_no_sax` (masks only `sax`) with `_no_python_solvers` masking
   `sax`, `circulax`, `meow`, `gdsfactory`. Masking only sax+circulax
   is insufficient: with `meow` installed (the finding's env),
   `run_em` still reads ready and the fresh-machine test still fails.
3. Capability-aware readiness — `src/workflows/capability_plan.py`
   (`plan_from_capabilities` plans a flow against the
   `report_capabilities` operations mapping; missing `sta` → M11
   not-ready with the `sta` missing item and the OpenSTA remedy).

## New files (this lane's fix + tests)

| File | Contents |
|---|---|
| `src/interfaces/setup_probes.py` | `detect_python(names)` — shadow-proof probe |
| `src/workflows/capability_plan.py` | `plan_from_capabilities(flow, operations)` |
| `tests/interfaces/test_setup_honesty.py` | 8 tests: probe units + wired-report composition + refreshed-mask behavior |
| `tests/workflows/test_capability_plan.py` | 8 tests: planner units + live-report integration |

Committed tests import the new modules (and the new-module probe
patched over the tracked report path at runtime), so they pass
before AND after the integrator applies the wiring patch.

## RED→GREEN evidence (all observed in-session)

Env for every command: `UV_CACHE_DIR=/tmp/uv-cache
UV_LINK_MODE=copy PATH=$HOME/tools/oss-cad-suite/bin:$HOME/tools/bin:$PATH
ROCKETEDA_HOME=/tmp/rocketeda-live` (+ `MPLCONFIGDIR=/tmp/mpl`
`XDG_CONFIG_HOME=/tmp/xdg-clean` for warning-free output).

### Fix 1 — import shadow (`/tmp/red_probe_shadow.py`, `/tmp/overlay_patch1.py`)

RED (tracked `setup._detect_python`, empty `gdsfactory/` dir on path):

```text
find_spec: ModuleSpec(name='gdsfactory', loader=None, ...)
tracked _detect_python found: {'gdsfactory': True} missing: []
RED CONFIRMED: shadow reads as installed (false-ready).
generate_views readiness: ready
```

GREEN (same report with `setup._detect_python` swapped for the new
`detect_python` at runtime — exactly what wiring patch #1 makes
permanent):

```text
RED (tracked probe): readiness=ready available=True missing=[]
GREEN (patched probe): readiness=blocked available=False missing=['gdsfactory']
OVERLAY PATCH #1: RED->GREEN proven.
```

### Fix 2 — stale mask (`/tmp/red_green_mask.py`, `/tmp/apply_patch2.py`)

RED: tracked `tests/interfaces/test_setup.py` with the second
`run_optical` solver installed — reproduced twice, once with a
stub circulax test-double and once genuinely in-tree after a
sibling lane synced the photonic group (`circulax 0.2.5`):

```text
FAILED tests/interfaces/test_setup.py::test_fresh_machine_names_every_missing_tool_with_remedy
FAILED tests/interfaces/test_setup.py::test_sax_absent_reports_photonic_remedy
2 failed in 0.23s
```

GREEN: the `/tmp` copy with wiring patch #2 applied verbatim:

```text
2 passed in 0.21s
PATCH #2: RED->GREEN proven.
```

### Fix 3 — no-sta M11 (`/tmp/before_after_cap.py`)

```text
sta on PATH: None
BEFORE applicable_stages M11: ready
AFTER plan_from_capabilities M11: blocked
blocked_by: ['run_timing']
missing: ['sta']
remedy: Install the pinned OpenSTA build 857316f (run scripts/provision_toolchain.sh --i
PATCH #3: before/after proven.
```

### Regression state (final observed run)

```text
pytest tests/interfaces/test_setup_honesty.py
  tests/workflows/test_capability_plan.py tests/interfaces/test_setup.py
  tests/workflows/test_process_data.py tests/test_api_spec.py
  tests/test_docstrings.py
2 failed, 42 passed in 187.80s
```

The 2 failures are exactly the tracked stale-mask tests above
(env currently has the photonic group installed — the genuine F2
RED); all 16 new lane tests pass in the same env. Earlier, on the
baseline env: `tests/interfaces + tests/workflows` → 392 passed,
12 skipped. Gates: `check_docstrings.py` (full tree) clean,
`api_spec.py --check` clean, `contract.py --check` clean — the new
modules add no wired endpoint, so no regen output changes.

## Exact wiring patch (integrator applies to tracked files)

### Patch #1 — `src/interfaces/setup.py`: delegate to the shadow-proof probe

```diff
--- a/src/interfaces/setup.py
+++ b/src/interfaces/setup.py
@@ -28,8 +28,6 @@
 """  (context only)
 
-import importlib.metadata
-import importlib.util
 import shutil
 from pathlib import Path
 
@@ -38,6 +36,7 @@
 from .errors import ContractError
 from .paths import slugify
 from .pdks import list_pdks, resolve_deck, resolve_engine_root
+from .setup_probes import detect_python
 from .vocabulary import OPERATIONS
 
@@ -191,15 +190,9 @@
 def _detect_python(names):
     """Split module names into found versions and missing names."""
-    found, missing = {}, []
-    for name in names:
-        if importlib.util.find_spec(name) is None:
-            missing.append(name)
-            continue
-        try:
-            found[name] = importlib.metadata.version(name)
-        except importlib.metadata.PackageNotFoundError:
-            found[name] = True
-    return found, missing
+    # Shadow-proof probe (SETUP-HONESTY): requires a real loader
+    # plus installed distribution metadata — see setup_probes.
+    return detect_python(names)
```

(`importlib.metadata` / `importlib.util` have no other use in
`setup.py`; the removal keeps imports honest. No cycle:
`setup_probes` imports stdlib only. `_detect_python` keeps its
name/signature, so `entry_state` and `report_capabilities` are
untouched.)

### Patch #2 — `tests/interfaces/test_setup.py`: mask every Python solver

Full unified diff, verified verbatim: `/tmp/apply_patch2.py`
applies exactly this to the tracked file (1 helper hunk + 12
call-site renames) and the patched copy passes (`2 passed` above).
 timestamps trimmed; `@@` lines match tracked HEAD.

```diff
--- a/tests/interfaces/test_setup.py
+++ b/tests/interfaces/test_setup.py
@@ -70,11 +70,18 @@
     return empty
 
 
-def _no_sax(monkeypatch):
+# Every Python-module solver the setup surface can report: a
+# fresh-machine simulation must mask all of them, or whichever
+# solver it forgets (circulax alongside sax, meow, gdsfactory)
+# reads ready and the simulation lies.
+_MASKED_PYTHON_SOLVERS = frozenset({"sax", "circulax", "meow", "gdsfactory"})
+
+
+def _no_python_solvers(monkeypatch):
     real = importlib.util.find_spec
 
     def _fake(name, *args, **kwargs):
-        if name == "sax":
+        if name in _MASKED_PYTHON_SOLVERS:
             return None
         return real(name, *args, **kwargs)
 
@@ -150,7 +157,7 @@
 def test_submit_get_capabilities_is_wired(tmp_path, monkeypatch):
     engine = _engine()  # RED: unsupported_operation
     _bare_path(monkeypatch, tmp_path)
-    _no_sax(monkeypatch)
+    _no_python_solvers(monkeypatch)
 
     report = _submit(engine, {"engine_root": str(tmp_path / "nostore")})
 
@@ -161,7 +168,7 @@
 def test_fresh_machine_names_every_missing_tool_with_remedy(tmp_path, monkeypatch):
     engine = _engine()  # RED: unwired query
     _bare_path(monkeypatch, tmp_path)
-    _no_sax(monkeypatch)
+    _no_python_solvers(monkeypatch)
     _no_network(monkeypatch)
 
     report = _submit(engine, {"engine_root": str(tmp_path / "nostore")})
@@ -211,7 +218,7 @@
 def test_single_tool_install_flips_exactly_its_state(tmp_path, monkeypatch):
     engine = _engine()  # RED: unwired query
     _bare_path(monkeypatch, tmp_path)
-    _no_sax(monkeypatch)
+    _no_python_solvers(monkeypatch)
     args = {"engine_root": str(tmp_path / "nostore")}
 
     before = {
@@ -239,7 +246,7 @@
 
     engine = _engine()  # RED: unwired query
     _bare_path(monkeypatch, tmp_path)
-    _no_sax(monkeypatch)
+    _no_python_solvers(monkeypatch)
     root = tmp_path / "root"
     args = {"engine_root": str(root)}
 
@@ -264,7 +271,7 @@
     engine = _engine()  # RED: unwired query
     bindir = _bindir(tmp_path, ["netgen"], banner=MESHER_BANNER)
     monkeypatch.setenv("PATH", str(bindir))
-    _no_sax(monkeypatch)
+    _no_python_solvers(monkeypatch)
 
     report = _submit(engine, {"engine_root": str(tmp_path / "nostore")})
 
@@ -277,7 +284,7 @@
 
 def test_sax_absent_reports_photonic_remedy(tmp_path, monkeypatch):
     engine = _engine()  # RED: unwired query
-    _no_sax(monkeypatch)
+    _no_python_solvers(monkeypatch)
 
     report = _submit(engine, {"engine_root": str(tmp_path / "nostore")})
 
@@ -291,7 +298,7 @@
 def test_cloud_entries_gated_without_keys_and_no_network(tmp_path, monkeypatch):
     engine = _engine()  # RED: unwired query
     _bare_path(monkeypatch, tmp_path)
-    _no_sax(monkeypatch)
+    _no_python_solvers(monkeypatch)
     _no_network(monkeypatch)
 
     report = _submit(engine, {"engine_root": str(tmp_path / "nostore")})
@@ -306,7 +313,7 @@
 def test_capabilities_pass_through_adapter_reports(tmp_path, monkeypatch):
     engine = _engine()  # RED: unwired query
     _bare_path(monkeypatch, tmp_path)
-    _no_sax(monkeypatch)
+    _no_python_solvers(monkeypatch)
 
     report = _submit(
         engine, {"target": "probe", "engine_root": str(tmp_path / "nostore")}
@@ -324,7 +331,7 @@
 def test_unregistered_operations_report_unsupported(tmp_path, monkeypatch):
     engine = _engine()  # RED: unwired query
     _bare_path(monkeypatch, tmp_path)
-    _no_sax(monkeypatch)
+    _no_python_solvers(monkeypatch)
 
     report = _submit(engine, {"engine_root": str(tmp_path / "nostore")})
 
@@ -343,7 +350,7 @@
 
     engine = _engine()
     _bare_path(monkeypatch, tmp_path)
-    _no_sax(monkeypatch)
+    _no_python_solvers(monkeypatch)
 
     report = _submit(engine, {"engine_root": str(tmp_path / "nostore")})
 
@@ -357,7 +364,7 @@
 def test_query_reads_without_creating_store(tmp_path, monkeypatch):
     engine = _engine()  # RED: unwired query
     _bare_path(monkeypatch, tmp_path)
-    _no_sax(monkeypatch)
+    _no_python_solvers(monkeypatch)
     root = tmp_path / "root"
 
     _submit(engine, {"engine_root": str(root)})
@@ -375,7 +382,7 @@
     engine = _engine()
     engine.register_solver("run_em", _Emx(), tool="emx")
     _bare_path(monkeypatch, tmp_path)
-    _no_sax(monkeypatch)
+    _no_python_solvers(monkeypatch)
 
     try:
         _submit(engine, {"engine_root": str(tmp_path / "nostore")})
```

### Patch #3 — `src/workflows/__init__.py`: export the capable planner

```diff
--- a/src/workflows/__init__.py
+++ b/src/workflows/__init__.py
@@ -1,5 +1,6 @@
 """D/A/P/M step order and check plans as data. Never calls solvers directly."""
 
+from .capability_plan import plan_from_capabilities
 from .connectgraph import (
     RULE_DANGLING_NET,
     RULE_ORPHAN_LABEL,
@@ -26,6 +27,7 @@
 __all__ = [
     "STAGES",
     "applicable_stages",
+    "plan_from_capabilities",
     "Connectivity",
     "ConnectGraphError",
```

(`applicable_stages` is intentionally unchanged — existing
callers and `test_missing_backend_keeps_stage_required` keep their
contract; the capable planner is the new surface for tool-aware
plans. No cycle: `capability_plan` imports `stages` only.)

## Integrator steps

1. Apply patches #1–#3 above to the three tracked files (or apply
   `/tmp/apply_patch2.py`'s transform for #2 — it asserts the
   tracked text matches before writing).
2. Reseal (only env path; offline flag works off the warm cache):
   `export UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy` then
   `UV_OFFLINE=1 scripts/install.sh --install`. Confirm
   `diff -rq src .venv/lib/python3.12/site-packages/rocket_engine
   --exclude=__pycache__` is empty.
3. Lane tests:
   `.venv/bin/python -m pytest
   tests/interfaces/test_setup_honesty.py
   tests/workflows/test_capability_plan.py
   tests/interfaces/test_setup.py -q` → all pass (the 2 stale-mask
   failures from §RED must be gone; in a photonic-group env this is
   the proof, in baseline they pass either way).
4. Contract freshness: `scripts/api_spec.py --check` and
   `scripts/contract.py --check` (expect no output), plus
   `scripts/check_docstrings.py` (expect exit 0). No `--write`
   regen needed: no wired endpoint or docstring contract changed.
5. Full suite + gate per the ticket: `pytest -q` (note: in THIS
   sandbox `tests/pdk_ihp` fails collection on `No module named
   'klayout'` — pre-existing env gap, out of lane scope) and the
   `scripts/correctness.py` gate.

## Notes and risks

- Behavior decision (fix 1): the probe requires loader AND
  version, per the finding's proposed title ("require loader +
  version"). A bare source dir without installed dist metadata now
  reports missing. All four catalogued Python tools (sax,
  circulax, meow, gdsfactory) ship dist metadata under the
  project's own `uv sync --group` profiles, so no honest install
  flips to missing; `test_distless_directory_reports_missing`
  pins the rule.
- Behavior decision (fix 2): the mask covers all four Python
  solvers, a strict superset of the ticket's "circulax alongside
  sax" — required, because `meow` (and a future installed
  `gdsfactory`) would otherwise keep the fresh-machine simulation
  lying, as shown in §RED.
- Fix 3 adds no Engine surface: the I27 completion-claim wiring
  (`plan_checks`) stays a separate ticket per the invariant map's
  F1; this lane delivers the capability-aware readiness
  computation it can consume.
- Shared-workspace caveat: sibling lanes concurrently reseal the
  venv and sync extra groups; the sealed copy drifted twice
  mid-lane (`src/adapters/meow/_envelope.py` unsealed at report
  time — not this lane's file). Step 2's reseal absorbs that.
- Repro scripts (throwaway, kept under `/tmp` per policy, not
  committed): `/tmp/red_probe_shadow.py`, `/tmp/red_probe_m11.py`,
  `/tmp/overlay_patch1.py`, `/tmp/apply_patch2.py`,
  `/tmp/red_green_mask.py`, `/tmp/before_after_cap.py`,
  `/tmp/patch2/test_setup_patched.py`, `/tmp/patch2_full.diff`.
