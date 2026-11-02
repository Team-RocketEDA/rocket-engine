Problem batch (frontend-requirements §13 engine touchpoints missing): annotate ops, ERC_TESTER + severities/pin-conflict config, net-occurrence query, buildConnectionGraph/DoWriteNetlist/UpdateNetlist, plot/export ops, ROCKET-XPROBE, geometry/cell mutation API, pin-map/cross-probe queries, resolvePin-as-query. Only run_*/LAYER_PRESET/wire subset exists; resolve_pin is a library fn + unrouted Engine method.
Expected-per: frontend-requirements.md:257-262,271-272. Audit MC-26.
Fix: implement the batch; split at staffing time. Depends on editor stack (MC-18) for geometry/cell pieces.
