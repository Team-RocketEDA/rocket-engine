# TOOL-OUTPUTS: Research pinned tool output shapes for v1 normalization

*Status: Ready · Design: ADR-014, API-V1-ADAPTERS · Created: 2026-11-01 · Re-scoped 2026-11-01 per docs/tool-bindings-audit.md (waves 1-3 kept tools only; deferred to wave 4)*

Depends: none (research starts immediately, per tool). Blocks:
API-V1-ADAPTERS wave staffing — no normalizer is written for a tool
whose output note is missing.

## Problem

Writing correct v1 normalizers requires knowing the FULL space of what
each pinned tool can emit: report inventory per mode, report grammars,
units, exit-state semantics, and what crashes/timeouts/truncations look
like versus clean failures. Harvesting this experimentally across input
matrices is combinatorial hell (and several tools are not even
installed here). Fixture-only mapping would silently drop shapes the
fixtures never showed.

## Method (analytical, not experimental)

Per pinned tool+version from the provision matrix, dissect the OUTPUT
side of its source (report writers, result printers, file writers, exit
paths) at the pinned revision and record, grounded in file:line:

1. Report inventory: which files/stdout sections each mode emits, and
   their stability contract (machine-readable vs human log).
2. Grammar: field layout, units, and number formats for every report
   the task's presentation kinds consume (regex/EBNF where feasible).
3. Exit states: exit codes/signals plus what partial outputs survive
   each failure mode (clean fail vs crash vs timeout vs truncated
   write) so gates can tell them apart.
4. Version sensitivity: which shapes are stable API vs incidental log
   text that may drift between releases.

Scope guard: research ONLY what the task's classified kinds + the
adapter's `parse()` consume. The note explicitly lists out-of-scope
shapes; the normalizer maps those to loud `unmapped_output` findings,
never silent drops. Golden fixtures (one good + one bad recorded
native output per tool) are harvested from real runs where installed,
else transcribed from upstream tests/docs with provenance noted.

## Extraction preference (bindings first, grammars last)

Verified 2026-11-01 (PyPI probes + upstream docs; see
docs/tool-bindings-audit.md for the full 71-tool table). Where a tool
offers a native structured readout, the dump reader uses it and NO text
grammar is researched for that shape:

1. Native Python API or queryable DB: Yosys `write_json` (pyosys lags
   the bundle and is exit()-unsafe — do NOT use), `openroad -python`
   (`import odb` for checkpoints/geometries; PyPI `openroad` is a
   squat), klayout `pya` + RDB results DBs, pyslang AST, pyGHDL
   (bundle/upstream, not stale PyPI), cocotb results.xml, SBY status
   file + DONE grammar, VCD/FST for waveforms (pywellen),
   `import librelane` where useful. Execution stays subprocess
   (isolation + SIGKILL); bindings are for READING results, not running
   tools in-process.
2. Text grammars (TOOL-OUTPUTS proper) only for the parse-only residue:
   magic/netgen Tcl-driven reports, ngspice raw ASCII + meas listings,
   xschem batch netlist print, STA report text (residue recorded for
   when opensta lands; the tool itself stays deferred).

## Deliverables

`docs/tool-outputs/<tool>-<version>.md` per tool: inventory, grammars,
exit states, version notes, fixture paths. One note per tool keeps
reviews small; waves below define staffing order.

## Waves (aligned with API-V1-ADAPTERS)

Wave 1 — checks (all kept): magic, klayout (DRC deck reports),
netgen (LVS reports), slang, connectgraph (own code: read it, don't
guess), sby (counterexample traces).
Wave 2 — sims (all kept): ngspice (all four analyses), icarus
(VCD/assertion output), sax, circulax, cosim harness, post-layout
report chain.
Wave 3 — implementation (kept only): librelane run-dir layout +
per-step reports (synth stat, DRC/LVS reports, GDS/operate outputs —
no STA rpt until the tool lands), yosys (stat JSON), gdsfactory
export inventory, xschem batch netlist print.
Wave 4 — deferred with the tools (do NOT staff): opensta reports
(STA-text grammar residue lives in the audit), xyce, openems, meep,
meow/EM, palace, thermal (elmer_fem), device (devsim), gmsh/meshwell,
scikit_fem, csxcad, femwell, gplugins, FPGA toolchain
(nextpnr/icestorm/trellis/oxide/apicula), openvaf, abc/yices/cvc4
(engine-only), cudd/trilinos/miniforge (build/bootstrap).

## Acceptance

Per tool: note exists with file:line-grounded grammars for every
consumed shape; golden good+bad fixtures recorded with provenance;
explicit out-of-scope list. A normalizer author can implement purely
from the note plus `parse()` source without running the tool.
