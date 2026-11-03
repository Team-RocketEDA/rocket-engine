Problem batch (frontend-requirements §13 engine touchpoints missing): annotate ops, ERC_TESTER + severities/pin-conflict config, net-occurrence query, buildConnectionGraph/DoWriteNetlist/UpdateNetlist, plot/export ops, ROCKET-XPROBE, geometry/cell mutation API, pin-map/cross-probe queries, resolvePin-as-query. Only run_*/LAYER_PRESET/wire subset exists; resolve_pin is a library fn + unrouted Engine method.
Expected-per: frontend-requirements.md:257-262,271-272. Audit MC-26.
Fix: implement the batch; split at staffing time. Depends on editor stack (MC-18) for geometry/cell pieces.

## Agent verdict (frontend-13 lane, 2026-11-03)

Landed, TDD RED->GREEN (owned-set failures -> green;
`tests/project` + wire suites: 171 passed, 1 skipped;
docstring guard exit 0):

- `src/project/frontend13.py` — the six touchpoints as pure
  seam functions (no Engine edits):
  1. `annotate` — idempotent ref assignment, counters continue
     past existing suffixes, unmapped symbols reported.
  2. `erc_check` — ERC_TESTER (duplicate_ref, unknown_symbol,
     unannotated, unmatched_pins, pin_conflict) with
     severities + pin-conflict config overrides.
  3. `connection_graph` — nodes/edges (contains/binds) plus
     `net_occurrences` over extracted net_pins.
  4. `write_netlist`/`update_netlist` — spice + verilog;
     net_pins required (refuses to invent connectivity);
     dangling pins emit explicit NC stubs reported under
     `unconnected`, never dropped.
  5. `xprobe` — ROCKET-XPROBE + resolvePin-as-query (symbol,
     cell, cell_pin, net + net_known flag; loud
     `net_known: False` without extraction).
  6. `plot_export` — pure SVG/JSON drawing emission.
- Binary-gated acceptances via `flow_gate("sta" |
  "librelane")`: probed (`which sta`, librelane import),
  pinned by `test_binary_gated_flows_report_blocked_never_green`
  — absent tools report loud BLOCKED-needs-host with remedy,
  never faked green. No network/docker paths exist in these
  modules (pure emission, no subprocess).
- Tests: `tests/project/test_frontend13.py`.

Deferred to the surface lane (recorded, not built):
geometry/cell mutation API (needs MC-18 editor stack),
`composition.py`/`vocabulary.py` wiring for annotate, ERC,
graph, netlist, xprobe, export, and resolvePin-as-query
names, plus I28 closure pinning of consumed symbol/cell
revisions.
