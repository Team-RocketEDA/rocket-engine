Problem: MVP task check.antenna has ZERO adapter. Catalog names openroad/klayout providers, but openroad is demoted to LibreLane-internal (no standalone adapter will ever be staffed).
Expected-per: tasks.json (mvp). Audit MC-07.
Fix: staff check.antenna via a KLayout-DB-backed path (drc_kl family or new adapter). Dump-first + fixtures. Do NOT staff openroad-standalone (ruled out per demotion; see X-13).

## Verdict (Wave-2, 2026-11-03) — Ready, Engine wiring to Wave-3

KLayout-DB antenna path complete (run_antenna OPERATION_ANTENNA,
island metal/gate ratio, 7 hermetic DB tests pinned).
Engine wiring (vocabulary/composition/MCP + regen) carries to the
Wave-3 surface lane.
