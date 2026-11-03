# ADR-015: Local desktop, typed results and MVP scope

*Status: accepted product/data-boundary direction, 2026-11-01; detailed schemas and conformance are being recorded before implementation inspection.*

## Requirement lock before frontend inspection

The following requirements come from the product owner's November 1 direction. They are the desired contract, not observations that the UIUX implementation already satisfies. No rendered frontend has been inspected for this decision. Subsequent source/rendered reviews must distinguish observed evidence from the requirements below.

The current presentation is Electron with React and web technologies, connected to one local headless EngineRuntime. A cloud-hosted IDE is outside the product. Local HTTP may remain an adapter; it does not imply hosting, remote users or a second runtime. Agent provider network access is a separate user-configured concern.

The UI consists of editors, chatbot, settings dialogs and data views. Use dense docked workspaces, restrained typography/spacing and domain controls. Do not add explanatory feature prose, decorative status indicators such as OPERATIONAL, blinking ornaments, large empty gutters or redundant success banners. Results render from typed data; raw verbose tool logs stream to the output terminal. DRC/LVS show actual violations and cross-probe locations; circuit simulations show plots; tables/fields/heatmaps appear only when returned data dimensions support them. No forced photonic heatmap when only a spectrum exists.

## Boundary and architecture lock

Define typed inputs and outputs between task stages as well as public requests/results/events. One canonical v1 schema bundle owns these types; generate TypeScript and Pydantic boundary models/validators from it instead of keeping separate handwritten shapes. A tool adapter converts native output to immutable dataset/result descriptors; orchestration passes typed artifact/dataset refs through declared ports. It does not parse terminal logs as the normal downstream data interface.

The engine owns axes, quantities/units, complex values, sweeps/corners, measurements, violation geometry, convergence and provenance. It supplies declarative data-view descriptors (traces/tables/matrices/fields/markers), never HTML, JavaScript, React components or explanatory page copy. The frontend owns plotting implementation/theme/docking/selection and deterministic display transforms. Unknown view/data versions produce a precise unsupported result; raw artifacts remain inspectable.

Hexagonal dependency direction is inward: transports and native/persistence adapters implement application-owned ports; use cases orchestrate typed domain data; the domain imports no transport/solver/UI framework. Pydantic is a boundary mechanism, not a dependency forced into domain entities. Keep explicit composition wiring split by feature, retaining one process owner.

## Delivery boundary

MVP deadline is **2026-11-04 Asia/Dubai**. Prioritize local runtime and editor correctness, the existing digital/analog/photonic circuit fixture paths, explicit DC/AC/transient SPICE analyses, result data contracts and native-tool evidence. Broader promised capabilities remain defined without being claimed complete.

All FPGA implementation/device programming is **off MVP**. FEM, EM/FDTD/EME/mode/device-field solvers and thermal/electrothermal work are **post MVP**; do not let them gate November 4. Preserve definitions and meaningful executable RED acceptance cases for the deferred runtime paths. Schema validity may be GREEN while deferred provider conformance remains RED. Do not fake evidence, skip/xfail the RED cases, or run missing tools just to make a deadline report appear GREEN.

## Local scripting policy

Human-authorized local Python, GDSFactory and native scripting are ordinary power-user features. The relevant consent boundary is what the owner permits the AI agent to execute. Respect the user's client-edge allow/ask/deny settings and retain attributed effects, request idempotency, project revision correctness and I28. Do not require a new dialog for every helper/import/library call or treat a local desktop as an untrusted multi-tenant hosted service. Do not silently widen a script to cloud execution. General local scripts can run in the user-approved local profile; an isolated profile can be selected, but its absence is not a product-wide scripting disable. Later changes must supersede conflicting blanket sandbox/mandatory-per-cell-approval requirements explicitly.

## Code organization

Use cohesive nested packages with one word per module/package segment; never two sibling modules sharing a first underscore-segment. Split responsibilities before adding more underscores. Put truly shared low-level code in small named modules under `src/common/` (for example `paths`, `units`, `hashes`), not a catch-all utils.py. Feature-specific helpers stay with their feature. Common code cannot import feature services or adapters. Extract repeated logic when shared semantics are real. No monster files: ~500 lines is reasonable, 1,000 is discouraged, 3,000 is a hard ceiling — never a target. Use Google-style module/class/public-callable docstrings. Record this rule in AGENTS.md and enforce it in the refactor tickets.

## Required follow-through

The canonical result/task schemas, data-view mapping, generated Python/TypeScript boundaries, RED evidence, November 4 roadmap, client skill library, agent policy amendments and sprint tickets accompany this decision. Existing v0 output remains current behavior until adapters satisfy the new contract; contract definitions are not deployment proof.
