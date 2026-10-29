# Sprint board: engine MVP

Goal: whole engine GREEN with a known-good/known-bad fixture corpus
per D/A/P/M flow, runnable through a scenario harness (mock UI track).

Rules: TDD gates on every ticket (RED→GREEN→review→commit). Agent
commits freely, never pushes. Managed by `scripts/sprint.py` —
humans may edit this file directly; keep the `- [ID] Title` format.

## Backlog

- [CORPUS-P] Photonic corpus (good/bad) — blocked: user review of suggestions
- [PROV] Provision toolchain + sky130A PDK/decks — needs deck-source decision
- [B10] install.sh + tests/installed + capability matrix

- [DEMO-PATH] Slice: install.sh on demo machine + scenarios + runbook
- [TEMPLATE-RUNTIME] Backlog: runtime-modifiable project templates
- [MAGIC-EXIT] Track: #531 + klayout-pex 2.5D triggers for Magic phase-out (DEFERRED until post-MVP/hackathon)
- [REPLAY] Backlog: first-class run replay affordance
- [VALIDATE-P] Photonic correctness e2e (cspdk + SAX)
- [VALIDATE-M] Mixed correctness e2e (sigma-delta)
- [ENGINE-CORRECTNESS] MVP gate, correct vs incorrect all flows
- [WORKERS] Isolated worker substrate (I23/I24)
- [STDIO-CONSOLE] MATLAB-esque script console, stdio-only (MVP stretch)
- [REMOTE-EXEC] HTTP/remote execution adapter (OFF MVP TRACK)
- [NOTEBOOK-SURFACE] Notebooks as editing surface (OFF MVP TRACK)
- [CLI-DISPATCH] One command surface (binary + batch + REPL entry)
- [FETCH-HARDEN] Harden fixture fetch pins + license gate
- [SCENARIO-PATH] Pin scenario gate to dev-PATH
- [PDK-DISPLAY] Preserve canonical PDK display id in store records
- [NGSPICE-LIVE] Live ngspice/netgen proofs where the binaries exist
- [DOCKER-DEPLOY] One-container judging/deployment recipe
## Ready


## Doing


- [DRC-GREEN] Magic/KLayout DRC adapter GREEN
## Review

- [PR-RED] RED-tests PR under user review (external)

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
