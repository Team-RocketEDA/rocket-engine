# Codebase cleanup: ticket waves

*Source: docs/module-contract-audit.md + RULING-01..07. Rule: latest
contract wins (RULING-02); TDD RED→GREEN per ticket; commit freely,
never push. Sandbox-vs-host split: EDA binaries + PDK present in both;
source builds, fuse (LibreLane AppImage), and userns (bwrap) are
user-host-only.*

## Step 1 — Wave-0 provision and verify

Intent: make the box able to do all ticket work. Sync venv groups
(photonic, layout), pip-install + pin pyslang/pywellen/meow-sim/
vlsirtools/amaranth, verify every binary + PDK + pymeep + ElmerSolver,
record the sandbox-vs-host execution split.
Tickets: ops (unblocks all). Acceptance: probe script green; new pins
in uv.lock; digital_flow fixture runs assigned to user host.

## Step 2 — Cancel + one admission path

Intent: wire cancel_job into vocabulary + submit + all transports with
tree kill; route CLI through submit so admission/gates/pool apply
everywhere; add the cross-transport parity test.
Tickets: CANCEL-WIREUP, TRANSPORT-PARITY, CORE-EXEC-HARDEN (cancel
part). Acceptance: cancel-mid-run test passes on MCP+HTTP+CLI;
identical engine.received shape across transports.

## Step 3 — Error fidelity + HTTP hardening

Intent: fix error serialization (fields, status map incl. 403/409/
429, v0↔v1 code table, no raw-exc bodies); delete dead auth.py
(trusted-local per RULING-04); harden the HTTP handler (path, bounds,
Origin, audit log).
Tickets: ERROR-FIDELITY, HTTP-HARDEN. Acceptance: error-shape tests
per transport; loopback guard still pinned; auth.py gone.

## Step 4 — Decompose core mega-modules

Intent: behavior-preserving split of composition dispatch/queries/
serving and the project service; move the four I/O stores out of
interfaces/ behind ports; type the v0 envelopes as the v0→v1 map.
Tickets: DECOMP-CORE. Acceptance: size rule holds; no behavior change
(full suite green); envelope map table committed.

## Step 5 — Execution integrity (gates, CAS, batch)

Intent: implement depends_on/gate-on-verdict, per-entity CAS,
parallel batches with cancel, drift-checked resume, durable
findings/logs.
Tickets: OP-GATES, ENTITY-CAS, BATCH-PARALLEL, CORE-EXEC-HARDEN
(remainder). Depends on step 2. Acceptance: gate matrix tests;
CAS-conflict tests; batch cancel test; reboot keeps findings.

## Step 6 — Design intent + coverage

Intent: canvas.toml constraint sections driving validation tools as
hard rules; own verbatim PDK serving end-to-end (alias PRD names);
coverage-map decks for D/A/P/M.
Tickets: CANVAS-CST, I29-OWNER, WORKFLOW-COVERAGE. Acceptance:
constraint violation fails loudly naming the rule; serving tests;
coverage map committed.

## Step 7 — Async submit + push events

Intent: prompt-ack/deferred-handle submit mode with lifecycle events;
true push on MCP notifications + HTTP SSE + IPC stream; docstrings
honest until push lands.
Tickets: ASYNC-SUBMIT, PUSH-EVENTS. Depends on step 5. Acceptance:
submit returns handle pre-verdict; queued/started/progress/finished
observed on the wire.

## Step 8 — IP lifecycle + rocket-blocks

Intent: implement ip_search/get/register/instantiate/promote with
per-PDK registries and symbol+footprint linkage; formalize the
per-PDK invariant; link resolution to the rocket-blocks layout.
Tickets: IP-LIFECYCLE. Acceptance: CRUD roundtrip per PDK; cross-PDK
instantiate rejected; invariant in behavior-invariants.yaml.

## Step 9 — Console sandbox study

Intent: comparative study only (no code): bwrap vs raw python exec
vs prepackaged scripting contexts — adoption friction, bug risk,
hygiene, project-context needs. Record the decision + rationale.
Tickets: BWRAP-STUDY. Acceptance: decision doc committed; feeds
step 10. Note: bwrap unusable in sandbox; study on user host.

## Step 10 — Console lifecycle

Intent: implement python open/generation/reset lifecycle + envelope
convergence (or record the scoping decision); live env provides all
scriptable libs + project contexts.
Tickets: CONSOLE-LIFECYCLE. Depends on step 9. Acceptance: lifecycle
tests; no-auth trusted-local model throughout.

## Step 11 — Declared ops + frontend/editor batch

Intent: wire-or-delist every declared-but-unwired op and missing
query; implement frontend §13 touchpoints; staff the editor stack
(layer catalogue → layout/schematic → symbol/cell/process).
Tickets: WIRE-DECLARED-OPS, FRONTEND-13, LAYER-CATALOG, LAYOUT-EDIT,
SCHEMATIC-EDIT, SYMBOL-CELL-EDIT, PROCESS-LAYER-MODEL,
TESTBENCH-COMPONENT. Acceptance: zero advertised-but-failing tools;
editor roundtrips green.

## Step 12 — File channels + blessed escapes

Intent: migrate the top-5 stdio parses to file channels
byte-identically; switch synth/syntax/hdl_sim/cosim to their blessed
escapes (write_json, pyslang/AST, pywellen VCD); pin drc_kl bbox;
conform violation/measurement shapes.
Tickets: MIGRATE-STDIO-FILE, ESCAPE-HARDEN. Acceptance: golden
fixtures byte-identical; file-channel tests; shape-conformance tests.

## Step 13 — Dump proofs wave 1

Intent: per kept tool: docs/tool-outputs/<tool>-<version>.md with
recorded native outputs, test_<name>_results.py determinism tests,
README dump-shape sections. Blocks all normalizers.
Tickets: DUMP-PROOFS-WAVE1. Depends on step 12. Acceptance: every
kept tool has note + tests + README section; suite green.

## Step 14 — digital_flow uranium rewrite

Intent: behavior-preserving rewrite of digital_flow readout onto
LibreLane run-dir machine files (state_out.json, metrics.csv, views);
delete generic regex/keyword verdicts. Fixture runs on user host
(AppImage needs fuse).
Tickets: DIGITAL-FLOW-URANIUM. Depends on step 13 method. Acceptance:
same verdicts on golden runs; zero unpinned scraping; fixtures
recorded from real runs.

## Step 15 — Formal + antenna providers

Intent: staff check.equivalence (eqy), check.mutation (mcy), and
check.antenna (KLayout-DB path) with dump-first acceptance + good/bad
fixtures.
Tickets: EQY-MCY-ADAPTERS, ANTENNA-KLAYOUT. Acceptance: three tasks
covered; fixtures recorded; no openroad-standalone anywhere.

## Step 16 — Sim + utility providers

Intent: staff simulate.hdl verilator/ghdl, generate/export via
xschem+vlsirtools, characterize via cace (re-verified at pin),
lvs-klayout + layout_xor, ghdl/amaranth synth, meow/devsim/meep/elmer
dumps, xschem decks. Split per provider at staffing.
Tickets: HDL-PROVIDERS, ADAPT-GROUPC, DECK-XSCHEM. Acceptance: per
provider dumps + fixtures; catalog kfactory entries re-scoped.

## Step 17 — Shape hardening research

Intent: research-only close-out of weak shapes: openroad STA writers,
cace at pin, openvaf OSDI verdict, xschem EBNF + re-pin, slang diags
at bundle, xyce extra formats, cocotb/gmsh shapes. Grammar + fixtures
or explicit scope-out each.
Tickets: SHAPE-HARDEN. Acceptance: audit rows updated; no adapter
staffed on prose.

## Step 18 — Provision from upstream READMEs

Intent: rewrite install_opensta/install_xyce/install_openems (+deps)
to copy upstream README recipes verbatim, preserving nonlinear order
(cudd-then-opensta etc.); record doc URLs + revisions. Unparks the
trio; user confirms with manual builds.
Tickets: PROV-UPSTREAM-RECIPE. Runs on user host (build toolchain).
Acceptance: --install reproduces README builds; trio unparks.

## Step 19 — Proof wave

Intent: restaff TIMING-STA post-provision; real-deck postlayout
proofs; DRC/LVS/bandgap/mixed triage tickets; demo-path hardening;
ngspice live re-proof.
Tickets: TIMING-STA, POSTLAYOUT-REAL, DRC-TRIAGE, LVS-ESCAPE,
MIXED-TOP-TRIAGE, BANDGAP-DRC-LVS, DEMO-PATH, NGSPICE-LIVE.
Depends on steps 13, 18. Acceptance: proofs green on fixtures;
demo path runs end to end.

## Step 20 — Conformance gate

Intent: verify the v1 conformance gate passes (every normalizer
against recorded fixtures for all MVP tasks, every bundle validates).
Gate only; failures file new tickets, never waived here.
Tickets: API-V1-CONFORMANCE. Depends on all above. Manual run: the
conformance suite has no scoped slash command; run it directly.
