# MEOW-STDOUT fix lane — report

Ticket: `docs/tickets/MEOW-STDOUT.md` · Branch: GREEN-the-tests ·
Finding: `docs/work/E2E-REREVIEW/journey-photonic.md` FIND-05.
Lane constraint: new files + wiring patch only — no tracked file
was modified, nothing committed or pushed.

## Root cause

`MeowAdapter.parse` runs `json.loads` over the whole driver stdout
(`src/adapters/meow/adapter.py:339`), but tidy3d prints its
unwritable-config warning to **stdout** on import (verified:
162 bytes on stdout, `import tidy3d` alone). Any impurity raises
`runner_unavailable`, so 4 healthy live solves report NOT_RUN in
the default env. The driver docstring claim ("solver warnings go
to stderr untouched") is falsified in this environment.

## Delivered files (new, in tree)

- `src/adapters/meow/_envelope.py` — marker-delimited envelope
  extraction. Clean streams parse exactly as before; marked
  streams use the BEGIN/END frame authoritatively; unmarked noisy
  streams fall back to a tolerant scan preferring the
  envelope-shaped value. Chatter is logged at warning level
  (truncated to 500 chars) and never fatal; no envelope (or a
  corrupt marked frame) returns None so `parse` keeps raising the
  same `runner_unavailable`. Pure stdlib, Google-style docstrings,
  `check_docstrings` clean, 100-col clean.
- `tests/adapters/test_meow_stdout_chatter.py` — 9 extractor unit
  tests (green now) + 3 wiring regression pins (RED until the
  patch below lands): chatter-tolerant parse, marker-frame-beats-
  decoy parse, driver-emits-markers. A chatter-without-envelope
  negative guard passes before and after.

## Exact wiring patch (integrator applies)

```diff
--- a/src/adapters/meow/adapter.py
+++ b/src/adapters/meow/adapter.py
@@ -45,6 +45,10 @@
     from ..errors import AdapterError
 except ImportError:
     from rocket_engine.adapters.errors import AdapterError
+try:
+    from ._envelope import extract_envelope
+except ImportError:
+    from rocket_engine.adapters.meow._envelope import extract_envelope
 
 OPERATION = "run_em"
 _TIMEOUT_S = 120
@@ -335,13 +339,12 @@
                 printed no JSON envelope or no result.
         """
         spec = native_output.get("spec", "")
-        try:
-            envelope = json.loads(native_output.get("stdout", ""))
-        except (TypeError, ValueError):
+        envelope = extract_envelope(native_output.get("stdout", ""))
+        if envelope is None:
             raise AdapterError(
                 "runner_unavailable",
                 "meow driver printed no JSON envelope.",
-            ) from None
+            )
         if not isinstance(envelope, dict) or not isinstance(
             envelope.get("ok"), bool
         ):
--- a/src/adapters/meow/_driver.py
+++ b/src/adapters/meow/_driver.py
@@ -1,9 +1,10 @@
-"""Staged meow EME driver: job JSON in, result envelope JSON on stdout.
+"""Staged meow EME driver: job JSON in, framed result envelope on stdout.
 
 The adapter copies this file into the run workdir next to
 `meow_job.json` and executes `python meow_driver.py meow_job.json`.
-Exactly one JSON document is printed to stdout; solver warnings go
-to stderr untouched.
+The envelope is framed between ROCKETEDA-ENVELOPE-BEGIN/END marker
+lines; solver warnings may share stdout — the adapter extracts the
+frame and logs the rest, never fatal.
 
 Cross-sections are built from the project spec (`doc` widths_um /
 wl_um / cell_length_um): nothing is hardcoded — widths, wavelength,
@@ -38,6 +39,9 @@
 NY = 41
 SI_HEIGHT_UM = 0.22
 
+_ENVELOPE_BEGIN = "ROCKETEDA-ENVELOPE-BEGIN"
+_ENVELOPE_END = "ROCKETEDA-ENVELOPE-END"
+
 
 def _token(doc, message):
     names = list(_TOKEN_KEYS) + [str(doc.get("device") or "")]
@@ -58,19 +62,28 @@
     return None
 
 
+def _emit(payload):
+    """Print one marker-framed JSON envelope on stdout.
+
+    Marker literals mirror src/adapters/meow/_envelope.py — this
+    file stages standalone, so change both or neither.
+    """
+    print(_ENVELOPE_BEGIN)
+    print(json.dumps(payload))
+    print(_ENVELOPE_END)
+
+
 def _fail(code, message, token, line):
-    print(
-        json.dumps(
-            {
-                "ok": False,
-                "error": {
-                    "code": code,
-                    "message": message,
-                    "token": token,
-                    "line": line,
-                },
-            }
-        )
+    _emit(
+        {
+            "ok": False,
+            "error": {
+                "code": code,
+                "message": message,
+                "token": token,
+                "line": line,
+            },
+        }
     )
 
 
@@ -181,33 +194,31 @@
         tidy3d_version = _metadata.version("tidy3d")
     except Exception:
         tidy3d_version = "unknown"
-    print(
-        json.dumps(
-            {
-                "ok": True,
-                "meow_version": getattr(meow, "__version__", "unknown"),
-                "tidy3d_version": tidy3d_version,
-                "result": {
-                    "wl_um": wl_um,
-                    "widths_um": widths,
-                    "cell_length_um": cell_um,
-                    "base": base,
-                    "refined": refined,
-                    "convergence": {
-                        "dT": abs(
-                            refined["transmission"] - base["transmission"]
-                        ),
-                        "dR": abs(
-                            refined["reflection"] - base["reflection"]
-                        ),
-                        "dneff": abs(
-                            refined["neff_re"][0] - base["neff_re"][0]
-                        ),
-                    },
-                    "ports": ports,
+    _emit(
+        {
+            "ok": True,
+            "meow_version": getattr(meow, "__version__", "unknown"),
+            "tidy3d_version": tidy3d_version,
+            "result": {
+                "wl_um": wl_um,
+                "widths_um": widths,
+                "cell_length_um": cell_um,
+                "base": base,
+                "refined": refined,
+                "convergence": {
+                    "dT": abs(
+                        refined["transmission"] - base["transmission"]
+                    ),
+                    "dR": abs(
+                        refined["reflection"] - base["reflection"]
+                    ),
+                    "dneff": abs(
+                        refined["neff_re"][0] - base["neff_re"][0]
+                    ),
                 },
-            }
-        )
+                "ports": ports,
+            },
+        }
     )
     return 0
 
```

The diff above was generated mechanically (`diff -U3`) from the
patched files the GREEN proof executed, and `git apply --check`
passes on the clean tree. No handler signature or docstring
changed, so contract/api_spec regens are expected no-ops — run
them anyway per acceptance. `json` is still used in adapter.py
(`execute` builds the job JSON); no import fallout. The patched
driver passes `check_no_cloud` (no new imports) and
`check_docstrings`.

## Integrator steps

1. `git apply` the patch above (2 tracked files).
2. Reseal the installed package so the fallback import resolves:
   `uv pip install --python .venv/bin/python --no-deps .`
   (install.sh's own sealed step).
3. `.venv/bin/python scripts/contract.py --write` then
   `.venv/bin/python scripts/api_spec.py --write`.
4. Default env, no XDG workaround
   (`PATH=$HOME/tools/oss-cad-suite/bin:$HOME/tools/bin:$PATH`,
   `ROCKETEDA_HOME=/tmp/rocketeda-live`):
   `.venv/bin/python -m pytest tests/adapters/test_meow_em.py
   tests/adapters/test_meow_stdout_chatter.py
   tests/workflows/test_photonic_wire.py -k "meow_em_live or
   live_meow or chatter or markers"` — expect all green.
5. Full suite + correctness gate green, then commit.

## RED evidence (default env, no XDG)

`.venv/bin/python -m pytest tests/adapters/test_meow_em.py
tests/workflows/test_photonic_wire.py -k "meow_em_live or
live_meow"` → `4 failed, 35 deselected in 25.53s` (both adapter
live tests raise `runner_unavailable: meow driver printed no JSON
envelope`; both wire live tests assert against NOT_RUN verdicts).

`.venv/bin/python -m pytest
tests/adapters/test_meow_stdout_chatter.py` → `3 failed, 10
passed`: the 3 wiring pins fail, all extractor units + the
negative guard pass.

Touched-area sweep (meow + wire + docstrings + no-cloud +
api_spec + contract): `7 failed, 68 passed` — exactly the 4 live
+ 3 pins, zero fallout from the new files.

## GREEN evidence (exact patch, default env, no XDG)

Tracked files were untouchable in this lane, so GREEN was proven
by executing the exact patched file contents via a package-path
overlay (`/tmp/meow-wired/prove_green.py`, scratch, not
delivered): the overlay dir shadows only
`rocket_engine.adapters.meow`; everything else (Engine, ledger,
verdicts) is the real installed tree. Non-vacuity: the proof
asserts the tidy3d WARNING is present in raw driver stdout and the
BEGIN marker was emitted.

Output: 4/4 canned regression equivalents green, then
`GREEN live matched: T=1.0, dT~=0.0, total 0 (chatter present)`,
`GREEN live step: T~=0.877 fail, total >= 1`,
`GREEN live wire proof-replay: PASS, T=1.0, run_id set`,
`GREEN live wire project-width: PASS with convergence evidence`.
Chatter-preserved-in-logs observed: each run logs
`meow driver stdout chatter (130 bytes, never fatal): 00:.. WARNING:
Unable to write to '.../.config/tidy3d' ...`.

## Env notes

- Base env came from `scripts/install.sh --install` (fresh
  `.venv`, sealed install verified `import rocket_engine` ok). The
  venv was re-provisioned concurrently mid-session (mtime
  23:42, photonic group wiped); solver profile restored with the
  pyproject-documented `uv sync --locked --group photonic
  --no-install-project` + the sealed reinstall — no scratch venvs,
  no pip handrolls, no PYTHONPATH shims. Final: meow 0.15.0,
  tidy3d 2.10.0.
- No XDG workaround was used in any proof run; the fix makes it
  unnecessary. Latent F2 (sax/circulax/gdsfactory share the strict
  parse) is out of scope — see ADAPTER-PARSE ticket.
