# SEAM-COSIM lane report — closed-loop mixed-signal co-simulation

Ticket: `docs/tickets/SEAM-COSIM.md` · Branch: GREEN-the-tests · No commits, no pushes (integrator commits).

## Files added (new files only — zero edits to existing files)

- `src/adapters/cosim/__init__.py` — the coupled solver: `CosimAdapter`
  (`run_cosim` behind the `ToolAdapter` port), stdlib-only SNDR
  estimator (`rfft_power`, `sndr_bits`), mid-period sampler
  (`sample_bits`, `settled_stats`), deck builder
  (`build_cosim_deck`), and the I28 record builder
  (`build_run_record`). Tiers are job inputs, never fixtures.
- `src/adapters/cosim/README.md` — adapter note (protocol, rules,
  tier inputs, patch pointers).
- `tests/adapters/test_cosim.py` (47 tests) — fast suite: port,
  preflight, estimator oracles, sampler, deck builder, canned
  joint-verdict mapping, staging seams. No tools needed.
- `tests/adapters/test_cosim_live.py` (14 live + 3 wiring + PEX set)
  — tier-1 live matrix, gated PEX-tier proofs, post-patch Engine
  wiring tests (skip until the patch lands).
- `tests/adapters/cosim_staging.py` — sigma-delta staging helpers
  (PEX wrapper, tier-1 xschem body, digital half via shipped
  MUTATE-HARNESS staging, tier job builders).
- `tests/adapters/fixtures/hdl/sdm_rx_cosim_bench.v` — live-vector
  verdict bench (protocol gates stay fatal; counts/data reported
  for the Python-side joint verdict).
- `docs/work/SEAM-COSIM/wiring.patch` — the exact wiring patch
  (vocabulary + composition + setup), also inlined below.
  Validated with `git apply --check` and behaviorally in-process.
- `docs/work/SEAM-COSIM/seam-tests.patch` — the VALIDATE-M seam-test
  update (honest-gap probe retires, handoff regression stays),
  also inlined below. Validated with `git apply --check`.
- `docs/work/SEAM-COSIM/report.md` — this file.

## Contract implemented (ticket clause → behavior)

- Coupled solver `run_cosim`: ngspice tran on the analog half,
  sampled mid-period into bits, streamed live as `cosim_bits.txt`
  into the sdm_rx RTL under icarus, one engine run, joint verdict.
- Joint verdict = SNDR >= 36 dB AND RTL ones-density/counts/
  golden-model all PASS. Quantitative misses are rule
  `measurement` (the halves' shared rule, mirroring
  `NgspiceAdapter`), so seam mutations keep their declared rules:
  sdm_* → only `assert_fatal`, sdtop_*/analog → only `measurement`.
- Digital native violations pass through with their own rules; a
  bench `$fatal` suppresses pile-on Python-side checks (cascade
  suppression); a valueless analog half synthesizes `sim_fail`
  quoting ngspice's error text. Verdicts always come from parsed
  output, never the exit code.
- Determinism: single-threaded tran (`num_threads=1`, the top_tb.py
  prescription), analytic sample instants, no timestamps or random
  inputs in natives; 3x-identical proven at both tiers.
- Artifacts per run: verdict JSON + native logs + run record with
  I28 ingredient closure for BOTH halves (per-half sources+sha,
  deck sha, vector/bits sha, loop config, solver versions, PDK
  closure verified fresh — drift fails loudly).
- Tiers are project inputs: `analog_sources` + loop config select
  the tier-1 behavioral body (model-free, seconds) or the PEX
  macro + wrapper (store models, ~6 min). The adapter hardcodes no
  fixture, no netlist, no band.

## TDD gates: RED → GREEN evidence

Commands run from `rocket-engine/` with the provisioned `.venv`
(`scripts/install.sh --install` once for venv+PDK; sealed refresh
after adding sources), `PATH` with oss-cad-suite bins,
`ROCKETEDA_HOME=/tmp/rocketeda-home` (the default store path is
read-only in this sandbox; the knob is documented).

- RED: `pytest tests/adapters/test_cosim.py
  tests/adapters/test_cosim_live.py -q` → `61 failed, 1 passed, 8
  skipped`: every adapter-importing test fails on
  `ModuleNotFoundError` (the pass is a staging-seam test with no
  adapter dependency; skips are the PEX gates + wiring).
- GREEN fast: `tests/adapters/test_cosim.py` → `47 passed`
  (port, preflight incl. the strobe-coverage guard, estimator
  oracles, sampler, deck builder, canned verdicts, staging).
- GREEN tier-1 live: combined `61 passed, 10 skipped in 143.71s`
  (good PASS in band, 7/7 sdm_* → only `assert_fatal`, mute +
  3 RIN fault classes → only `measurement`, 3x determinism over
  good + all mutants, artifacts + I28; skips = PEX set + wiring).
- GREEN PEX-tier good: `test_pex_good_joint_passes_in_extracted_band`
  → `1 passed in 365.94s`, SNDR 39.06 dB in 38.3–40.7, ones
  0.4922, golden bit-exact, PDK sky130A pinned.
- GREEN PEX matrix: `test_pex_sdtop_mutant_flips_only_measurement`
  (5 seeds) + `test_pex_determinism_3x_good` → `6 passed in
  2612.74s`; every sdtop_* seed flips the JOINT verdict with
  `{measurement}` only, 3x good bit-identical (see appendix).
- Docstring gate: `scripts/check_docstrings.py` on the new module
  and the full tree → clean (exit 0); 100-col limit holds on all
  new files.
- Named neighbors (real tree, unpatched): `tests/test_docstrings.py`,
  `tests/test_api_spec.py`, `tests/test_contract.py`,
  `tests/test_check_contract.py` → 29 passed; `test_mixed.py` seam
  trio + staging guard → 4 passed (honest gap intact pre-patch).

## Live evidence (measured values)

Estimator oracle (stdlib, no numpy): recorded `pex_bits.txt` →
40.191 dB (documented 40.2 dB), ones 0.4946 exact; FFT cross-checked
against a naive DFT to 1e-9 relative.

| Case | SNDR (dB) | ones | Joint |
| --- | --- | --- | --- |
| tier-1 good (4096/256/5) | 37.52 (band 36.4–38.0) | 0.5000 | PASS |
| tier-1 mute (AMP=0) | -inf | 0.5000 | FAIL measurement |
| tier-1 rin_hi (RIN×0.29) | -inf | 0.0000 | FAIL measurement |
| tier-1 rin_lo (RIN×3.9) | 26.98 | 0.6694 | FAIL measurement |
| tier-1 rin_open (R_IN lifted) | -15.92 | 0.7283 | FAIL measurement |
| PEX good (2048/64/13) | 39.06 (band 38.3–40.7) | 0.4922 | PASS |
| PEX sdtop_* (5 seeds) | -10.5…30.6 (all < 36) | 0.23–0.70 | FAIL measurement |

rin_hi trips both the SNDR and the ones-density gate (two
violations, one rule): the loop rails under 3.4x input gain. The
"only it" contract holds at rule level for every mutant.

## Integrator runbook

1. `git apply --check docs/work/SEAM-COSIM/wiring.patch
   docs/work/SEAM-COSIM/seam-tests.patch` (must print nothing),
   then `git apply` both. The seam patch must land WITH the wiring
   patch: the old honest-gap probe fails once `run_cosim` registers.
2. Refresh the sealed install so the new adapter resolves, then
   regen the derived contracts:
   `uv pip install --python .venv/bin/python --no-deps .` (or full
   `scripts/install.sh --install`),
   `python scripts/api_spec.py --write && python scripts/contract.py --write`
   (both report stale before, fresh after — no `STUB_OVERLAP`
   additions: the new op has no fuel-stub counterpart yet, which
   the contract tolerates, same as SETTINGS-STORE).
3. Run: `.venv/bin/python -m pytest tests/adapters/test_cosim.py
   tests/adapters/test_cosim_live.py tests/validate/test_mixed.py -q`
   → all green with the 3 wiring tests unskipped (21 live + PEX
   gates as set). PEX tiers:
   `COSIM_PEX_LIVE=1` adds the ~6 min extracted proof;
   `COSIM_PEX_MATRIX=1` adds the sdtop_* matrix + 3x (~1.5 h).

Behavioral validation of the patch (no tracked file touched, no
import shimmed): `/tmp/cosim_wirecheck.py` registers the three
hunks in-process on the real tree and proves engine.run PASS with
measurements on the verdict, findings [], capabilities ready,
job_kinds `[cosim]`, MCP `tools/call run_cosim` admitted with
verdict PASS, and the seam-probe logic → WIRECHECK GREEN. The
script stays under `/tmp` for review, out of the deliverable.

## Wiring patch (exact — also in `wiring.patch`)

```diff
diff --git a/src/composition.py b/src/composition.py
--- a/src/composition.py
+++ b/src/composition.py
@@ -28,7 +28,7 @@
 first registered (run_drc: magic, then klayout; run_optical: sax;
 run_extraction: magic; run_lvs: netgen; run_spice: ngspice;
 run_syntax: slang; run_hdl_test: icarus; run_connectivity:
-connectgraph; run_erc: connectgraph).
+connectgraph; run_erc: connectgraph; run_cosim: cosim).
 Unregistered operations and unknown deck tools raise instead of
 faking a verdict.
 """
@@ -39,6 +39,7 @@
 from ruamel.yaml import YAML

 from .adapters.connectivity import ConnectivityAdapter
+from .adapters.cosim import CosimAdapter
 from .adapters.drc import MagicDrcAdapter
 from .adapters.drc_kl import KlayoutDrcAdapter
 from .adapters.errors import AdapterError
@@ -270,6 +271,7 @@
             "run_syntax": {"slang": SyntaxAdapter()},
             "run_connectivity": {"connectgraph": ConnectivityAdapter()},
             "run_erc": {"connectgraph": ConnectivityAdapter()},
+            "run_cosim": {"cosim": CosimAdapter()},
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
+    ("run_cosim", "cosim"): {"binaries": ["ngspice", "iverilog", "vvp"]},
 }


 class SetupError(ContractError):
diff --git a/src/interfaces/vocabulary.py b/src/interfaces/vocabulary.py
--- a/src/interfaces/vocabulary.py
+++ b/src/interfaces/vocabulary.py
@@ -10,7 +10,7 @@
         "run_connectivity", "run_drc", "run_lvs", "run_erc", "run_spice",
         "run_optical", "run_digital_flow", "run_timing", "run_extraction",
         "run_post_layout", "run_em", "run_thermal", "python_execute",
-        "run_view_sync", "run_job",
+        "run_view_sync", "run_cosim", "run_job",
         "resume_run", "discard_run", "resume_all_retryable",
         "create_project", "write_doc", "delete_doc", "apply_mutations",
         "rewind", "place_cell", "write_settings",
```

## Seam-tests patch (exact — also in `seam-tests.patch`)

```diff
diff --git a/tests/validate/test_mixed.py b/tests/validate/test_mixed.py
--- a/tests/validate/test_mixed.py
+++ b/tests/validate/test_mixed.py
@@ -974,18 +974,22 @@
     assert "36" in text


-def test_seam_status_honest_no_closed_loop():
-    # The engine has no coupled mixed-signal solver: run_hdl_test and
-    # run_spice are separate operations with no joint deck. This test
-    # fails if anyone claims a closed loop by wiring a fake joint op.
+def test_seam_closed_loop_wired():
+    # SEAM-COSIM closed the loop: run_cosim couples a live analog
+    # tran to the RTL in one engine run with joint verdicts. The
+    # one-way pex_bits handoff test above stays as the
+    # recorded-vector regression; this probe pins the wiring shape
+    # (single cosim tool; the halves keep their single tools).
     from rocket_engine.composition import Engine
+    from rocket_engine.interfaces.vocabulary import OPERATIONS

     engine = Engine("validate_m_seam_probe", actor="validate-m")
     solvers = engine._solvers
-    assert "run_cosim" not in solvers
+    assert set(solvers.get("run_cosim", {})) == {"cosim"}
     assert "run_mixed_signal" not in solvers
     assert set(solvers.get("run_hdl_test", {})) == {"icarus"}
     assert set(solvers.get("run_spice", {})) == {"ngspice"}
+    assert "run_cosim" in OPERATIONS


 # Staging guards: unknown designs and missing pieces fail loudly.
```

## PEX matrix appendix (sdtop_* joint flips + determinism)

`COSIM_PEX_LIVE=1 COSIM_PEX_MATRIX=1 pytest
test_pex_sdtop_mutant_flips_only_measurement
test_pex_determinism_3x_good` → **6 passed in 2612.74s (43:32)**.
5/5 sdtop_* seeds FAIL with rule-set exactly `{measurement}`;
3/3 good repeats bit-identical (verdict, canon findings, SNDR
39.06, 2048 sampled bits). Values measured from the runs'
persisted waveforms with the lane sampler:

| Case | SNDR (dB) | ones | Flipped gate |
| --- | --- | --- | --- |
| sizing-0 (RIN l=30, gain high) | 5.52 | 0.6953 | SNDR |
| sizing-1 (RIN l=400, gain low) | 30.64 | 0.2998 | SNDR |
| sizing-2 (RIN l=10, extreme) | 4.25 | 0.7036 | SNDR |
| open-0 (X64 → UA0_OPEN) | -9.66 | 0.2329 | SNDR |
| open-1 (X64 commented) | -10.53 | 0.2329 | SNDR |

Opens still modulate (idle limit cycle, ones 0.23) but carry no
signal, hence negative SNDR; the mild sizing-1 degrades the loop
gain 4x and lands 5.4 dB under the gate, as predicted. Every ones
value stays inside [0.2, 0.8], so each flip is SNDR-only within
the single `measurement` rule.

## Refused / not changed (with reasons)

- No existing file edited (`git diff --stat` empty): composition,
  vocabulary, setup, test_mixed, scripts, pyproject/uv.lock,
  generated docs — all integrator-applied via the two patches +
  regen runbook above.
- `tests/pdk_*/` and `docs/pdk/*/` untouched (PDK-lane ownership);
  full suite never run (lane tests + named neighbors only).
- No scenario backend added to `scripts/scenarios.py`: the joint
  lane is proven through the adapter + Engine directly; a
  `cosim_tier1`/`cosim_pex` scenario backend is follow-up, not
  required for the ticket's acceptance.
- No `scripts/mutate.py` recheck path for run_cosim: recheck
  dispatches on `OPERATORS[].operation` (`run_hdl_test`/`run_spice`);
  joint rechecks ride the suite's `_tier1_case`/`_pex_case` shapes.
- The vendored fixture is never written: xschem netlists a scratch
  copy (see gOF1 finding), params are emitted to scratch, the PEX
  X99 clamp applies to staged copies via shipped staging.

## Findings for the integrator

- `uic` is a per-job analog knob (default False): tier-1 seeds its
  integrator from `.ic` (fixture's own `uic` tran) while PEX must
  start from the DC operating point (cold-start physics). Without
  it tier-1 rails at -700 V and reads all-zeros.
- xschem 3.4.8 compat: `gOF1` is the only tier-1 ground symbol
  without explicit `lab=GND`, and this xschem leaves its net
  floating (R_OFF dangles, SNDR 23 dB). Staging normalizes a scratch
  schematic copy with the attribute its six siblings carry and
  asserts `R_OFF sum GND` post-netlist; the sim then reproduces
  the documented band (37.52 dB). Drift-guarded both ends.
- The SNDR estimator replicates the vendor `snr.py` guard quirk
  (signal sums spec sig±1, guard zeroes spec sig-2..sig+4) so lane
  numbers match designer numbers exactly; the single deliberate
  deviation is `-inf` instead of numpy `nan`+warning on empty
  ratios (deterministic, pinned by test).
- Shared-tree venv churn: peer lanes re-ran `uv venv --clear`
  several times mid-session, wiping the sealed install; each time
  repaired with install.sh's own sealed-install step (no shims, no
  alternate envs). Integrator runs are single-lane and unaffected.
- `rin_hi` fires two `measurement` violations (SNDR and ones): the
  "only it" contract is at rule level, matching the OPERATORS table
  shape (`expected_rules: ["measurement"]`).
- PDK store in this sandbox lives at `/tmp/rocketeda-home`
  (`ROCKETEDA_HOME`, documented knob) because the default path is
  read-only here; outside the sandbox the default resolves and
  `scripts/install.sh --install` registers identically.

