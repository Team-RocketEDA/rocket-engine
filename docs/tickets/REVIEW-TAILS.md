# REVIEW-TAILS: Doc + surface cleanups from E2E-REREVIEW

*Status: Backlog · Depends: none · Size: S ·
Roadmap: hardening (E2E-REREVIEW FIND-19 + FIND-20 +
FIND-22 + FIND-23 + FIND-24 + FIND-25, all LOW)*

## Why

Six low-severity review tails, batched: evaluate()
drops the exit code its docstring claims
(service.py:190-224); no circuit-mistune fail
scenario (sax_mzi_fail.yaml:5); Engine.run docstring
contradicts I09 (composition.py:2426 vs :2389);
api_search/api_info/api_help unwired or undescoped
(I18, vocabulary.py:24); host-execution opt-in
surface unnamed (I19, mcp:23); no offline
clean-account install proof (I20, test_packaging.py).

## What (when scheduled)

- Fix/doc/test each tail; I19/I20 scoped to the
  deferred-auth/post-hackathon decisions where they
  collide (loud scope, not silent skip).

## Acceptance

- All six closed or explicitly scoped with reasons.
