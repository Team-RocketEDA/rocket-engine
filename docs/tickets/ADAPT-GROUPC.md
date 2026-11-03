Why: audit group C (re-triage 2026-11-02) is provisioned-but-unstaffed: implemented physics with bindings/file channels, blocked only on adapters + proof. Staff cheapest-first per TOOL-OUTPUTS preference (bindings > structured files > deterministic text); execution stays subprocess, bindings for READING.

Order:
1. meow (locked 0.15.0 + adapter exists): dump-first proofs (NOT task bindings — binding gate explicit per X-15; simulate.em stays post_mvp per RULING-02 until ruled otherwise).
2. devsim (2.11.2 installed): driver calls get_contact_current/get_*_model_values/solve(info=True) + write_devices files, dump JSON.
3. meep (pymeep 1.35.0 installed): subprocess driver, in-API flux/DFT/Harminv + HDF5 via h5py.
4. elmer_fem (ambient PPA): SaveScalars JSON/CSV + VTU via pyvista.

Grammars: docs/tools/devsim.md, meep.md, elmerfem.md (meow via adapter + envelope). Acceptance per adapter: coherent deterministic dump + golden good/bad fixtures + documented shape (NOT strict ResultBundle yet — that is API-V1-CONFORMANCE).

## Verdict (adapt lane, 2026-11-03) — devsim/meep/elmer Done, gated

`src/adapters/devsim/` (run_tcad, driver JSON dump: currents,
potentials, solve(info=True)), `src/adapters/meep/` (run_optical,
in-API dump first, S1 telemetry fallback, HDF5 as artifacts),
`src/adapters/elmer/` (run_thermal, SaveScalars JSON first, NS/SS
fallback, VTU as artifacts) all land dump-first with good/bad
fixtures pinned in `tests/adapters/test_devsim*.py`,
`test_meep*.py`, `test_elmer*.py` (RED 76 failed total across the
lane, GREEN 75 passed / 2 skipped). devsim imports live in the
venv; meep is absent (BLOCKED-needs-host pinned by test);
ElmerSolver 26.2 present. Notes `docs/tool-outputs/devsim-2.11.2.md`,
`meep-1.35.0.md`, `elmer-ambient.md`. Wiring seam
(vocabulary/composition) recorded, untouched.
