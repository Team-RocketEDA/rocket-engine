# FORMAL-SBY lane report — run_formal via sby (bounded proof, honestly reported)

Ticket: `docs/tickets/FORMAL-SBY.md` · Branch: GREEN-the-tests ·
No commits, no pushes (integrator commits). New files only — zero
edits to tracked files (verified: `git diff --stat` empty).

## Files added (new files only)

- `src/adapters/formal_sby/__init__.py` — `FormalSbyAdapter`
  behind the `ToolAdapter` port (`OPERATION = "run_formal"`,
  deck.tool `sby`). Preflight refuses the wrong operation, foreign
  deck tools, bad proof inputs (mode/depth/top/engines/timeout),
  missing sources, duplicate basenames, and unresolvable or
  impostor sby (banner version-asserted; every missing-tool error
  names the PROV oss-cad-suite bundle). Execute generates a
  `formal.sby` task from the job's project sources and runs
  `sby -f` bounded and cancellable (own process group, expiry
  SIGKILLs the whole tree and reports a timeout native block).
  Parse normalizes the sby status file plus the DONE summary into
  scoped measurements — proven / bounded / unknown / timeout —
  with assumptions, properties, failures, counterexamples, and
  cover witnesses. Stdlib plus the standard relative/import shim
  (`AdapterError`, `ToolAdapter`, `ExecutionError`,
  `clean_stream`, `tool_roots`); no sibling-lane imports.
- `src/adapters/formal_sby/README.md` — lane readme (protocol,
  scope map, PROV pointer, wiring-patch pointer).
- `tests/adapters/test_formal_sby.py` — 30 RED-first tests (see
  evidence below), incl. 2 wiring tests that skip until the
  integrator applies the patch.
- `tests/adapters/fixtures/formal/` — 8 fixtures: `counter.v`
  (prove PASS), `counter_bad.v` (bmc FAIL + VCD trace),
  `counter_induct.v` (basecase pass / induction fail →
  UNKNOWN), `counter_broken.v` (yosys syntax ERROR),
  `counter_cover.v` (reached cover), `counter_cover_miss.v`
  (unreached cover → FAIL), `serv_alu_prop.v` + `serv_alu_bad.v`
  (true/false BMC properties over upstream SERV `serv_alu.v`).
- `docs/work/FORMAL-SBY/wiring.patch` — the exact wiring patch
  (same text as inline below; apply with `patch -p1`).
- `docs/work/FORMAL-SBY/report.md` — this file.

## Contract implemented (ticket clause → behavior)

- RED-first `run_formal` ToolAdapter driving pinned `sby` —
  `FormalSbyAdapter` serves `run_formal` with deck.tool `sby`
  (the only tool); sby resolves from job `tool_dir` else PATH,
  and preflight version-asserts the banner (`SBY ...`, impostors
  refuse as `missing_dependency`). Tests pin the ambient
  `SBY v0.70` (observed `SBY v0.70-9-g79fc9ed`, Yosys 0.70+219,
  boolector/z3/yices/bitwuzla bundled).
- Scoped verdicts, never a bare PASS — parse returns
  `measurements.scope` in {proven, bounded, unknown, timeout}:
  prove PASS → proven; bmc/cover PASS → bounded at the depth;
  FAIL → bounded with per-property `assert_fail`/`cover_missed`
  error findings plus `counterexamples` (property, step, VCD
  path, on-disk presence); UNKNOWN/ERROR → unknown with
  `formal_unknown`/`formal_error` error findings (induction-gap
  traces and engine notes preserved); wall-clock expiry →
  timeout with a `formal_timeout` error finding. PASS always
  carries scope + banner + depth + assumptions, so an unwarranted
  PASS is unrepresentable; FAIL/UNKNOWN/timeout always carry
  error findings, so nothing inconclusive reads clean.
- `deck.tool sby`; missing binary → loud `missing_dependency`
  naming the PROV bundle — every resolution/probe failure raises
  `missing_dependency` with "PROV bundle: install the pinned
  oss-cad-suite tarball per docs/provision-plan.md, or pass
  tool_dir." A foreign `deck.tool` refuses as
  `unsupported_operation` (engine selection stays authoritative).
- Counterexample fixtures: known-bad fails with a consumable
  trace; timeout reports timeout, never hangs (bounded,
  cancellable) — `counter_bad.v`, `serv_alu_bad.v`, and
  `counter_cover_miss.v` fail with traces asserted present on
  disk; timeout tests drive a fake `sby` that spawns a lingering
  child and sleeps: execute returns a timeout native block
  within budget, the whole tree is reaped (both pids asserted
  dead), and parse reports scope timeout. Runner-contained
  timeouts map to the same scope; other runner failures convert
  to `AdapterError` (hdl_sim precedent, stub-tested).
- Generalization law: the op consumes project inputs — sources,
  top, mode, depth, and engines all arrive via the job; the
  adapter generates the sby task from them (arbitrary absolute
  source paths verified; duplicate basenames refused loudly
  since sby stages into one `src/` dir). Properties live in the
  project sources (assume/assert/cover), exactly as testbenches
  do for the sim lane.
- Clock/reset note (D08): crossing/reset properties run as
  project properties through this op (reset assumes included);
  sby ships no dedicated CDC engine, so no separate crossing
  checker is claimed. SERV's riscv-formal suite needs a network
  checkout and is out of scope; the SERV acceptance is met by
  local BMC properties over the vendored `serv_alu.v`.

## RED → GREEN evidence

Toolchain: provisioned `.venv` via `scripts/install.sh --install`
only (`UV_CACHE_DIR=/tmp/uv-cache`, `UV_LINK_MODE=copy`); live
runs with `PATH=$HOME/tools/oss-cad-suite/bin:$HOME/tools/bin:$PATH`.
The install is a copy (not editable), so every source change was
followed by an install.sh resync — no shims, no hand installs.

RED (tests written before the module):

    .venv/bin/python -m pytest tests/adapters/test_formal_sby.py -q
    # 28 failed in 0.24s — every failure is
    # ModuleNotFoundError: No module named
    #   'rocket_engine.adapters.formal_sby'
    # (The 2 branch-coverage tests added later import the same
    # missing module first, so they are RED-valid by construction.)

GREEN (after adding `src/adapters/formal_sby/` + resync):

    # same command
    # 28 passed, 2 skipped in 7.42s
    # (skips = the 2 wiring tests awaiting the integrator patch)

Named neighbors plus the full tracked suite (PDK dirs excluded
per lane rules; sibling untracked RED files excluded — see note):

    .venv/bin/python -m pytest $(git ls-files 'tests/*.py' \
      'tests/*/*.py' | grep -v -E "tests/pdk_" | grep -E \
      "test_.*\.py$") tests/adapters/test_formal_sby.py -q
    # 1569 passed, 101 skipped, 0 failed in 519.58s

Gates on the final tree:

    .venv/bin/python scripts/check_docstrings.py            # clean, exit 0
    .venv/bin/python scripts/api_spec.py --check            # clean (regen-neutral)
    .venv/bin/python scripts/contract.py --check            # clean (regen-neutral)
    .venv/bin/python scripts/check_no_cloud.py              # clean, exit 0
    awk 'length > 100' on both new .py files                # no hits

One RED-phase catch, fixed before GREEN: two summary regexes
anchored `$` without `re.M`, so mid-log matches silently missed
and FAILs fell into the synthesized-violation path. The
pairing assertions (`trace["property"] is not None`,
witness file/step) now pin the real parse path.

Shared-branch note: mid-session, sibling lanes resynced the
shared `.venv` (and left it briefly broken), causing transient
failures in long runs (a 15-failure neighbor run, a 42-failure
full run). Both reran fully green after a clean resync with no
code changes; the final numbers above are from quiet runs.
`install.sh`'s PDK-register step fails in this sandbox
(read-only `~/.local/share/rocketeda`) — pre-existing env
limitation; sync + import check succeed.

bwrap note: namespaces are unavailable in this sandbox
(`No permissions to create a new namespace`), so there is no
live sandboxed test — the same skip posture as the sim lane.
The runner path is covered by stub tests (error conversion +
timeout mapping).

## Wiring patch for the integrator (exact unified diff)

Verified: `git apply --check` and `patch -p1 --dry-run` both
accept it. Generation verified on /tmp AST copies (no imports,
no tree edits): `solver_map` resolves
`run_formal → FormalSbyAdapter`, Job keys parse (`sources`,
`top` required), `wired: True`, and the reference section
renders. Runtime verified in-process via the public
`register_solver` seam: prove run → PASS/proven with banner
`SBY v0.70-9-g79fc9ed`, bad-property run → FAIL/bounded with a
present VCD trace, and `get_capabilities` with the patch's
detection row → `ready`, sby available. Copy of this diff:
`docs/work/FORMAL-SBY/wiring.patch`.

What the patch does (5 files; no vocabulary, query, CRUD, or
replay changes):

- `src/composition.py`: import + register
  `"run_formal": {"sby": FormalSbyAdapter()}` in `_solvers`
  (deck.tool selects; default first registered), plus the
  one-line module-docstring map update.
- `src/interfaces/setup.py`: `SOLVER_DEPS` gains
  `("run_formal", "sby"): {"binaries": ["sby"]}` so the
  setup surface can probe the solver (a registered solver
  without a row fails loudly as `unknown_solver`).
- 3 tracked tests that pin `run_formal` as the unwired example
  move to `run_em` (still unregistered) / drop the orphan
  assert: `test_engine_run.py`,
  `test_mcp_server.py`, `test_setup.py`.

```diff
diff --git a/src/composition.py b/src/composition.py
--- a/src/composition.py
+++ b/src/composition.py
@@ -28,7 +28,7 @@
 first registered (run_drc: magic, then klayout; run_optical: sax;
 run_extraction: magic; run_lvs: netgen; run_spice: ngspice;
 run_syntax: slang; run_hdl_test: icarus; run_connectivity:
-connectgraph; run_erc: connectgraph).
+connectgraph; run_erc: connectgraph; run_formal: sby).
 Unregistered operations and unknown deck tools raise instead of
 faking a verdict.
 """
@@ -43,6 +43,7 @@
 from .adapters.drc_kl import KlayoutDrcAdapter
 from .adapters.errors import AdapterError
 from .adapters.extract_magic import MagicExtractAdapter
+from .adapters.formal_sby import FormalSbyAdapter
 from .adapters.hdl_sim import HdlSimAdapter
 from .adapters.lvs_netgen import NetgenLvsAdapter
 from .adapters.ngspice import NgspiceAdapter
@@ -270,6 +271,7 @@
             "run_syntax": {"slang": SyntaxAdapter()},
             "run_connectivity": {"connectgraph": ConnectivityAdapter()},
             "run_erc": {"connectgraph": ConnectivityAdapter()},
+            "run_formal": {"sby": FormalSbyAdapter()},
         }
         self._yaml = YAML(typ="safe")
         self._constraints = dict(constraints) if constraints is not None else None
diff --git a/src/interfaces/setup.py b/src/interfaces/setup.py
--- a/src/interfaces/setup.py
+++ b/src/interfaces/setup.py
@@ -61,6 +61,7 @@
     ("run_syntax", "slang"): {"binaries": ["slang"]},
     ("run_connectivity", "connectgraph"): {},
     ("run_erc", "connectgraph"): {},
+    ("run_formal", "sby"): {"binaries": ["sby"]},
 }
 
 
diff --git a/tests/adapters/test_mcp_server.py b/tests/adapters/test_mcp_server.py
--- a/tests/adapters/test_mcp_server.py
+++ b/tests/adapters/test_mcp_server.py
@@ -126,7 +126,7 @@
     result = asyncio.run(
         _call(
             call,
-            "run_formal",
+            "run_em",
             {"project_id": PROJECT, "expected_revision": "p12"},
         )
     )
diff --git a/tests/interfaces/test_setup.py b/tests/interfaces/test_setup.py
--- a/tests/interfaces/test_setup.py
+++ b/tests/interfaces/test_setup.py
@@ -332,7 +332,6 @@
         op for op, detail in report["operations"].items()
         if detail["readiness"] == "unsupported"
     ]
-    assert "run_formal" in orphans
     assert "run_em" in orphans
     for op in orphans:
         assert report["operations"][op]["tools"] == {}
diff --git a/tests/test_engine_run.py b/tests/test_engine_run.py
--- a/tests/test_engine_run.py
+++ b/tests/test_engine_run.py
@@ -76,14 +76,14 @@
         engine.submit(
             {
                 "project_id": PROJECT,
-                "operation": "run_formal",
+                "operation": "run_em",
                 "arguments": {"expected_revision": "p12"},
             }
         )
     except Exception as exc:
         assert getattr(exc, "code", None) == "unsupported_operation"
     else:
-        raise AssertionError("expected unsupported_operation for run_formal")
+        raise AssertionError("expected unsupported_operation for run_em")
 
 
 def test_submit_run_syntax_accepted():
```

## Integrator steps

Run from `rocket-engine/` on a quiet tree (no concurrent
resync — see the shared-branch note above):

1. Check and apply the patch (read-only check first):
   `git apply --check docs/work/FORMAL-SBY/wiring.patch`, then
   `patch -p1 < docs/work/FORMAL-SBY/wiring.patch`.
2. Resync (the install is a copy — required for the new
   package and wiring to take effect):
   `export UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy`
   then `bash scripts/install.sh --install` (sync + import
   check must succeed; the PDK-register step fails on
   read-only stores — pre-existing, unrelated).
3. Put live tools on PATH:
   `export PATH=$HOME/tools/oss-cad-suite/bin:$HOME/tools/bin:$PATH`.
4. Regen the contract artifacts (the patch is intentionally
   regen-positive — `run_formal` becomes wired):
   `.venv/bin/python scripts/api_spec.py --write` then
   `.venv/bin/python scripts/contract.py --write`.
   Expect diffs only in `docs/engine-api.md`,
   `docs/api-schema.json`, `docs/api-help.json`, and
   `docs/contract.json`: the `run_formal` section becomes
   wired (`Tools: sby`, Job keys with `sources`/`top`
   required) and the contract sha bumps. Confirm with
   `git status` — nothing else should move.
5. Verify: `--check` variants exit 0;
   `.venv/bin/python -m pytest tests/adapters/test_formal_sby.py -q`
   → 30 passed, 0 skipped (both wiring tests go green);
   full suite green; `check_docstrings.py` and
   `check_no_cloud.py` exit 0.
6. Follow-up outside this repo: `UIUX/src/engine/client.test.ts`
   asserts `unsupported_operation` for `run_formal` — flag to
   the UIUX owner post-merge.
