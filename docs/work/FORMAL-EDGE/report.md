# FORMAL-EDGE lane report — vacuity guard + ifdef-aware sites

Ticket: `docs/tickets/FORMAL-EDGE.md` · Findings: F1 (MED) + F2 (LOW)
in `docs/work/E2E-REREVIEW/journey-digital.md` · Branch: GREEN-the-tests ·
No commits, no pushes (integrator commits). New files only — zero
edits to tracked files (verified: `git diff --stat` empty).

## Files added (new files only)

- `src/adapters/formal_sby/formal_edge.py` — the fix: `property_sites`
  (ifdef-aware, define-skipping) plus `guard_vacuous_pass` (zero
  properties → loud bounded-vacuous FAIL). Stdlib only; Google-style
  docstrings; 100-col clean; `check_docstrings` clean.
- `tests/adapters/test_formal_edge.py` — 10 RED-first tests: 8 unit
  tests over the new helpers (always GREEN after resync) + 2 wiring
  tests that skip until the integrator applies the patch.
- `docs/work/FORMAL-EDGE/wiring.patch` — the exact wiring patch
  (same text as inline below; apply with `patch -p1`).
- `docs/work/FORMAL-EDGE/report.md` — this file.

## Contract implemented (ticket clause → behavior)

- Vacuity detection — zero properties → loud bounded-vacuous verdict,
  never a bare PASS; docstring aligned. `guard_vacuous_pass` returns
  None when ≥1 property was checked, else scope `bounded-vacuous`
  plus a `formal_vacuous` error violation. The wiring patch calls it
  on every sby PASS in `parse`: vacuous PASS becomes total 1 with
  `measurements.scope = bounded-vacuous` and `measurements.vacuous =
  True`, so engine `evaluate` (FAIL on any error) judges FAIL. The
  sby truth is preserved (`sby_status PASS`, `sby_rc 0`); only the
  scope + verdict refuse the vacuous proof. Docstrings aligned:
  module, class, and `parse` docstrings now state PASS always means
  ≥1 property checked, zero-property PASS is bounded-vacuous FAIL.
- Ifdef-aware site counting with a picorv32 regression test.
  `property_sites` strips `/* */` (multi-line) + `//` comments,
  never counts `` `define `` lines, resolves `` `ifdef``/`` `ifndef``/
  `` `elsif``/`` `else``/`` `endif`` against the active defines
  (default `{FORMAL}`, matching sby `read -formal`; verified: plain
  `read_verilog` elaborates 0 `$assert`, `read -formal` elaborates
  the full set with or without extra `-DFORMAL`), and tracks
  `` `define``/`` `undef`` in active branches. Same return shape as
  `_property_sites` (assumptions file+line, properties file+line+kind);
  unreadable sources skipped, never fatal. Picorv32: 26 → 23 sites
  (3 define-line hits on :40×2/:47 gone); with `defines=set()` the
  `` `ifdef FORMAL `` block drops out (23 → 13), pinning ifdef-awareness.

## RED → GREEN evidence

Toolchain: provisioned `.venv` via `scripts/install.sh --install`
only (`UV_CACHE_DIR=/tmp/uv-cache`, `UV_LINK_MODE=copy`); live runs
with `PATH=$HOME/tools/oss-cad-suite/bin:$HOME/tools/bin:$PATH`,
`ROCKETEDA_HOME=/tmp/rocketeda-live`. The install is a copy (not
editable), so every source change was followed by an install.sh
resync — no shims, no hand installs.

RED (probes against tracked code before the fix; scripts in /tmp,
not in the repo):

    .venv/bin/python /tmp/formal-edge-red/red_vacuous.py
    # sites assumptions: [] properties: []
    # total: 0 violations: []
    # scope: bounded sby_status: PASS properties: []
    # → property-free plain.v returns bare PASS (F1 reproduced)

    .venv/bin/python /tmp/formal-edge-red/red_sites.py
    # assumptions: 0 properties: 26
    # define-line hits: lines 40 (×2), 47
    # → `define assert( lines counted (F2 reproduced)

GREEN (after adding `formal_edge.py` + resync):

    .venv/bin/python -m pytest tests/adapters/test_formal_edge.py -v
    # 8 passed, 2 skipped in 0.06s
    # (skips = the 2 wiring tests awaiting the integrator patch)

Named neighbors (no regression):

    .venv/bin/python -m pytest tests/adapters/test_formal_sby.py -q
    # 30 passed in 7.35s

Full tracked suite + new file (PDK dirs excluded per lane rules):

    .venv/bin/python -m pytest $(git ls-files 'tests/*.py'
      'tests/*/*.py' | grep -v -E "tests/pdk_" | grep -E
      "test_.*\.py$") tests/adapters/test_formal_edge.py -q
    # 1769 passed, 117 skipped, 165 failed, 11 errors in 1497.56s
    # (tail: photonic/console/workflows failures, zero in formal).
    # The failures are shared-branch noise, not this lane: this lane
    # edits zero tracked files (nothing new is imported by tracked
    # tests), and reruns prove it — sampled full-run failures
    # (test_photonic_wire + test_console_route_wiring, 9 tests) rerun
    # 9 passed in isolation, and formal reruns 38 passed + 2 wiring
    # skips. Same transient pattern as the FORMAL-SBY lane report
    # (sibling .venv resync mid-run; this run took 1497s vs the
    # 519s quiet baseline). Integrator: rerun the full suite on a
    # quiet tree after applying the patch.

Gates on the final tree:

    .venv/bin/python scripts/check_docstrings.py            # clean, exit 0
    .venv/bin/python scripts/api_spec.py --check            # clean (regen-neutral)
    .venv/bin/python scripts/contract.py --check            # clean (regen-neutral)
    .venv/bin/python scripts/check_no_cloud.py              # clean, exit 0
    awk 'length > 100' on both new .py files                # no hits

Wiring-patch verification (no tree edits): `git apply --check` exit
0, `patch -p1 --dry-run` accepts, patched AST parses, patched file
100-col clean, and an in-process simulation of the patched logic
(monkeypatched exactly as the patch wires) yields vacuous → total 1
scope bounded-vacuous rule formal_vacuous, synthetic define+ifdef
sites → [6], and counter.v PASS still total 0.

## Wiring patch for the integrator (exact unified diff)

Verified: `git apply --check` and `patch -p1 --dry-run` both
accept it. Copy of this diff: `docs/work/FORMAL-EDGE/wiring.patch`.

What the patch does (1 file; no vocabulary, query, CRUD, replay,
or contract changes — regen-neutral by check):

- `src/adapters/formal_sby/__init__.py`: import the two helpers;
  `_property_sites` becomes an ifdef-aware delegate (new optional
  `defines` param, backwards-compatible); `parse` guards every sby
  PASS with `guard_vacuous_pass` (vacuous → total 1, scope
  bounded-vacuous, `vacuous: True`); module, class, and `parse`
  docstrings aligned to the guard.

```diff
diff --git a/src/adapters/formal_sby/__init__.py b/src/adapters/formal_sby/__init__.py
--- a/src/adapters/formal_sby/__init__.py
+++ b/src/adapters/formal_sby/__init__.py
@@ -6,8 +6,8 @@
 `sby -f` under a timeout in its own process group, and parse the
 machine-readable status file plus the DONE summary line
 (PASS rc 0, FAIL rc 2, UNKNOWN rc 4, ERROR rc 16). Verdicts always
-carry scope (proven/bounded/unknown/timeout) with assumptions and
-counterexamples — never a bare PASS.
+carry scope (proven/bounded/bounded-vacuous/unknown/timeout) with
+assumptions and counterexamples — never a bare PASS.

 Tool resolution: an explicit job `tool_dir` wins, else PATH. The
 sby banner is version-asserted (an impostor binary refuses as
@@ -26,6 +26,7 @@
 from ...execution.runner import clean_stream, tool_roots
 from ...interfaces import ToolAdapter
 from ..errors import AdapterError
+from .formal_edge import guard_vacuous_pass, property_sites

 OPERATION = "run_formal"
 _TIMEOUT_S = 300
@@ -68,27 +69,16 @@
 _PROP_RE = re.compile(r"\b(assert|assume|cover)\s*\(")


-def _property_sites(sources):
-    """Assume/assert/cover sites by file and line (evidence-grade).
+def _property_sites(sources, defines=None):
+    """Active assume/assert/cover sites by file and line (evidence-grade).

-    Line comments are stripped before matching; a site is one
-    matched keyword per line. Unreadable sources are skipped, never
-    fatal — the sites annotate the verdict, they are not the verdict.
+    Ifdef-aware delegate to formal_edge.property_sites: define lines
+    never count and ifdef branches resolve against the active
+    defines (FORMAL assumed, matching sby read -formal). Unreadable
+    sources are skipped, never fatal — the sites annotate the
+    verdict, they are not the verdict.
     """
-    assumptions, properties = [], []
-    for source in sources:
-        try:
-            text = Path(source).read_text(encoding="utf-8", errors="replace")
-        except OSError:
-            continue
-        for lineno, line in enumerate(text.splitlines(), start=1):
-            for match in _PROP_RE.finditer(line.split("//", 1)[0]):
-                entry = {"file": str(source), "line": lineno}
-                if match.group(1) == "assume":
-                    assumptions.append(entry)
-                else:
-                    properties.append({**entry, "kind": match.group(1)})
-    return assumptions, properties
+    return property_sites(sources, defines=defines)


 def _split_at(token):
@@ -247,8 +237,9 @@
     sources, runs it bounded and cancellable, and parses the sby
     status plus the DONE summary into a scoped verdict: prove PASS
     is proven, bmc/cover PASS is bounded to the depth, FAIL carries
-    counterexamples, inconclusive runs are unknown, and wall-clock
-    exhaustion is timeout — never a bare PASS.
+    counterexamples, inconclusive runs are unknown, wall-clock
+    exhaustion is timeout, and zero-property PASS is bounded-vacuous
+    FAIL — never a bare PASS.

     Job keys:
         sources (required): RTL source paths carrying the design
@@ -457,7 +448,10 @@
         with neither the output refuses as runner_unavailable —
         unparseable never parses as clean. Timeout natives report
         scope timeout; FAIL/UNKNOWN/ERROR always carry error
-        findings, so PASS always means some scope was earned.
+        findings, so PASS always means at least one property was
+        checked in some scope; zero-property sby PASS reports scope
+        bounded-vacuous with a formal_vacuous error (engine FAIL),
+        never a bare PASS.

         Args:
             native_output: Native output from execute with the
@@ -538,6 +532,19 @@
             }
         )
         if status == "PASS":
+            vacuous = guard_vacuous_pass(
+                properties,
+                mode=native_output.get("mode"),
+                depth=native_output.get("depth"),
+            )
+            if vacuous is not None:
+                measures["scope"] = vacuous["scope"]
+                measures["vacuous"] = True
+                return {
+                    "total": 1,
+                    "violations": [vacuous["violation"]],
+                    "measurements": measures,
+                }
             scope = "proven" if native_output.get("mode") == "prove" else "bounded"
             measures["scope"] = scope
             return {"total": 0, "violations": [], "measurements": measures}
```

## Integrator steps

Run from `rocket-engine/` on a quiet tree (no concurrent
resync — the shared `.venv` breaks under concurrent installs):

1. Check and apply the patch (read-only check first):
   `git apply --check docs/work/FORMAL-EDGE/wiring.patch`, then
   `patch -p1 < docs/work/FORMAL-EDGE/wiring.patch`.
2. Resync (the install is a copy — required for the new
   package and wiring to take effect):
   `export UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy`
   then `bash scripts/install.sh --install` (sync + import
   check must succeed; the PDK-register step fails on
   read-only stores — pre-existing, unrelated).
3. Put live tools on PATH:
   `export PATH=$HOME/tools/oss-cad-suite/bin:$HOME/tools/bin:$PATH`
   and `export ROCKETEDA_HOME=/tmp/rocketeda-live`.
4. Regen check (expect neutral — the patch adds no operations):
   `.venv/bin/python scripts/api_spec.py --check` and
   `.venv/bin/python scripts/contract.py --check` both exit 0
   with no diff. If either is dirty, run `--write` and confirm
   `git status` shows only the four contract artifacts.
5. Verify: `.venv/bin/python -m pytest
   tests/adapters/test_formal_edge.py -q` → 10 passed, 0
   skipped (both wiring tests go green);
   `.venv/bin/python -m pytest tests/adapters/test_formal_sby.py
   -q` → 30 passed (no vacuity regressions: every existing PASS
   fixture carries ≥1 property); full suite green;
   `check_docstrings.py` and `check_no_cloud.py` exit 0.
6. Note: any downstream consumer asserting bare PASS on a
   property-free design (none found in-tree) must now expect
   FAIL with scope `bounded-vacuous` and rule `formal_vacuous`.
