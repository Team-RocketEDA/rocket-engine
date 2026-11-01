# TESTBENCH-COMPONENT: Scoped SPICE, HDL and cocotb testbench blocks with editable templates

*Status: Ready · Design: ADR-014 · Created: 2026-11-01*

Depends: API-V1-EDITORS, CANVAS-CST. Canonical TestbenchData/BenchTarget/BenchProbe/HarnessBinding and docs/work/API-V1/editor-review.md are authoritative.

At occurrence P+[bench], legal DUTs are P+[sibling circuit instance]+descendants. One primary target plus explicit nonoverlapping additional targets; probes remain within selected DUT closures. Stable ID paths, no name/position inference; exclude self, ancestors, unrelated scopes, annotations and benches. Explicit harness binding maps include stimulus/load/power assumptions; no ambient parent circuit inclusion.

Create a saved editable source template from type (SPICE analysis incl transient, inherited HDL, cocotb), placement scope and materialized target interface; return canonical port bindings/interface digest/template provenance. Generate no guessed resets/power pins/parameters, and execute no user code while creating or describing. Renames preserve bindings; hierarchy move/delete/interface/HDL changes mark stale and block run. Regenerate to new source/diff for explicit adoption; never overwrite edits. Save reusable script/test source in project. Harness components excluded from production netlist/physical flow unless explicitly adopted into design. I28 pins testbench code, template when consumed, DUT occurrences/interfaces/bit maps, harness model conditions, source/tool/profile closure.

Prove sibling and deep descendant success; illegal ancestor/self/unrelated targets rejected; reused-definition occurrence disambiguation; overlapping DUT rejection; scoped probes; all three template kinds; source edits preserved; generated source saved; stale link refusal; unit and top harness runs; production netlist excludes stimulus.
