# EVAL DEFINITION: mvp-correctness

Eval-driven contract for MUTATE-HARNESS, VALIDATE-D/A/P/M, and the
single-command ENGINE-CORRECTNESS gate. Written before wave-4 code
lands; wave-5 implements the gate against this file, and the sprint
is GREEN only when every eval below passes. Code graders only
(pytest + scripts) — no model graders in the gate.

## Capability evals (per flow: D, A, P, M)

Each flow MUST satisfy all five (flow = one of digital, analog,
photonic, mixed-signal):

1. `good-matches-documented`: the accepted fixture, unmutated, run
   end-to-end through the engine, yields the designer's documented
   outcome (digital: testbench PASS; analog/mixed: measurements
   within stated tolerance; photonic: layout match + sim within
   documented tolerance). Grader: pytest assert on verdict +
   measurements vs fixture's documented numbers.
2. `mutation-flips-only-target`: every MUTATE-HARNESS operator for
   the flow, applied to a scratch COPY of the fixture, yields its
   declared expected verdict — and no other verdict changes.
   Grader: per-operator pytest (unmutated PASS → mutated
   expected-FAIL), operator→verdict map in docs.
3. `determinism-3x`: good + each mutation re-run 3x → identical
   verdicts (I28 results-not-bytes: verdicts/findings/measurements
   equal; native bytes may differ). Grader: repeat-run pytest.
4. `artifacts-kept`: every FAIL keeps verdict JSON + native logs +
   run record with I28 ingredient closure. Grader: artifact files
   asserted present and non-empty.
5. `no-silent-skip`: any skip/fail-loud carries a reason + issue
   ref (e.g. NGSPICE-LIVE). A bare skip fails the eval. Grader:
   grep pytest `-rs` output for reason-less skips → must be empty.

## Regression evals (every wave)

1. `suite-tools-path`: full pytest on tools PATH green
   (failures = 0; skips allowed ONLY with loud reason).
2. `suite-clean-path`: full pytest on clean PATH green.
3. `coverage-floor`: total coverage ≥ 80%.
4. `scenarios-gate`: `scripts/scenarios.py scenarios/` exit code
   matches the report (0 iff 0 failed) on both PATHs; failures
   must be environmental-with-ref (tool/PATH/store missing) —
   never code defects, never silent.
5. `tree-clean`: no committed store/fixture blobs; vendored
   fixture HEADs equal `scripts/fetch_fixtures.py` pins.

## Gate: ENGINE-CORRECTNESS (single command)

- Command: `.venv/bin/python scripts/correctness.py` (one command;
  `--flow`, `--design`, `--only-good` narrow for triage; `--report`
  overrides the stable path). Runs all four flows (good + all
  mutations), collects verdicts, writes the correctness report to
  `tmp/correctness/report.json` + `report.md` (totals, failed cases
  with artifacts under `tmp/correctness/cases/<case>/`, quarantined
  flakes with refs).
- Gate verdict: 4/4 flows green → PASS, else FAIL. Skip = FAIL
  (with reason + ref; environment-blocked flows surface as FAIL
  blocked-env, never hidden, never fake-green). Exit code 0 iff PASS.
- DEMO-PATH runs this gate as its centerpiece.

## Metrics

- Capability evals: pass^3 = 100% (3 consecutive full-gate runs
  green — the demo runs once, in front of people).
- Regression evals: pass^3 = 100% on release-critical paths.

## Run log

- 2026-10-29: definition written (pre-wave-4-landing). No runs yet.
- 2026-10-29 (wave-4b): Digital 5/5 capability PASS live
  (SERV greeting+HALT, picorv32 182/45/45 + vendor-make oracle,
  6 ops x seeds FAIL assert_fatal-only, 3x identical, artifacts
  kept, zero bare skips). Analog 1/5 live (no-silent-skip PASS;
  rest blocked-env, ngspice+store absent — oracle verbatim,
  envelope 45/45, canned-parse all PASS, quarantined under
  NGSPICE-LIVE). Regression 5/5 PASS (424/48 tools, 380/92
  clean, coverage 82.41%, scenarios-gate + tree-clean PASS).
- 2026-10-29 (VALIDATE-P): Photonic 3/5 live, 5/5 proven-or-live
  (cspdk si340 MZI ref GDS passes documented 350nm/200nm rules
  live both PATHs, klayout 0.28.16; sax 0.18.2 recorded oracle
  verbatim + canned-parse all PASS, optical live quarantined
  under B10 photonic group; 2 ops x seeds FAIL
  transmission-only, layout stays PASS, 3x identical, artifacts
  kept, zero bare skips). Regression 5/5 PASS (452/53 tools,
  408/97 clean, coverage 82.51%, scenarios-gate + tree-clean
  PASS).
- 2026-10-29 (VALIDATE-M): Mixed 3/5 live, 5/5 proven-or-live
  (sdm_rx ID/VERSION/OSR/DC-15625/PEX-1013 + bit-exact -305/-98680
  live tools PATH, iverilog 14.0; sd_top PEX 133-dev + 2048/0.4946
  vector + GATE 36.0 oracles verbatim + canned-parse all PASS,
  analog live quarantined under NGSPICE-LIVE; 7 digital + 5 analog
  ops x seeds FAIL declared-rule-only, 3x identical (digital live,
  analog file+canned), artifacts kept, zero bare skips; seam
  honest-gap, no closed-loop, closure tracked under SEAM-COSIM).
  Regression 5/5 PASS (528/52 tools, 466/114 clean, coverage
  84.12%, scenarios-gate 18/8 tools + 10/16 clean all
  environmental-with-ref, tree-clean PASS).
- 2026-10-29 (ENGINE-CORRECTNESS): gate live
  (`scripts/correctness.py`, report `tmp/correctness/`). Tools PATH:
  FAIL 1/4 truthful (digital 16/16 PASS live iverilog 14.0; analog
  0/6 blocked-env ngspice; photonic 4/8 — layout 4 PASS live
  klayout, optical 4 blocked-env sax; mixed 8/14 — digital 8 PASS
  live, analog 6 blocked-env ngspice; 28 pass / 0 fail / 16
  quarantined, all with refs, exit 1). Clean PATH: FAIL 0/4
  truthful (4 layout PASS, 40 quarantined, exit 1). Digital-only
  3x PASS identical. Broken-fixture FAILs with artifacts, exit
  codes exact. Regression 5/5 PASS (534/52 tools, 470/116 clean
  with store, coverage 84.12%, scenarios-gate 18/8 + 10/16 all
  environmental-with-ref, tree-clean PASS).
- 2026-10-29 (wave-5 landing, parent re-verified): suite 525/61
  tools, gate FAIL 1/4 truthful (28 pass / 0 fail / 16
  quarantined, exit 1) — both reproduce logged numbers exactly.
  cspdk accepted as the photonic corpus (MIT, pin 3323b17b,
  ref GDS + upstream regression confirmed) → CORPUS-P Done.
