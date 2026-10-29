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

- One command runs all four flows (good + all mutations),
  collects verdicts, writes the correctness report (totals, failed
  cases with artifacts, quarantined flakes with refs).
- Gate verdict: 4/4 flows green → PASS, else FAIL. Skip = FAIL
  (with reason + ref). Exit code 0 iff PASS.
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
