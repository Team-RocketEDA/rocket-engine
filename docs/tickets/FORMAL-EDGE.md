# FORMAL-EDGE: Vacuity guard + ifdef-aware property sites

*Status: Ready · Depends: none · Size: S ·
Roadmap: hardening (E2E-REREVIEW FIND-06 MED + FIND-18 LOW)*

## Why

run_formal PASSes a property-free design — a vacuous
proof that contradicts the adapter's own docstring
(formal_sby:540-543, service.py:221), with no vacuity
test. Separately, _property_sites counts `define
assert( lines ifdef-blind (formal_sby:68-74), so
disabled properties inflate the count.

## What

- RED-first: vacuity detection — zero properties →
  loud bounded-vacuous verdict (or refusal), never a
  bare PASS; docstring aligned.
- Ifdef-aware site counting with a regression test
  on picorv32's guarded asserts.

## Acceptance

- Property-free design cannot PASS silently;
  guarded-assert counts correct.
- Contract + api_spec regen; full suite + gate green.
