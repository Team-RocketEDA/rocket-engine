# POSTLAYOUT-REAL: Translate klt PEX to vendor sim before post-layout sim

*Status: Ready · Depends: none · Size: M ·
Roadmap: hardening (E2E-REREVIEW FIND-02, HIGH)*

## Why

run_post_layout sims klt generic device classes as-is,
so real extracted PEX is unsimmable (can't-find-model).
Synthetic deltas pass; the real bandgap leg fails. The
engine must translate klt extraction output to vendor
models (or refuse loudly naming the gap) before
claiming post-layout coverage.

## What

- RED-first: klt→vendor model translation on the
  postlayout path (adapter.py:533-534), or a loud
  unsupported refusal when untranslatable — never a
  silent sim_fail.
- Bandgap real-PEX leg green or loudly refused.

## Acceptance

- Real extracted netlist sims with pre/post delta, or
  a named blocker; no silent sim_fail.
- Contract + api_spec regen; full suite + gate green.

## Verdict (adapt lane, 2026-11-03) — translate-or-refuse Done

`src/adapters/postlayout/translate.py` lands klt→vendor mapping
(known classes translate with provenance rows; unknown classes
raise `unsupported_operation` naming the device and the vendor
gap — loud refusal, never silent sim_fail). Tests
`tests/adapters/test_postlayout_translate.py` pin map, refusal,
and detection. Note `docs/tool-outputs/postlayout-klt.md`. The
sim-path call site (adapter.py staging) belongs to the owning
surface and is untouched here; the bandgap real-PEX leg needs a
live gate-host run to go green or be loudly refused.
