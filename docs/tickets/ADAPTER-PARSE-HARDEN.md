# ADAPTER-PARSE-HARDEN: Envelope parsing for sax/circulax/gdsfactory

*Status: Ready · Depends: none · Size: S ·
Roadmap: hardening (E2E-REREVIEW FIND-09, MED)*

## Why

Same latent fragility as MEOW-STDOUT in three more
adapters: sax, circulax, and gdsfactory all parse
whole-stdout strictly (sax:366), so any solver
warning breaks the envelope. Meow already bled;
these three are the same cut waiting to happen.

## What

- RED-first: marker-delimited envelope parsing in
  all three adapters (shared helper preferred over
  three copies); chatter-injection regression tests.
- Warnings preserved in logs, never fatal.

## Acceptance

- Chatter-injected drivers parse clean in all three;
  shared helper or documented reason against.
- Contract + api_spec regen; full suite + gate green.
