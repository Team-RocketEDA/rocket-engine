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
