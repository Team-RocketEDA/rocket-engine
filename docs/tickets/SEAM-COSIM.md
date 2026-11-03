# SEAM-COSIM: Closed-loop mixed-signal co-simulation

*Status: Backlog · Depends: VALIDATE-M, SIM-SKY130 · Size: L · Roadmap: orch-build-mvp*

## Why

VALIDATE-M proves each half of the sigma-delta separately through the
engine: the sdm_rx wrapper live via run_hdl_test (ID/VERSION/OSR,
DC OSR^3, PEX ones 0.4946, bit-exact golden model), the sd_top macro
structurally + canned (PEX 133 devices, GATE_DB 36.0 dB acceptance,
integrator-DC window, live quarantined under NGSPICE-LIVE). The seam
between them is a one-way file handoff — the digital bench consumes
the analog half's RECORDED 2048-bit vector — never a coupled sim
where a live analog tran drives the RTL in one engine run. A mixed-
signal engine that cannot close that loop is honestly partial (see
VALIDATE-M seam tests); this ticket tracks closing it, never cutting
it silently.

## What

- A coupled mixed-signal solver (new engine operation, e.g.
  run_cosim): ngspice tran on sd_top_pex.spice (or tier-1 behavioral
  deck for speed) sampled mid-period into bits, streamed live into
  sdm_rx RTL under icarus, with joint verdicts (SNDR >= 36 dB AND
  RTL ones-density/counts/golden-model all PASS).
- Determinism + artifacts per the VALIDATE-M shape (3x identical
  verdicts, verdict JSON + native logs + run record with I28
  ingredient closure for BOTH halves).
- Mutations across the seam: an analog sizing/open must flip the
  JOINT verdict (not just the analog half), and vice versa.

## Acceptance

- Good design → joint PASS with SNDR in the documented extracted
  band (38.3-40.7 dB) and RTL checks green.
- Every sdm_* / sdtop_* mutation → joint FAIL with the expected
  rule, and only it.
- 3x repeats identical; flakes quarantined with refs, never silent.
- VALIDATE-M seam tests updated to assert the closed loop (the
  honest-gap probes retire, the handoff test stays as the
  recorded-vector regression).

*Verify 2026-11-03: RUN-PARAMS migration — tier-1 engine test moved
budget into run.request (was smuggled root timeout_s, refused at
admission); engine test green, tier-1 set 15 passed / 7 skipped
(pex matrix absent on host).*
