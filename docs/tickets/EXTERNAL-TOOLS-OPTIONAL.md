# EXTERNAL-TOOLS-OPTIONAL: Engine runs degraded and loud without any external tool

*Status: Backlog · Filed: 2026-11-04 · Source: setup-surface review 2026-11-04*

Principle (not Xyce-specific): every externally-sourced tool with an
adapter — anything outside Python, i.e. native binaries, source
builds, AppImages, conda envs, PDK trees — is OPTIONAL. The engine
must run degraded and loudly with any or all of them absent: Xyce,
openEMS, openSTA, Magic, KLayout, the LibreLane closure, Elmer, the
pymeep env, every one. A missing Python library, by contrast, is a
hard failure (see [PYTHON-PROVISION-GUARANTEE](PYTHON-PROVISION-GUARANTEE.md)).

This generalizes and replaces XYCE-OPTIONAL (removed): Xyce is one
instance, with ngspice as its working fallback — not a special case.

## Scope

- Enumerate every solver adapter bound to an external (non-Python)
  dependency. Each must, with its tool absent: return typed
  `unavailable` (never error, never silent skip) with the provision
  remedy attached; keep the engine importable and all unrelated ops
  green (no import-time tool binding — lazy resolve at submit).
- `get_capabilities` marks tool-gated ops `blocked` (missing +
  remedy) vs `unsupported` distinctly, per tool, per PDK.
- Degradation matrix test: full MVP suite green with ALL external
  tools absent (python-only engine), plus spot checks with each tool
  individually absent asserting the unavailable+remedy shape.

## Acceptance

- Python-only host: suite green, capabilities honest for every
  external tool, zero engine breakage, zero silent skips.
- No adapter imports or requires its binary at module load:
  dependency direction stays inward (adapters → `interfaces/`
  ports; `execution/` → ports only), with all tool wiring in the
  composition root so a missing tool yields a port with no working
  adapter — i.e. typed `unavailable`, never an import or submit
  exception.
- Port-contract tests cover the absent-tool path per adapter
  (unavailable + remedy shape), alongside fake-port unit tests for
  the submit path.
