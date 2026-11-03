# TESTBENCH-COMPONENT: Scoped SPICE, HDL and cocotb testbench blocks with editable templates

*Status: Ready · Design: ADR-014 · Created: 2026-11-01*

Depends: API-V1-EDITORS, CANVAS-CST. Canonical TestbenchData/BenchTarget/BenchProbe/HarnessBinding and docs/work/API-V1/editor-review.md are authoritative.

At occurrence P+[bench], legal DUTs are P+[sibling circuit instance]+descendants. One primary target plus explicit nonoverlapping additional targets; probes remain within selected DUT closures. Stable ID paths, no name/position inference; exclude self, ancestors, unrelated scopes, annotations and benches. Explicit harness binding maps include stimulus/load/power assumptions; no ambient parent circuit inclusion.

Create a saved editable source template from type (SPICE analysis incl transient, inherited HDL, cocotb), placement scope and materialized target interface; return canonical port bindings/interface digest/template provenance. Generate no guessed resets/power pins/parameters, and execute no user code while creating or describing. Renames preserve bindings; hierarchy move/delete/interface/HDL changes mark stale and block run. Regenerate to new source/diff for explicit adoption; never overwrite edits. Save reusable script/test source in project. Harness components excluded from production netlist/physical flow unless explicitly adopted into design. I28 pins testbench code, template when consumed, DUT occurrences/interfaces/bit maps, harness model conditions, source/tool/profile closure.

Prove sibling and deep descendant success; illegal ancestor/self/unrelated targets rejected; reused-definition occurrence disambiguation; overlapping DUT rejection; scoped probes; all three template kinds; source edits preserved; generated source saved; stale link refusal; unit and top harness runs; production netlist excludes stimulus.

## Verdict (Wave-3, 2026-11-03) — blocks + templates landed

`src/project/testbench/` (new): `blocks.py` scopes DUT targets
over the ENGINE-ECS entity seam (primary instance plus explicit
nonoverlapping additional targets; probes inside the DUT
closure; stable entity ids disambiguate reused definitions —
never names/positions), pins DUT/interface/template digests,
marks hierarchy/interface drift stale and refuses the run
(`stale_link`), regenerates to an explicit-adoption candidate
without touching edited live source, saves generated source as
`testbench/<name>.<ext>`, and filters harness instances from
production net pins unless adopted. `templates.py` renders the
three kinds (SPICE incl. transient, inherited HDL, cocotb) from
the materialized interface plus the explicit harness binding —
no guessed resets/power pins/parameters — with provenance
(kind, version, digest). Simulator runs stay binary-gated:
`probe_simulator` reports ready or BLOCKED-needs-host with a
remedy (ngspice/icarus/cocotb probed, never faked green).

Wired through `create_testbench`/`regenerate_testbench`
(submit) and `list_testbenches`/`describe_testbench` (query)
with I28 pins; harness exclusion enforced in `netlist_report`.
Pinned by `tests/test_testbench_blocks.py` (15 passed:
sibling/deep-descendant success, ancestor/unrelated/overlap/
out-of-closure refusals, disambiguation, edit preservation,
saved source, stale refusal, exclusion, loud BLOCKED gates).
