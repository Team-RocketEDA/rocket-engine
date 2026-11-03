# API-V1-TOOLS: Bind complete v1 task catalog, workflow gates and tool qualification

*Status: Ready · Design: ADR-014 · Created: 2026-11-01*

Depends: API-V1-CORE, CANVAS-CST, WORKFLOW-COVERAGE. Use contracts/v1/catalog/tasks.json and tools.json plus task schemas; do not expose opaque parameters or invent endpoints per binary. Binds the `mvp` delivery subset only; deferred tasks live in API-V1-TOOLS-DEFERRED with RED evidence and never gate this ticket.

Bridge existing run_* names to typed run.start tasks. Implement button workflows with parent/child DAG, required coverage resolution and truthful skipped/unsupported states. Explicit SPICE op/dc/ac/tran/noise/tf/pz/sens/disto and qualified Xyce harmonic_balance; HDL/cocotb, specific cosim synchronization, SAX/Circulax, generation/netlist, all checks/formal/equivalence/mutation, synthesis, LibreLane ASIC stages/registered steps, timing/power, extraction/postlayout, CACE sweeps/PVT/MonteCarlo, model compilation, export and measurement call points. FPGA targets and EM/modes/thermal/device binding are API-V1-TOOLS-DEFERRED (post-MVP), not this ticket. Selected task/tool registration remains distinct from installed/qualified/target-ready.

Report full stack capability records including subordinate libraries/solvers/viewers; no fake endpoint for each helper. Build/pin new Amaranth frontend/profile through installer and qualify separately; do not mark Hardcaml supported. Keep artifact-only tasks source-neutral; edits/adoption publish explicitly. Preserve independent LVS reference, process decks, model dialect/corners, convergence and tool-specific limitations. Each tool needs real external representative fixtures + regressions; current cosim sampled path must not claim general continuous feedback. Generated configs are exhaust, all consumed inputs including canvas.toml join I28.

*T-28 catalog gaps (ruling pending): simulate.cosim = mvp with providers [] (SEAM-COSIM Backlog); analyze.measurements has NO providers at all. openroad-standalone ruled OUT (LibreLane-closure only, per demotion). Do not staff cosim/measurements providers until ruled.*

## Verdict — v1-tools binding (CLIENTS wave, 2026-11-03)

Scope: owned set only — no Engine/vocabulary/service edits. Binding
proved observationally through the public Engine surface.

- Contract gate green: `scripts/check_v1_contract.py` passes (6
  methods, 33 tasks, 65 tools; 76 accepted + 24 rejected fixtures;
  generated artifacts current).
- Every mvp catalog task is provider-bound except exactly the T-28
  set, each with its recorded reason: `workflow.analog` /
  `workflow.photonic` (orchestrated, no single provider),
  `simulate.cosim` (SEAM-COSIM Backlog — not staffed until ruled),
  `analyze.measurements` (no provider at all — not staffed until
  ruled). Every other mvp task names only declared tools, and every
  tool lists its tasks back. `implement.asic` stays librelane-led
  (LibreLane-closure rule observed).
- Qualification is never faked: `Engine.capabilities()` entries for
  run_drc/run_spice/run_synth/run_lvs/run_view_sync/run_cosim/
  run_antenna are ready only with available-tool evidence (or a
  direct-serve reason); blocked/unsupported entries carry reason
  plus remedy.
- Workflow gates enforced: deferred names (`implement.fpga`,
  `simulate.em/thermal/device`, `simulate.cosim`,
  `analyze.measurements`) are refused loudly
  (`unsupported_operation`), never queued; unknown operations are
  refused on the engine and on every transport alike.
- Proof: `tests/test_v1_tools_binding.py` (6 tests) green; full
  gate via `scripts/conformance_v1.py`.
- Carry (core/composition lane): bridging `run_*` names to typed
  `run.start` v1 tasks needs the Engine-side dispatch, which this
  wave does not touch.
