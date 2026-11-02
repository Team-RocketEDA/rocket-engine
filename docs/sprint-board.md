# Sprint board: engine MVP

Goal: whole engine GREEN with a known-good/known-bad fixture corpus
per D/A/P/M flow, runnable through a scenario harness (mock UI track).

Rules: TDD gates on every ticket (RED→GREEN→review→commit). Agent
commits freely, never pushes. Managed by `scripts/sprint.py` —
humans may edit this file directly; keep the `- [ID] Title` format.

## Backlog

- [TEMPLATE-RUNTIME] Backlog: runtime-modifiable project templates
- [MAGIC-EXIT] Track: #531 + klayout-pex 2.5D triggers for Magic phase-out (DEFERRED until post-MVP/hackathon)

- [REMOTE-EXEC] HTTP/remote execution adapter (OFF MVP TRACK)
- [NOTEBOOK-SURFACE] Notebooks as editing surface (OFF MVP TRACK)
- [DOCKER-DEPLOY] One-container judging/deployment recipe
- [CLOUD-AUTH] Secure field for opt-in cloud account data
- [PDK-VTT] VTT 3um SOI support (verify upstream first)
- [PDK-QPDK] Quantum RF PDK (STRETCH, off MVP track)
- [PDK-PROFILE] Hexagonal PDK organization (refactor after proofs)
- [REVIEW-TAILS] Doc + surface cleanups from E2E-REREVIEW
- [PROV-DEFERRED] Provision + qualify post/off-MVP packs
- [API-V1-TOOLS-DEFERRED] Bind deferred FPGA/physics tasks (post-MVP)
- [APISPEC-DISCOVERY] api_spec misses submit-branch ops (cancel/resume/discard render unwired)
- [CANVAS-PHOTONIC-NO-HDL] Canvas v1 requires hdl even for photonic-only projects
## Ready

- [DIGITAL-FLOW] run_digital_flow via LibreLane (one click RTL to GDS)
- [TIMING-STA] Standalone run_timing via OpenSTA (top-level recheck)

- [PROV] B10 full-bundle provisioning via install.sh (phase 1+2 encoded; live --install pending on networked host)
- [BUILD-LOCAL] Repo-local toolchain default + super-repo build plan
- [MCP-CONTRACT] Conform to fuel Contract 1 + expose cancel_job
- [ENTITY-CAS] Per-entity revisions + compare-and-swap
- [BATCH-PARALLEL] Concurrent batch dispatch + per-item cancel
- [DECK-XSCHEM] Schematic to netlist to sim execution deck
- [WORKFLOW-COVERAGE] Stage tables as the tool coverage map
- [OP-GATES] Engine-side depends_on + gate-on-verdict guardrails
- [POSTLAYOUT-REAL] Translate klt PEX to vendor sim before post-layout sim
- [DRC-BANDGAP-TRIAGE] Foundry deck 740x li.5 vs fixture-clean
- [LVS-BANDGAP-TRIAGE] Netgen 185 mismatch vs fixture match
- [LVS-ESCAPE] Bulk-rename mutant escapes LVS 3/3 seeds
- [EXTRACT-GDS] run_extraction must accept GDS, not .mag-only
- [MIXED-TOP-TRIAGE] m4.5ab DRC, deck-mode cell arg, xschem top-LVS

- [LAYER-CATALOG] Technology-resolved editable layer catalog
- [LAYOUT-EDIT] Shared geometry create/edit operations for the layout editor
- [SCHEMATIC-EDIT] Hierarchical schematic authoring operations
- [SYMBOL-CELL-EDIT] Editable symbol and physical-cell libraries
- [PROCESS-LAYER-MODEL] Versioned technology semantics and export recipes
- [API-V1-CORE] Implement shared v1 runtime, discovery, references and lossless admission
- [API-V1-EDITORS] Implement typed project, schematic, symbol, cell and layout edit transactions
- [TESTBENCH-COMPONENT] Scoped SPICE, HDL and cocotb testbench blocks with editable templates
- [API-V1-TOOLS] Bind complete v1 task catalog, workflow gates and tool qualification
- [API-V1-CLIENTS] Generate and migrate MCP, stdio, HTTP and Python clients to v1
- [API-V1-CONFORMANCE] Prove v1 consumers/providers and installed workflows before deployment
- [CANVAS-CST] Canvas TOML design intent, selected authored HDL and tool settings
- [API-V1-ADAPTERS] Migrate every solver adapter to emit v1 ResultBundles
- [TOOL-OUTPUTS] Research pinned tool output shapes for v1 normalization
- [SHAPE-HARDEN] Harden the 7 weak + 2 missing tool output shapes
- [ADAPT-GROUPC] Staff group-C adapters: meow proof, devsim, meep, elmer
- [MIGRATE-STDIO-FILE] Migrate top-5 stdio parses to file channels
- [ASYNC-SUBMIT] Async submit: prompt ack + deferred handle + lifecycle events
- [PUSH-EVENTS] True push: MCP notifications + SSE + IPC stream
- [TRANSPORT-PARITY] One admission path + parity test across transports
- [IP-LIFECYCLE] IP lifecycle ops with per-PDK invariant
- [CONSOLE-LIFECYCLE] Console lifecycle + envelope convergence
- [WIRE-DECLARED-OPS] Wire or delist declared-but-unwired ops batch
- [EQY-MCY-ADAPTERS] Staff check.equivalence + check.mutation adapters
- [ANTENNA-KLAYOUT] Staff check.antenna via KLayout-DB path
- [DIGITAL-FLOW-URANIUM] Rewrite digital_flow on machine files
- [ESCAPE-HARDEN] Structured escapes + shape conformance batch
- [DUMP-PROOFS-WAVE1] Per-tool output notes + determinism tests
- [HDL-PROVIDERS] MVP provider coverage batch
- [CORE-EXEC-HARDEN] Core timeout/cancel/confinement/durability batch
- [DECOMP-CORE] Decompose composition/service, stores behind ports
- [I29-OWNER] Own verbatim PDK serving end-to-end
- [FRONTEND-13] Frontend section-13 touchpoints batch
- [PROV-UPSTREAM-RECIPE] Provision recipes verbatim from upstream READMEs
- [BWRAP-STUDY] Comparative console sandbox study
## Doing


- [FUEL-CONTRACT] Pin fuel mcp-stub to the engine contract
## Review

- [PR-RED] RED-tests PR under user review (external)

- [HTTP-LOCALHOST] Loopback trust boundary, loud and enforced
- [INVARIANT-PARTIALS] Close I01-guard, I28-replay, I12-auth gaps
- [API-V1-RESULTS] Freeze typed result/renderer contracts and task io classification
- [REFACTOR-SERVICE] Split src/project/service.py (3809 lines, over limit)
- [REFACTOR-COMPOSITION] Split src/composition.py before it hits the limit
- [REFACTOR-EXEC] Split execution mega modules
## Done

- [S1] Slice 1 GREEN (interfaces I01-I02, project I05-I07)
- [S2] Slice 2 GREEN (execution I08-I11, I22)
- [S3] Slice 3 GREEN (library I03, I04, I13)
- [S4] Slice 4 GREEN code (workflows/transports) — commit pending
- [MOCK-HARNESS] Scenario harness CLI (mock UI track)
- [CONSOLE-RED] B8 console RED (I15-I18, I23-I24)
- [CONSOLE-GREEN] Console GREEN (workers, approvals, help)
- [MCP-LIVE] MCP live-harness wiring (B9)
- [DRC-RED] DRC adapter RED (I14 fixtures, good/bad layouts)
- [HDL-SCENARIO] HDL live scenarios (run_live hdl backend + icarus wiring)
- [RUNNER-ROLLOUT] Runner rollout to drc/klayout/syntax + stdin support
- [STORAGE-REV] Amend ADR-001: co-located runs, shared pdks, kicad-style policy
- [FIXTURE-FETCH] Slice: vendor 4 fixtures + documented mutations
- [SAX-ADAPTER] Photonic sim solver via SAX
- [CORPUS-D] Digital corpus (good/bad) — blocked: user review of suggestions
- [CORPUS-A] Analog corpus (good/bad) — blocked: user review of suggestions
- [CORPUS-M] Mixed corpus scope — blocked: user picks an option
- [LAYOUT-SCHEMA] Folder schema YAML in source (versioned base template + parser)
- [PATH-GUARD] Path safety module, RED-first (unix-only, charset, traversal, containment)
- [PDK-STORE] Slice: register/verify/list PDK against user tree
- [DRC-SKY130] Slice: KLayout sky130A.lydrc live proof
- [EXTRACT-SKY130] Slice: magic extraction + Netgen LVS proof; sky130.lvs bug verdict
- [SIM-SKY130] Slice: ngspice sky130.lib proof + SERV regression
- [MUTATE-HARNESS] Systematic incorrect-design generator
- [VALIDATE-D] Digital correctness e2e (SERV, picorv32)
- [VALIDATE-A] Analog correctness e2e (bandgap)
- [VALIDATE-P] Photonic correctness e2e (cspdk + SAX)
- [VALIDATE-M] Mixed correctness e2e (sigma-delta)
- [ENGINE-CORRECTNESS] MVP gate, correct vs incorrect all flows
- [CORPUS-P] Photonic corpus (good/bad) — blocked: user review of suggestions
- [CLI-DISPATCH] One command surface (binary + batch + REPL entry)
- [WORKERS] Isolated worker substrate (I23/I24)
- [STDIO-CONSOLE] MATLAB-esque script console, stdio-only (MVP stretch)
- [DEMO-PATH] Slice: install.sh on demo machine + scenarios + runbook
- [FETCH-HARDEN] Harden fixture fetch pins + license gate
- [SCENARIO-PATH] Pin scenario gate to dev-PATH
- [PDK-DISPLAY] Preserve canonical PDK display id in store records
- [SAX-LIVE] Prove run_optical live with SAX
- [CIRCULAX-LIVE] Time-domain smoke proof
- [MEOW-LIVE] EME smoke + tidy3d-locality verdict
- [GDSFACTORY-SMOKE] Layout smoke proof
- [E2E-AUDIT] E2E routing audit (submit honesty, run_job, run_syntax)
- [DRC-GREEN] Magic/KLayout DRC adapter GREEN
- [NGSPICE-LIVE] Live ngspice/netgen proofs where the binaries exist
- [LEDGER-DURABLE] Durable attributed event log + advancing revisions
- [CRUD-API] Uniform document CRUD over the project tree
- [REWIND] Restorable project snapshots
- [PR3-MERGE] Merge fuel-mcp-fixes (PR #3) into GREEN-the-tests with consolidation
- [API-GEN] Docstring-mandated generated API contract
- [ENGINE-SETUP] Vivado-style setup surface (capability + provision)
- [B10] tests/installed + capability matrix (closed: install.sh + ENGINE-SETUP report_capabilities/catalogue)
- [ENGINE-ECS] Entity store + component CRUD + addressing + events
- [WIRE-PLACE] Wire/junction entities + connect ops + stable net IDs
- [REPLAY-SAFE] Report-not-run survivors + explicit resume + poison quarantine
- [CONSOLE-ROUTE] Console mutations route to golden recipe via admission
- [COALESCE-I33] Request coalescing per I33 (revision-pinned, force bypass)
- [PDK-CSPDK] Cornerstone PDK support (first photonic proof)
- [PDK-GF180] GF180MCU support (second CMOS node)
- [PDK-IHP] IHP SG13G2 support (BiCMOS + RF flavors)
- [PDK-UBC] SiEPIC EBeam UBC support
- [PDK-LXT] Luxelligence GF support (TFLN + gated DRC deck)
- [PDK-SKY130GF] SkyWater pip distribution (decision + profile)
- [PDK-ASAP7] ASAP7 predictive 7nm support (spike enablement first)
- [RUN-PARAMS] Explicit run.request params schema
- [BLOCK-RUNS] Block-scoped run targets (run-from-block)
- [API-GENERALIZE] Frontend protocol remainder: pool, catalogue/place_cell, raw serving
- [CELL-LINK] Symbol↔cell linkage contract (CellLink component + resolvePin)
- [SETTINGS-STORE] Engine settings store (design truth + migration mechanics)
- [CONNECT-GRAPH] Shared connectivity extraction + raw-IR emitters
- [LAYER-SERVING] Layer stackup + preset serving for viewer + 3D
- [PYTHON-EXEC] Python execution API (inline lines + project script files)
- [ASAP7-DRC-DECK] Clean-room KLayout DRC deck transcribed from the DRM
- [REPLAY] Closed decided-against: finished runs never re-execute (see REPLAY-SAFE)
- [SYNTH-YOSYS] run_synth via oss-cad-suite Yosys (RTL to mapped netlist)
- [FORMAL-SBY] run_formal via sby (bounded proof, honestly reported)
- [POSTLAYOUT] run_post_layout via ngspice on extracted netlists
- [PHOTONIC-WIRE] Wire proven photonic solvers to engine ops
- [VIEW-SYNC] run_view_sync (intended vs extracted comparison)
- [RUAMEL-DUMPER] Fresh dumpers for Engine/ProjectService YAML writes
- [GENERATE-VIEWS] Graduate gdsfactory smoke to a real generate_views op
- [SEAM-COSIM] Closed-loop mixed-signal co-simulation (VALIDATE-M follow-up)
- [E2E-REREVIEW] Invariant-by-invariant codebase re-review + e2e journeys
- [MEOW-STDOUT] Harden run_em envelope against solver chatter
- [ADAPTER-PARSE-HARDEN] Envelope parsing for sax/circulax/gdsfactory
- [FORMAL-EDGE] Vacuity guard + ifdef-aware property sites
- [SETUP-HONESTY] No false-ready probes, fresh tests, capable readiness
- [I27-GATE] Wire plan_checks/design-completion gate (I27)
- [API-V1-CONTRACT] Freeze canonical v1 API, entities, tasks and consumer artifacts
- [API-V1-PYTHON] Finish and lock Pydantic boundary generation
- [MCP-SCHEMA] Real input schemas on every MCP tool
- [I22-AMEND] Approvals at client edge (needs I22 ruling)
- [CANCEL-WIREUP] Wire cancel_job to vocabulary + submit + transports
- [ERROR-FIDELITY] Serialize fields, status map, v0-v1 code mapping
- [HTTP-HARDEN] Delete auth.py, harden HTTP handler
- [DECOMP-SLICE-1] DECOMP slice-1 GREEN (stores/drc/apig/console moves, envelope map)
