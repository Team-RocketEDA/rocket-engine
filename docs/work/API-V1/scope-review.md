# November 4 scope and roadmap review

Date: 2026-11-01, Asia/Dubai. This review applies ECC Product Capability and Hexagonal Architecture to the user's explicit delivery constraints. It inspected engine tickets, current Python adapter/source boundaries and existing product documents. It did not inspect the rendered frontend or claim that UIUX matches the desired contract.

## Capability and fixed constraints

The product is a local Electron/React EDA workbench with a headless engine that emits typed datasets, findings and evidence. The frontend owns rendering; the output terminal consumes verbose logs. Shared transport/task contracts and generated Pydantic/TypeScript models must precede independent provider and client refactors. Native results should flow through typed stage ports, not console text or Python plotting-widget objects.

All FPGA work is off MVP. FEM, EM/FDTD/EME, optical modes/fields, thermal/electrothermal and semiconductor device solvers are post MVP. These capabilities stay discoverable and specified; delivery status must not masquerade as installation or qualification. A package may be installed while its product feature remains deferred. A prior smoke can remain historical evidence without becoming a November 4 requirement.

The existing digital, analog, compact photonic and mixed-signal circuit fixture lanes stay on the MVP path. Required explicit SPICE modes are operating point, DC sweep, AC and transient, selected under `run` / `simulate.spice`. A wavelength spectrum should render as spectral traces; only actual multi-axis/matrix/field data merits a heatmap. Human-authorized local scripting remains a power-user capability; security work focuses on the owner's agent execution policy and project/evidence integrity rather than a hosted multi-tenant threat model.

## Existing ticket conflicts

The board was read using `.venv/bin/python scripts/sprint.py list` and `show` for API-V1-CORE, API-V1-TOOLS, API-V1-CLIENTS, API-V1-CONFORMANCE, PROV, PHOTONIC-WIRE, GENERATE-VIEWS, TESTBENCH-COMPONENT, DIGITAL-FLOW and DECK-XSCHEM.

1. **PROV has a release-blocking full-matrix promise.** It says every pack must be provisioned, including nextpnr, Meep/openEMS/Palace/Gmsh, Elmer and DEVSIM, before the MVP B10 ticket can close. Amend it to the selected MVP tool closure and split the deferred packs into separate tickets. Do not delete its historical provisioning evidence.
2. **API-V1-TOOLS currently mixes all delivery tracks.** It puts FPGA, EM/modes/thermal/device qualification in one Ready acceptance body. Split implementation acceptance by delivery track; keep their typed task descriptions in the common registry.
3. **The selected tech stack mixes planned inventory with release inclusion.** Its broad future packages should remain documented with delivery metadata; the November 4 installer gate covers the MVP subset. Shared numerical libraries are not globally deferred merely because a post-MVP physics task also uses them.
4. **PHOTONIC-WIRE and MEOW-LIVE are Done in the board while bodies use older statuses.** Retain the actual recorded smoke/wiring history. SAX/Circulax compact-model circuit response remains MVP; MEOW EME is deferred by the new user direction.
5. **Remote/cloud/container tickets need the local desktop ruling.** HTTP transport support does not imply a cloud-hosted IDE. Remote execution and cloud credentials cannot be required to run the engine's ordinary local workflows; optional agent provider connectivity remains a separate configuration.
6. **Schema versus provider state is already different.** The v1 contract is designed and generated; current HTTP still speaks the earlier `project_id/operation/arguments` envelope. Do not mark providers GREEN just because schema fixtures validate.

## Proposed delivery metadata

Use `delivery: mvp | post_mvp | off_mvp` in task discovery and the catalog. This answers product scope; keep it distinct from availability, installation and qualification. The canonical registry is the authority, not this note.

| Task/surface | Delivery | Meaning |
|---|---|---|
| `implement.fpga`, architecture databases, bitstream/programming work | `off_mvp` | No November 4 implementation/provisioning dependency. Programming is not an implicit extension of bitstream export. |
| `simulate.em` and field/mode/FDTD/FEM/EME tools | `post_mvp` | Data/study contract and explicit RED provider acceptance retained. |
| `simulate.thermal`, thermal/electrothermal | `post_mvp` | Same typed axes/fields/provenance conventions; native execution later. |
| `simulate.device`, device-field/semiconductor equations | `post_mvp` | Do not require DEVSIM qualification for circuit simulation MVP. |
| `simulate.spice` with `op/dc/ac/tran` | `mvp` | Existing analog work remains first-class; add normalized datasets rather than separate RPC verbs. Other modes are independently qualified. |
| `simulate.optical` with supported SAX/Circulax circuit modes | `mvp` | Compact circuit data only; no inferred spatial field result. |
| `synthesize.hdl`, HDL simulation/tests and ASIC implementation | `mvp` on qualified source/PDK/profile paths | HDL authoring and digital circuit verification are independent of FPGA delivery. |
| Domain-neutral dataset schemas/view descriptors | `mvp` contract infrastructure | Can describe future fields/meshes without shipping a field solver. |

For a deferred task the MVP provider should describe its declared schemas and delivery reason, then return an explicit typed pre-admission `capability_unavailable` with `admitted:false` rather than launching native work. This is a release-profile rule, not a permanent ban on the future feature. Promotion requires a deliberate scope/qualification change.

## Implementation contract and handoff

The [roadmap](../../roadmap.md) orders six slices: canonical data types; shared core/edits; native result normalization; editor/presentation consumers; whole local workflows; installed release evidence. Type generation and fixture contracts unlock parallel frontend/provider work. Actual rendering and actual native provider tests remain separate acceptance evidence.

Ports should describe source/result/dataset/event capabilities. Native tool adapters consume typed snapshots/study descriptors and return normalized immutable datasets plus diagnostic/native refs. Use cases validate declared stage bindings and I28 without depending on ngspice, JSX, Matplotlib or transport request objects. Pydantic validates boundary DTOs; domain data remains framework-independent.

No product ambiguity blocks recording this scope. Native tool availability and unfinished v1 integration remain implementation blockers with explicit tickets. The roadmap is ready to drive implementation; it is not a deployment-readiness verdict.
