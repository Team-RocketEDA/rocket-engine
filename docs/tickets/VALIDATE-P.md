# VALIDATE-P: Photonic correctness end-to-end (cspdk + SAX)

*Status: Backlog · Depends: SAX-ADAPTER, MUTATE-HARNESS · Size: M · Roadmap: orch-build-mvp*

## Why

P is the only flow with zero engine coverage today — no solver, no
fixtures, no proofs. The fix is a two-source truth: cspdk
(Cornerstone PDK, MIT, regression-tested with in-repo reference
GDS) supplies a reference MZI/ring circuit as layout truth, and
SAX (Apache-2.0, our decided photonic sim) supplies documented
transmission models as behavior truth. Validating the engine
against both closes the D/A/P/M square for the MVP criterion.

## What

- Fetch cspdk reference MZI/ring (verify reference GDS + tests on
  fetch; fallback: SAX notebook MZI as pure-circuit target).
- Layout side: GDS through engine checks vs reference; behavior
  side: SAX sim through SAX-ADAPTER vs documented transmission.
- Apply MUTATE-HARNESS photonic operators (geometry + circuit
  mistune); recheck end-to-end.

## Acceptance (e2e patterns: artifacts, determinism, quarantine)

- Good circuit → layout matches reference + sim within documented
  tolerance. Every mutation → expected FAIL, and only it.
- Failure artifacts kept; 3x repeats identical; flakes quarantined
  with issue refs, never silently skipped.
- SiEPIC-Tools explicitly NOT used (license unclear, stale).
