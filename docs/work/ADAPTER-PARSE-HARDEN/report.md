# ADAPTER-PARSE-HARDEN lane report — marker-delimited envelopes for sax/circulax/gdsfactory

Ticket: `docs/tickets/ADAPTER-PARSE-HARDEN.md` · Branch: GREEN-the-tests · No commits, no pushes (integrator commits).
Finding evidence: `docs/work/E2E-REREVIEW/journey-photonic.md` FIND-09/F2 (strict whole-stdout parse in `src/adapters/sax/__init__.py:366`, `src/adapters/circulax/adapter.py:397`, `src/adapters/gdsfactory/adapter.py:455`).

## Files added (new files only — zero edits to existing files)

- `src/adapters/envelope.py` — shared marker-delimited envelope helper: `ENVELOPE_BEGIN/END` (`ROCKETEDA_ENVELOPE_BEGIN/END`), `emit_envelope(payload)`, `extract_envelope(stdout, *, tool)`. Markers first, then legacy whole-stdout, then best-effort envelope scan for unmarked chatter. Error messages preserved exactly (`sax`/`circulax`/`views`/`meow` + `driver printed no JSON envelope.`). Stdlib + `AdapterError` only.
- `tests/adapters/test_adapter_parse_harden.py` — 23 tests: 8 helper unit tests (roundtrip, legacy, marked/unmarked chatter, garbage/wrong-shape/truncated rejection, bytes), 4 per adapter (marked chatter, unmarked chatter, error envelope with chatter, garbage still raises), 3 driver-framing checks.
- `docs/work/ADAPTER-PARSE-HARDEN/wiring.patch` — the exact wiring patch as a file (same text as inline below; apply with `patch -p1`).
- `docs/work/ADAPTER-PARSE-HARDEN/report.md` — this file.

## Contract implemented (ticket clause → behavior)

- RED-first marker-delimited parsing in all three adapters via one shared helper (no three copies): each `parse` replaces its strict `json.loads(stdout)` + shape check with `extract_envelope(stdout, tool=...)` (`sax`, `circulax`, `views`). Drivers frame both success and `_fail` envelopes with BEGIN/END prints around the existing JSON print (no logic change, no reindent).
- Chatter-injection regression tests per adapter: tidy3d-style WARNING prefix (journey F1 text) + progress suffix, marked and unmarked, success and error envelopes. Warnings stay in native stdout; the Engine logs it verbatim (`src/composition.py` `_run_operation` stores `stdout`+`stderr` in `_logs[run_id]`), so warnings are preserved in logs, never fatal.
- Shared helper preferred: `src/adapters/envelope.py` serves all three (and meow via `tool="meow"` for the MEOW-STDOUT lane's reuse — that lane's adapter/driver are untouched here).
- Backward compatible: clean legacy stdout (no markers) parses as before; garbage still raises `runner_unavailable` with the identical message (existing rejection tests keep passing).

## RED → GREEN evidence

Env: `UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy`, `PATH=$HOME/tools/oss-cad-suite/bin:$HOME/tools/bin:$PATH`, `ROCKETEDA_HOME=/tmp/rocketeda-live`. Provisioned only via `scripts/install.sh --install` (twice: once to repair the broken `.venv` with no `rocket_engine` installed, once to pick up the new helper into the sealed copy). PDK reverified; toolchain DEGRADED (librelane/opensta absent, expected offline).

RED (clean tree, helper installed, adapters unpatched):

    .venv/bin/python -m pytest tests/adapters/test_adapter_parse_harden.py -q
    # 12 failed, 11 passed in 0.12s
    # FAILED: 9 adapter chatter (3 per adapter: marked/unmarked/error-with-chatter)
    # FAILED: 3 driver framing (no markers yet)
    # PASSED: 8 helper unit + 3 garbage-still-raises (old rejection intact)

GREEN (wiring applied to /tmp/aph-patched tree copy; its own `.venv` via install.sh; repo tree never edited):

    cd /tmp/aph-patched && .venv/bin/python -m pytest \
      tests/adapters/test_adapter_parse_harden.py -q
    # 23 passed in 0.10s

Named neighbors (clean 79 passed → patched 102 passed = 79 + 23 new, zero regressions):

    # clean repo (without new tests):
    .venv/bin/python -m pytest tests/adapters/test_sax.py \
      tests/adapters/test_circulax_optical.py \
      tests/adapters/test_generate_views.py tests/adapters/test_gdsfactory.py \
      tests/test_docstrings.py tests/test_api_spec.py -q
    # 79 passed, 17 skipped in 192s
    # patched copy (with new tests):
    # 102 passed, 17 skipped in 194s
    .venv/bin/python scripts/check_docstrings.py src/adapters/envelope.py \
      src/adapters/sax/__init__.py src/adapters/circulax/adapter.py \
      src/adapters/gdsfactory/adapter.py
    # clean (exit 0) on both trees
    .venv/bin/python scripts/api_spec.py --check && \
      .venv/bin/python scripts/contract.py --check
    # exit 0 on both trees: regen-neutral, no new operations/queries

Style: no line over 100 chars in new/patched files (repo ruff limit).

## Wiring patch for the integrator (exact unified diff)

Verified: `patch -p1 --dry-run` applies cleanly to a pristine copy, the applied result is byte-identical to the tested tree (`cmp` on all 7 files), all patched files `py_compile`, `check_docstrings.py` passes, and the patched tree runs 102/102 neighbor tests with `api_spec`/`contract --check` green. Apply with `patch -p1 < docs/work/ADAPTER-PARSE-HARDEN/wiring.patch`, then run the verification below. Copy of this diff: `docs/work/ADAPTER-PARSE-HARDEN/wiring.patch`.

What the patch does (3 adapters + 3 drivers + 1 strict test; no vocabulary, ledger, or API changes):

- Each adapter `parse`: replace strict `json.loads(stdout)` + shape check with `extract_envelope(stdout, tool=...)` (same `runner_unavailable` message on no envelope). Imports follow each file's style (direct for sax, try/except fallback for circulax/gdsfactory file-loader tests).
- Each `_driver.py`: `ROCKETEDA_ENVELOPE_BEGIN/END` constants + BEGIN/END prints around both envelope prints (success + `_fail`); module docstring notes marker framing and chatter tolerance.
- `tests/adapters/test_generate_views.py::test_generate_views_driver_reports_missing_solver_loudly`: strict `json.loads(proc.stdout)` → `extract_envelope(proc.stdout, tool="views")` (the one tracked test that reads real driver stdout; it failed on marked output until updated).

```diff
diff --git a/src/adapters/circulax/_driver.py b/src/adapters/circulax/_driver.py
index 0aec7a1..4cba8e3 100644
--- a/src/adapters/circulax/_driver.py
+++ b/src/adapters/circulax/_driver.py
@@ -2,8 +2,9 @@
 
 The adapter copies this file into the run workdir next to
 `circulax_job.json` and executes `python circulax_driver.py
-circulax_job.json`. Exactly one JSON document is printed to stdout;
-solver warnings go to stderr untouched.
+circulax_job.json`. One marker-delimited JSON envelope is printed to stdout
+(ROCKETEDA_ENVELOPE_BEGIN/END); chatter outside the markers is
+tolerated and stays in logs.
 
 The netlist is built from the project spec (`doc` instances +
 connections + transient): nothing is hardcoded — R/C/V, the
@@ -24,6 +25,9 @@ import json
 import re
 import sys
 
+_ENVELOPE_BEGIN = "ROCKETEDA_ENVELOPE_BEGIN"
+_ENVELOPE_END = "ROCKETEDA_ENVELOPE_END"
+
 _QUOTED_RE = re.compile(r"""['\"]([^'\"]+)['\"]""")
 
 _COMPONENTS = ("vsource", "resistor", "capacitor", "ground")
@@ -51,6 +55,7 @@ def _find_line(text, token):
 
 
 def _fail(code, message, token, line):
+    print(_ENVELOPE_BEGIN)
     print(
         json.dumps(
             {
@@ -64,6 +69,7 @@ def _fail(code, message, token, line):
             }
         )
     )
+    print(_ENVELOPE_END)
 
 
 def main(argv):
@@ -156,6 +162,7 @@ def main(argv):
         token = _token(doc, message)
         _fail("invalid_circuit", message, token, _find_line(text, token))
         return 2
+    print(_ENVELOPE_BEGIN)
     print(
         json.dumps(
             {
@@ -174,6 +181,7 @@ def main(argv):
             }
         )
     )
+    print(_ENVELOPE_END)
     return 0
 
 
diff --git a/src/adapters/circulax/adapter.py b/src/adapters/circulax/adapter.py
index cf04191..6520ab8 100644
--- a/src/adapters/circulax/adapter.py
+++ b/src/adapters/circulax/adapter.py
@@ -41,6 +41,10 @@ try:
     from ...interfaces import ToolAdapter
 except ImportError:
     from rocket_engine.interfaces import ToolAdapter
+try:
+    from ..envelope import extract_envelope
+except ImportError:
+    from rocket_engine.adapters.envelope import extract_envelope
 try:
     from ..errors import AdapterError
 except ImportError:
@@ -393,20 +397,9 @@ class CirculaxAdapter(ToolAdapter):
                 driver printed no JSON envelope or no result.
         """
         spec = native_output.get("spec", "")
-        try:
-            envelope = json.loads(native_output.get("stdout", ""))
-        except (TypeError, ValueError):
-            raise AdapterError(
-                "runner_unavailable",
-                "circulax driver printed no JSON envelope.",
-            ) from None
-        if not isinstance(envelope, dict) or not isinstance(
-            envelope.get("ok"), bool
-        ):
-            raise AdapterError(
-                "runner_unavailable",
-                "circulax driver printed no JSON envelope.",
-            )
+        envelope = extract_envelope(
+            native_output.get("stdout", ""), tool="circulax"
+        )
         if not envelope["ok"]:
             error = envelope.get("error") or {}
             code = error.get("code")
diff --git a/src/adapters/gdsfactory/_driver.py b/src/adapters/gdsfactory/_driver.py
index 4756453..509ee1c 100644
--- a/src/adapters/gdsfactory/_driver.py
+++ b/src/adapters/gdsfactory/_driver.py
@@ -2,8 +2,9 @@
 
 The adapter copies this file into the run workdir next to
 `gf_views_job.json` and executes `python gf_views_driver.py
-gf_views_job.json`. Exactly one JSON document is printed to stdout;
-solver warnings go to stderr untouched.
+gf_views_job.json`. One marker-delimited JSON envelope is printed to stdout
+(ROCKETEDA_ENVELOPE_BEGIN/END); chatter outside the markers is
+tolerated and stays in logs.
 
 Every recipe consumes project inputs from the job: view-spec cells +
 params, project GDS paths, and the optional project pin map. Nothing
@@ -23,6 +24,9 @@ import json
 import sys
 from pathlib import Path
 
+_ENVELOPE_BEGIN = "ROCKETEDA_ENVELOPE_BEGIN"
+_ENVELOPE_END = "ROCKETEDA_ENVELOPE_END"
+
 _BOUNDARY_NOTE = (
     "GDS import alone does not reconstruct macro pins/obstructions "
     "(PRD boundary note); bind a project pin_map to publish them."
@@ -34,6 +38,7 @@ _BUILD_NOTE = (
 
 
 def _fail(code, message, token, line):
+    print(_ENVELOPE_BEGIN)
     print(
         json.dumps(
             {
@@ -47,6 +52,7 @@ def _fail(code, message, token, line):
             }
         )
     )
+    print(_ENVELOPE_END)
 
 
 def _find_line(text, token):
@@ -410,6 +416,7 @@ def main(argv):
         _fail("unsupported_format", str(exc), recipe,
               _find_line(text, recipe))
         return 2
+    print(_ENVELOPE_BEGIN)
     print(
         json.dumps(
             {
@@ -431,6 +438,7 @@ def main(argv):
             }
         )
     )
+    print(_ENVELOPE_END)
     return 0
 
 
diff --git a/src/adapters/gdsfactory/adapter.py b/src/adapters/gdsfactory/adapter.py
index 09875b9..f595ba5 100644
--- a/src/adapters/gdsfactory/adapter.py
+++ b/src/adapters/gdsfactory/adapter.py
@@ -42,6 +42,10 @@ try:
     from ...interfaces import ToolAdapter
 except ImportError:
     from rocket_engine.interfaces import ToolAdapter
+try:
+    from ..envelope import extract_envelope
+except ImportError:
+    from rocket_engine.adapters.envelope import extract_envelope
 try:
     from ..errors import AdapterError
 except ImportError:
@@ -451,20 +455,9 @@ class GdsfactoryViewsAdapter(ToolAdapter):
         if not spec:
             sources = native_output.get("sources") or []
             spec = sources[0] if sources else ""
-        try:
-            envelope = json.loads(native_output.get("stdout", ""))
-        except (TypeError, ValueError):
-            raise AdapterError(
-                "runner_unavailable",
-                "views driver printed no JSON envelope.",
-            ) from None
-        if not isinstance(envelope, dict) or not isinstance(
-            envelope.get("ok"), bool
-        ):
-            raise AdapterError(
-                "runner_unavailable",
-                "views driver printed no JSON envelope.",
-            )
+        envelope = extract_envelope(
+            native_output.get("stdout", ""), tool="views"
+        )
         if not envelope["ok"]:
             error = envelope.get("error") or {}
             code = error.get("code")
diff --git a/src/adapters/sax/__init__.py b/src/adapters/sax/__init__.py
index c5f6799..38bd308 100644
--- a/src/adapters/sax/__init__.py
+++ b/src/adapters/sax/__init__.py
@@ -24,6 +24,7 @@ from ruamel.yaml import YAML
 from ...execution.errors import ExecutionError
 from ...execution.runner import tool_roots
 from ...interfaces import ToolAdapter
+from ..envelope import extract_envelope
 from ..errors import AdapterError
 
 OPERATION = "run_optical"
@@ -362,18 +363,9 @@ class SaxAdapter(ToolAdapter):
                 target pair.
         """
         spec = native_output.get("spec", "")
-        try:
-            envelope = json.loads(native_output.get("stdout", ""))
-        except (TypeError, ValueError):
-            raise AdapterError(
-                "runner_unavailable", "sax driver printed no JSON envelope."
-            ) from None
-        if not isinstance(envelope, dict) or not isinstance(
-            envelope.get("ok"), bool
-        ):
-            raise AdapterError(
-                "runner_unavailable", "sax driver printed no JSON envelope."
-            )
+        envelope = extract_envelope(
+            native_output.get("stdout", ""), tool="sax"
+        )
         if not envelope["ok"]:
             error = envelope.get("error") or {}
             code = error.get("code")
diff --git a/src/adapters/sax/_driver.py b/src/adapters/sax/_driver.py
index 2a73a6b..7ebceff 100644
--- a/src/adapters/sax/_driver.py
+++ b/src/adapters/sax/_driver.py
@@ -1,8 +1,9 @@
 """Staged SAX sim driver: job JSON in, result envelope JSON on stdout.
 
 The adapter copies this file into the run workdir next to `sax_job.json`
-and executes `python sax_driver.py sax_job.json`. Exactly one JSON
-document is printed to stdout; sax warnings go to stderr untouched.
+and executes `python sax_driver.py sax_job.json`. One marked JSON
+envelope is printed to stdout (ROCKETEDA_ENVELOPE_BEGIN/END);
+chatter outside the markers is tolerated and stays in logs.
 
 Envelope: `{"ok": true, "sax_version, "result": {wavelength_nm[],
 transmission{"a>b": []}, ports[]}}` or `{"ok": false, "error":
@@ -16,6 +17,9 @@ import json
 import re
 import sys
 
+_ENVELOPE_BEGIN = "ROCKETEDA_ENVELOPE_BEGIN"
+_ENVELOPE_END = "ROCKETEDA_ENVELOPE_END"
+
 _QUOTED_RE = re.compile(r"""['\"]([^'\"]+)['\"]""")
 
 
@@ -51,6 +55,7 @@ def _find_line(text, token):
 
 
 def _fail(code, message, token, line):
+    print(_ENVELOPE_BEGIN)
     print(
         json.dumps(
             {
@@ -64,6 +69,7 @@ def _fail(code, message, token, line):
             }
         )
     )
+    print(_ENVELOPE_END)
 
 
 def main(argv):
@@ -120,6 +126,7 @@ def main(argv):
         token = _token(doc, message)
         _fail("invalid_circuit", message, token, _find_line(text, token))
         return 2
+    print(_ENVELOPE_BEGIN)
     print(
         json.dumps(
             {
@@ -133,6 +140,7 @@ def main(argv):
             }
         )
     )
+    print(_ENVELOPE_END)
     return 0
 
 
diff --git a/tests/adapters/test_generate_views.py b/tests/adapters/test_generate_views.py
index f765d4e..3977cdc 100644
--- a/tests/adapters/test_generate_views.py
+++ b/tests/adapters/test_generate_views.py
@@ -500,8 +500,10 @@ def test_generate_views_driver_reports_missing_solver_loudly(tmp_path):
         text=True,
         timeout=120,
     )
+    from rocket_engine.adapters.envelope import extract_envelope
+
     assert proc.returncode == 3
-    envelope = json.loads(proc.stdout)
+    envelope = extract_envelope(proc.stdout, tool="views")
     assert envelope["ok"] is False
     assert envelope["error"]["code"] == "missing_dependency"
 
```

Post-patch verification (integrator, full env):

    export UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy
    export PATH=$HOME/tools/oss-cad-suite/bin:$HOME/tools/bin:$PATH
    export ROCKETEDA_HOME=/tmp/rocketeda-live
    patch -p1 < docs/work/ADAPTER-PARSE-HARDEN/wiring.patch
    bash scripts/install.sh --install   # sealed copy picks up helper + wiring
    .venv/bin/python -m pytest tests/adapters/test_adapter_parse_harden.py -q
    # expect 23 passed
    .venv/bin/python scripts/api_spec.py --write && git diff --stat docs/
    # expect no changes: no new ops/queries
    .venv/bin/python scripts/contract.py --write && git diff --stat docs/
    # expect no changes
    # then the full suite + gate per ticket acceptance.

## Refusals with reasons

- No edits to any existing file: ownership allows creates only; all wiring is delivered as the patch above (developed and tested on /tmp tree copies; the repo tree was never modified in place).
- No full-suite run: ran only the new tests plus the named neighbors above (sax, circulax, views, gdsfactory, docstrings, api_spec); the full suite + gate are the integrator's post-patch step per ticket acceptance.
- No `api_spec`/`contract --write` run: both rewrite tracked `docs/*` files, which I may not edit; `--check` passes on both the real and patched trees, with the exact `--write` commands above for the integrator to confirm the no-op.
- No `tests/pdk_*/` or `docs/pdk/*/` touched.
- No meow scope: `src/adapters/meow/*` untouched (MEOW-STDOUT lane owns it); the helper accepts `tool="meow"` for that lane's reuse. If that parallel lane created its own envelope helper at the same path, the integrator keeps one copy (this helper's marked + legacy + scan behavior) and points both lanes at it.
- No live solver runs: all new tests use canned envelopes (no photonic/layout groups needed); live tests skip loudly without them, as designed.
- No scratch venvs, PYTHONPATH shims, or handrolled pip installs: all runs used `.venv` provisioned only via `scripts/install.sh --install` (repo + one /tmp patched copy).
