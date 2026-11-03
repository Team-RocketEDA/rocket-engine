"""Process inventory as data: stage tables plus readiness planning.

Each stage carries its PRD identifier, a short step summary, the
evidence it must leave, its applicability condition, whether it gates
a "fully verified" claim, and the engine operations that execute it.
Full prose lives in the PRD; this module is the machine-readable
projection the planner and UI consume.

Limitation (v1): every planned stage is marked required. Evaluating
the prose `when` conditions into true applicability is a later slice;
until then a missing backend blocks completion claims rather than
silently narrowing scope.
"""

_SCRIPTED = frozenset({"project scripting", "get_capabilities", "ip_instantiate"})

STAGES = {
    "digital": [
        {"id": "D01", "step": "Define logic, clocks, interfaces, limits.", "evidence": "Specification and verification plan.", "when": "always", "required": True, "entrypoints": ["project scripting"]},
        {"id": "D02", "step": "Select and lock PDK, cells, memories, tools, HDL features.", "evidence": "Pinned libraries and capability report.", "when": "always", "required": True, "entrypoints": ["get_capabilities"]},
        {"id": "D03", "step": "Write or import RTL; resolve files, parameters, IP.", "evidence": "Saved RTL revision and dependency closure.", "when": "always", "required": True, "entrypoints": ["ip_instantiate"]},
        {"id": "D04", "step": "Parse RTL; syntax, widths, latches, lint.", "evidence": "Located diagnostics and waiver reasons.", "when": "always", "required": True, "entrypoints": ["run_syntax"]},
        {"id": "D05", "step": "Elaborate and compile design with testbench.", "evidence": "Build result and executable simulation.", "when": "always", "required": True, "entrypoints": ["run_hdl_test"]},
        {"id": "D06", "step": "Run functional tests incl. boundaries and resets.", "evidence": "Assertions, seeds, cycles, waveforms.", "when": "always", "required": True, "entrypoints": ["run_hdl_test"]},
        {"id": "D07", "step": "Review coverage; add tests for gaps.", "evidence": "Required scenario and coverage report.", "when": "always", "required": True, "entrypoints": ["run_hdl_test"]},
        {"id": "D08", "step": "Check clock/reset crossings and formal properties.", "evidence": "Crossing findings, proof scope, counterexamples.", "when": "multiple clock/reset domains or formal requirements", "required": True, "entrypoints": ["run_formal"]},
        {"id": "D09", "step": "Write physical and timing constraints from the spec.", "evidence": "Clocks, IO delays, die and placement limits.", "when": "always", "required": True, "entrypoints": ["project scripting"]},
        {"id": "D10", "step": "Plan power domains, macros, manufacturing test.", "evidence": "Supply connections and test/scan plan.", "when": "multiple supplies, test insertion, or hard macros", "required": True, "entrypoints": ["project scripting"]},
        {"id": "D11", "step": "Start the LibreLane flow; inspect enabled stages.", "evidence": "Exact flow, configuration, stage list.", "when": "always", "required": True, "entrypoints": ["run_digital_flow"]},
        {"id": "D12", "step": "Recheck lint; synthesize to standard cells.", "evidence": "Mapped netlist, cell counts, area.", "when": "always", "required": True, "entrypoints": ["run_digital_flow"]},
        {"id": "D13", "step": "Pre-placement constraint and timing check.", "evidence": "Constraint coverage and timing estimates.", "when": "always", "required": True, "entrypoints": ["run_digital_flow"]},
        {"id": "D14", "step": "Floorplan; place hard macros.", "evidence": "Die geometry, macro sites, halos.", "when": "always", "required": True, "entrypoints": ["run_digital_flow"]},
        {"id": "D15", "step": "Power connections, taps, power grid.", "evidence": "Supply graph and power-grid checks.", "when": "always", "required": True, "entrypoints": ["run_digital_flow"]},
        {"id": "D16", "step": "Place cells and IO; repair timing/electrical.", "evidence": "Legal placement, congestion, timing.", "when": "always", "required": True, "entrypoints": ["run_digital_flow"]},
        {"id": "D17", "step": "Build and balance the clock tree.", "evidence": "Clock network, skew, timing findings.", "when": "clocked design with CTS enabled", "required": True, "entrypoints": ["run_digital_flow"]},
        {"id": "D18", "step": "Global routing; repair antenna/timing.", "evidence": "Global routes and congestion reports.", "when": "always", "required": True, "entrypoints": ["run_digital_flow"]},
        {"id": "D19", "step": "Detail routing; check violations and opens.", "evidence": "Routed database and diagnostics.", "when": "always", "required": True, "entrypoints": ["run_digital_flow"]},
        {"id": "D20", "step": "Filler cells and density features.", "evidence": "Added geometry and density coverage.", "when": "process requires", "required": True, "entrypoints": ["run_digital_flow"]},
        {"id": "D21", "step": "Extract interconnect R/C from routed database.", "evidence": "SPEF, corner, coverage.", "when": "parasitic-aware timing required", "required": True, "entrypoints": ["run_digital_flow", "run_extraction"]},
        {"id": "D22", "step": "Multi-corner STA with extracted parasitics.", "evidence": "Setup/hold, paths, limits.", "when": "always", "required": True, "entrypoints": ["run_digital_flow", "run_timing"]},
        {"id": "D23", "step": "Power and IR-drop analysis.", "evidence": "Power assumptions, hotspots, limits.", "when": "required by power plan", "required": True, "entrypoints": ["run_digital_flow"]},
        {"id": "D24", "step": "Stream GDS/LEF and model views.", "evidence": "GDS, LEF, netlists, timing models.", "when": "always", "required": True, "entrypoints": ["run_digital_flow", "generate_views"]},
        {"id": "D25", "step": "Final foundry-deck DRC (plus XOR where configured).", "evidence": "Geometry-difference and rule reports.", "when": "DRC required for qualification", "required": True, "entrypoints": ["run_drc"]},
        {"id": "D26", "step": "Extract layout devices; LVS vs reference.", "evidence": "Extracted circuit and LVS report.", "when": "electrical verification required", "required": True, "entrypoints": ["run_lvs"]},
        {"id": "D27", "step": "Equivalence and final manufacturing gates.", "evidence": "Per-stage acceptance and summary.", "when": "required delivery gates", "required": True, "entrypoints": ["run_digital_flow", "run_formal"]},
        {"id": "D28", "step": "Gate-level timing or interface SPICE sim.", "evidence": "Reset/X/timing scenarios.", "when": "design-specific requirements", "required": True, "entrypoints": ["run_hdl_test", "run_post_layout"]},
        {"id": "D29", "step": "Chip-level density/antenna/ESD/pad rules.", "evidence": "Rule coverage and blockers.", "when": "chip-level delivery", "required": True, "entrypoints": ["run_drc", "run_lvs"]},
        {"id": "D30", "step": "Repeat affected stages; freeze delivery.", "evidence": "Pinned bundle and unresolved limits.", "when": "always", "required": True, "entrypoints": ["project scripting"]},
    ],
    "analog": [
        {"id": "A01", "step": "Define gain, bandwidth, noise, supply, load, power.", "evidence": "Measurable acceptance criteria.", "when": "always", "required": True, "entrypoints": ["project scripting"]},
        {"id": "A02", "step": "Select PDK devices, corners, simulator, decks.", "evidence": "Pinned device/model/deck references.", "when": "always", "required": True, "entrypoints": ["get_capabilities"]},
        {"id": "A03", "step": "Create schematic/netlist bound to real devices.", "evidence": "Sizes, pin order, hierarchy, reference netlist.", "when": "always", "required": True, "entrypoints": ["ip_instantiate"]},
        {"id": "A04", "step": "Check syntax, connectivity, ERC.", "evidence": "Located syntax/connectivity/ERC findings.", "when": "always", "required": True, "entrypoints": ["run_syntax", "run_connectivity", "run_erc"]},
        {"id": "A05", "step": "Build testbenches with sources, loads, limits.", "evidence": "Versioned testbenches and measures.", "when": "always", "required": True, "entrypoints": ["project scripting"]},
        {"id": "A06", "step": "DC operating point and sweeps.", "evidence": "Op points, regions, convergence.", "when": "applicable modes", "required": True, "entrypoints": ["run_spice"]},
        {"id": "A07", "step": "Frequency response and loop stability.", "evidence": "Gain, bandwidth, phase margin.", "when": "applicable AC requirements", "required": True, "entrypoints": ["run_spice"]},
        {"id": "A08", "step": "Transient and startup checks.", "evidence": "Settling, slew, overshoot, startup.", "when": "applicable transient requirements", "required": True, "entrypoints": ["run_spice"]},
        {"id": "A09", "step": "Noise, distortion, periodic/RF analyses.", "evidence": "Noise/distortion figures and limits.", "when": "required by spec", "required": True, "entrypoints": ["run_spice"]},
        {"id": "A10", "step": "PVT corners and mismatch/Monte Carlo.", "evidence": "Worst corners, stats, yield estimate.", "when": "robustness plan requires", "required": True, "entrypoints": ["run_spice"]},
        {"id": "A11", "step": "Resize/retune to pre-layout targets.", "evidence": "Accepted revision and measurements.", "when": "always", "required": True, "entrypoints": ["run_spice"]},
        {"id": "A12", "step": "Set matching, symmetry, floorplan constraints.", "evidence": "Explicit analog physical constraints.", "when": "always", "required": True, "entrypoints": ["project scripting"]},
        {"id": "A13", "step": "Place PDK devices, wells, guards, dummies.", "evidence": "Device layout and pin mapping.", "when": "always", "required": True, "entrypoints": ["generate_views"]},
        {"id": "A14", "step": "Route signals, supplies, shields; fill.", "evidence": "Routed geometry and supply graph.", "when": "always", "required": True, "entrypoints": ["generate_views"]},
        {"id": "A15", "step": "Incremental DRC during layout.", "evidence": "Rule findings linked to geometry.", "when": "physical qualification", "required": True, "entrypoints": ["run_drc"]},
        {"id": "A16", "step": "LVS vs independent schematic netlist.", "evidence": "Device identities, nets, pin maps.", "when": "physical qualification", "required": True, "entrypoints": ["run_lvs"]},
        {"id": "A17", "step": "Extract layout parasitics.", "evidence": "PEX netlist, coverage, settings.", "when": "physical performance qualification", "required": True, "entrypoints": ["run_extraction"]},
        {"id": "A18", "step": "Build post-layout testbench on extraction.", "evidence": "Pin order and conditions preserved.", "when": "after qualified extraction", "required": True, "entrypoints": ["project scripting"]},
        {"id": "A19", "step": "Repeat required sims with parasitics.", "evidence": "Post-layout results and deltas.", "when": "supported analyses", "required": True, "entrypoints": ["run_post_layout"]},
        {"id": "A20", "step": "Coupling, IR drop, thermal checks.", "evidence": "Hotspots, margins.", "when": "sensitive circuits", "required": True, "entrypoints": ["run_em", "run_thermal"]},
        {"id": "A21", "step": "Repair layout/sizing; rerun affected gates.", "evidence": "Fresh evidence for new geometry.", "when": "required gate failure", "required": True, "entrypoints": ["run_drc", "run_lvs", "run_extraction", "run_post_layout"]},
        {"id": "A22", "step": "Final GDS, readback, recheck.", "evidence": "Final-byte validation and evidence.", "when": "always", "required": True, "entrypoints": ["generate_views", "run_drc", "run_lvs"]},
        {"id": "A23", "step": "Freeze macro/chip package.", "evidence": "GDS, netlists, models, reports.", "when": "always", "required": True, "entrypoints": ["project scripting"]},
    ],
    "photonic": [
        {"id": "P01", "step": "Define optical/electrical targets and interfaces.", "evidence": "Loss, bandwidth, phase, delay limits.", "when": "always", "required": True, "entrypoints": ["project scripting"]},
        {"id": "P02", "step": "Select PDK, stack, modes, model ranges.", "evidence": "Pinned tech/model refs and gaps.", "when": "always", "required": True, "entrypoints": ["get_capabilities"]},
        {"id": "P03", "step": "Compose intended circuit from devices.", "evidence": "Independent connectivity and params.", "when": "always", "required": True, "entrypoints": ["ip_instantiate"]},
        {"id": "P04", "step": "Validate ports, modes, bounds, coverage.", "evidence": "Mismatch and missing-model findings.", "when": "always", "required": True, "entrypoints": ["run_connectivity", "run_syntax"]},
        {"id": "P05", "step": "Build device geometry/mesh/ports/boundaries.", "evidence": "Reproducible physical sim model.", "when": "outside existing model validity", "required": True, "entrypoints": ["generate_views"]},
        {"id": "P06", "step": "Solve modes/fields; check convergence.", "evidence": "Modes, S-params, convergence.", "when": "characterization required", "required": True, "entrypoints": ["run_em"]},
        {"id": "P07", "step": "Fit and validate a compact model.", "evidence": "Versioned model with validity range.", "when": "new model needed", "required": True, "entrypoints": ["project scripting"]},
        {"id": "P08", "step": "Frequency-domain circuit simulation.", "evidence": "Spectra and target measurements.", "when": "frequency targets apply", "required": True, "entrypoints": ["run_optical"]},
        {"id": "P09", "step": "Dynamic/active circuit simulation.", "evidence": "Transient behavior and limits.", "when": "active/time-dependent circuit", "required": True, "entrypoints": ["run_optical"]},
        {"id": "P10", "step": "Variation sweeps; tune topology/params.", "evidence": "Worst cases and sensitivities.", "when": "robustness plan requires", "required": True, "entrypoints": ["run_optical"]},
        {"id": "P11", "step": "Floorplan and place device instances.", "evidence": "Placed hierarchy and port map.", "when": "always", "required": True, "entrypoints": ["generate_views"]},
        {"id": "P12", "step": "Route waveguides with constraints.", "evidence": "Route geometry and failures.", "when": "always", "required": True, "entrypoints": ["generate_views"]},
        {"id": "P13", "step": "Route heaters/supplies; vias and fill.", "evidence": "Electrical geometry and features.", "when": "active devices or process rules", "required": True, "entrypoints": ["generate_views"]},
        {"id": "P14", "step": "Layout rules; compare intended vs extracted.", "evidence": "DRC and connectivity findings.", "when": "always", "required": True, "entrypoints": ["run_drc", "run_view_sync"]},
        {"id": "P15", "step": "Layout-aware optical extraction.", "evidence": "Derived netlist and coverage.", "when": "layout-aware verification required", "required": True, "entrypoints": ["run_extraction"]},
        {"id": "P16", "step": "Electrical parasitics and coupling.", "evidence": "R/C and coupling models.", "when": "active/RF/thermal structures", "required": True, "entrypoints": ["run_extraction", "run_em"]},
        {"id": "P17", "step": "Bind extraction to calibrated models.", "evidence": "Layout-aware simulation model.", "when": "always", "required": True, "entrypoints": ["project scripting"]},
        {"id": "P18", "step": "Rerun circuit sims on layout model.", "evidence": "Pre/post deltas, measurements.", "when": "supported analysis modes", "required": True, "entrypoints": ["run_optical"]},
        {"id": "P19", "step": "Crosstalk, thermal, package checks.", "evidence": "Field/temperature margins.", "when": "sensitive structures", "required": True, "entrypoints": ["run_em", "run_thermal"]},
        {"id": "P20", "step": "Repair layout/models; repeat gates.", "evidence": "Fresh evidence for new geometry.", "when": "required gate failure", "required": True, "entrypoints": ["run_extraction", "run_optical", "run_drc"]},
        {"id": "P21", "step": "Final dataprep, streamout, readback.", "evidence": "Final GDS, units, layers.", "when": "always", "required": True, "entrypoints": ["generate_views"]},
        {"id": "P22", "step": "Final DRC/connectivity recheck.", "evidence": "Final geometry acceptance.", "when": "always", "required": True, "entrypoints": ["run_drc", "run_connectivity"]},
        {"id": "P23", "step": "Freeze photonic block/chip.", "evidence": "GDS, models, complete evidence.", "when": "always", "required": True, "entrypoints": ["project scripting"]},
    ],
    "mixed": [
        {"id": "M01", "step": "Define system; partition domains.", "evidence": "System limits and contracts.", "when": "always", "required": True, "entrypoints": ["project scripting"]},
        {"id": "M02", "step": "Verify compatibility; plan supplies/interfaces.", "evidence": "Compatibility and supply plan.", "when": "always", "required": True, "entrypoints": ["get_capabilities"]},
        {"id": "M03", "step": "Top reference schematic + behavioral bench.", "evidence": "Reference nets and system tests.", "when": "always", "required": True, "entrypoints": ["project scripting"]},
        {"id": "M04", "step": "Harden blocks via their domain flows.", "evidence": "Pinned bundles and coverage.", "when": "always", "required": True, "entrypoints": ["run_digital_flow", "run_spice", "run_optical"]},
        {"id": "M05", "step": "Import layouts; bind pins and views.", "evidence": "Consistent interfaces, hierarchy.", "when": "always", "required": True, "entrypoints": ["generate_views"]},
        {"id": "M06", "step": "Top-level floorplan with keepouts.", "evidence": "Floorplan and reserved areas.", "when": "always", "required": True, "entrypoints": ["generate_views"]},
        {"id": "M07", "step": "Connect blocks; shields, wells, taps.", "evidence": "Top geometry and connectivity.", "when": "always", "required": True, "entrypoints": ["generate_views"]},
        {"id": "M08", "step": "Chip structures, pads, seal, fill.", "evidence": "Deliverable boundary.", "when": "full-chip delivery", "required": True, "entrypoints": ["generate_views"]},
        {"id": "M09", "step": "Top-level DRC, ERC, LVS.", "evidence": "Violations and mismatches.", "when": "top-level qualification", "required": True, "entrypoints": ["run_drc", "run_erc", "run_lvs"]},
        {"id": "M10", "step": "Top-level extraction, counted once.", "evidence": "Top PEX and coverage.", "when": "physical performance required", "required": True, "entrypoints": ["run_extraction"]},
        {"id": "M11", "step": "Top timing with real loads.", "evidence": "Chip timing and boundary constraints.", "when": "clocked digital interfaces", "required": True, "entrypoints": ["run_timing"]},
        {"id": "M12", "step": "Post-layout mixed-signal tests.", "evidence": "System response and interfaces.", "when": "always", "required": True, "entrypoints": ["run_post_layout"]},
        {"id": "M13", "step": "ADC transfer and dynamic metrics.", "evidence": "DNL/INL/SNR/ENOB, sample limits.", "when": "ADC design", "required": True, "entrypoints": ["run_post_layout"]},
        {"id": "M14", "step": "System corners, coupling, thermal.", "evidence": "Worst-system margins.", "when": "system qualification plan", "required": True, "entrypoints": ["run_em", "run_thermal", "run_spice"]},
        {"id": "M15", "step": "Repair; repeat block and top gates.", "evidence": "Updated evidence, open blockers.", "when": "gate failure or changed inputs", "required": True, "entrypoints": ["run_drc", "run_lvs", "run_extraction", "run_post_layout"]},
        {"id": "M16", "step": "Final export, readback, archive.", "evidence": "Final hash, models, manifest.", "when": "always", "required": True, "entrypoints": ["generate_views"]},
    ],
}


# Deck join (WORKFLOW-COVERAGE, ADR-007): curated op -> deck tools.
#
# Each entry cites the Engine solver registry (composition.py
# Engine._solvers: operation -> {deck-tool: adapter}) plus the
# provision need from interfaces/setup.py SOLVER_DEPS (binaries +
# python probes flattened). Curated here so stage planning stays a
# pure function of its inputs (no imports, no I/O); freshness is
# pinned mechanically by tests/test_stages_decks.py against the live
# registry and SOLVER_DEPS, so a new solver without a DECKS entry
# fails loudly instead of rotting.
DECKS = {
    "run_syntax": [{"tool": "slang", "needs": ["slang"]}],
    "run_synth": [{"tool": "yosys", "needs": ["yosys"]}],
    "run_connectivity": [{"tool": "connectgraph", "needs": []}],
    "run_erc": [{"tool": "connectgraph", "needs": []}],
    "run_view_sync": [{"tool": "connectgraph", "needs": []}],
    "run_drc": [
        {"tool": "magic", "needs": ["magic"]},
        {"tool": "klayout", "needs": ["klayout"]},
    ],
    "run_antenna": [{"tool": "klayout", "needs": ["klayout"]}],
    "run_xschem": [{"tool": "xschem", "needs": ["xschem"]}],
    "run_lvs": [{"tool": "netgen", "needs": ["netgen"]}],
    "run_spice": [{"tool": "ngspice", "needs": ["ngspice"]}],
    "run_post_layout": [{"tool": "ngspice", "needs": ["ngspice"]}],
    "run_optical": [
        {"tool": "sax", "needs": ["sax"]},
        {"tool": "circulax", "needs": ["circulax"]},
    ],
    "run_digital_flow": [{"tool": "librelane", "needs": ["librelane"]}],
    "run_timing": [{"tool": "opensta", "needs": ["sta"]}],
    "run_extraction": [{"tool": "magic", "needs": ["magic"]}],
    "run_em": [{"tool": "meow", "needs": ["meow"]}],
    "run_formal": [{"tool": "sby", "needs": ["sby"]}],
    "run_hdl_test": [{"tool": "icarus", "needs": ["iverilog", "vvp"]}],
    "run_cosim": [{"tool": "cosim", "needs": ["ngspice", "iverilog", "vvp"]}],
    "generate_views": [{"tool": "gdsfactory", "needs": ["gdsfactory"]}],
}

_UNCOVERED_REASONS = {
    "run_thermal": "no solver registered: run_thermal.",
}


def covering_decks(entrypoint, solvers=None, operations=None):
    """Cite the covering decks for one stage entrypoint.

    A scripted entrypoint cites itself (no backend needed). A tool
    entrypoint with registered solvers cites one deck per tool with
    its provision need, plus live readiness when an operations
    mapping (as from `report_capabilities`) is given. An entrypoint
    with no registered solver is an explicit uncovered marker with
    its reason — never a silent gap.

    Args:
        entrypoint: Stage entrypoint name to cover.
        solvers: Operation -> deck-tool cites (tool plus needs).
            Defaults to the curated DECKS table.
        operations: Per-operation readiness mapping as reported by
            `report_capabilities`; None means unprobed.

    Returns:
        List of deck cites (deck, scripted, or uncovered marker).
    """
    table = DECKS if solvers is None else solvers
    if entrypoint in _SCRIPTED:
        return [{"entrypoint": entrypoint, "kind": "scripted"}]
    cites = table.get(entrypoint)
    if not cites:
        return [
            {
                "entrypoint": entrypoint,
                "kind": "uncovered",
                "reason": _UNCOVERED_REASONS.get(
                    entrypoint, f"no solver registered: {entrypoint}."
                ),
            }
        ]
    return [_deck_cite(entrypoint, cite, operations) for cite in cites]


def _deck_cite(entrypoint, cite, operations):
    """One deck cite with live readiness when probed.

    Args:
        entrypoint: Stage entrypoint the deck serves.
        cite: Deck cite with tool plus provision needs.
        operations: Per-operation readiness mapping, or None.

    Returns:
        Deck cite with readiness (ready/blocked/unprobed).
    """
    deck = {
        "entrypoint": entrypoint,
        "kind": "deck",
        "tool": cite["tool"],
        "needs": list(cite["needs"]),
    }
    if operations is None:
        return {**deck, "readiness": "unprobed"}
    row = operations.get(entrypoint, {})
    readiness = row.get("readiness", "unsupported")
    deck["readiness"] = readiness
    if readiness != "ready":
        deck["reason"] = row.get(
            "reason", f"no capability report: {entrypoint}."
        )
        deck["missing"] = list(row.get("missing") or [entrypoint])
        if row.get("remedy"):
            deck["remedy"] = row["remedy"]
    return deck


def flow_cover(flow, solvers=None, operations=None):
    """Cover every stage of a flow with its decks or gap markers.

    Args:
        flow: Flow inventory to cover (digital/analog/photonic/mixed).
        solvers: Operation -> deck-tool cites; the DECKS table when
            omitted.
        operations: Per-operation readiness mapping; None means
            unprobed (deck cites without live readiness).

    Returns:
        Stage list with per-stage cover cites in stage order.

    Raises:
        ValueError: Unknown flow name.
    """
    try:
        stages = STAGES[flow]
    except KeyError:
        raise ValueError(f"Unknown flow: {flow}.") from None
    covered = []
    for stage in stages:
        cover = []
        for entrypoint in stage["entrypoints"]:
            cover.extend(covering_decks(entrypoint, solvers, operations))
        covered.append({**stage, "cover": cover})
    return covered


def render_lane(flow, solvers=None, operations=None):
    """Render one flow lane as stage -> deck cover lines.

    Args:
        flow: Flow inventory to render (digital/analog/photonic/mixed).
        solvers: Operation -> deck-tool cites; the DECKS table when
            omitted.
        operations: Per-operation readiness mapping; None means
            unprobed.

    Returns:
        Text lane render, one line per stage.

    Raises:
        ValueError: Unknown flow name.
    """
    lines = []
    for stage in flow_cover(flow, solvers, operations):
        parts = []
        for cite in stage["cover"]:
            if cite["kind"] == "deck":
                needs = ",".join(cite["needs"]) if cite["needs"] else "builtin"
                parts.append(
                    f"{cite['entrypoint']}/{cite['tool']}"
                    f"[{cite['readiness']}:{needs}]"
                )
            elif cite["kind"] == "scripted":
                parts.append(f"{cite['entrypoint']}[scripted]")
            else:
                parts.append(f"{cite['entrypoint']}[uncovered: {cite['reason']}]")
        lines.append(f"{stage['id']} {stage['step']} :: {' + '.join(parts)}")
    return "\n".join(lines) + "\n"


def applicable_stages(flow, available_backends):
    """Plan a flow against installed backends.

    Scripted entrypoints need no backend. A stage whose tool
    entrypoints are all available is ready; otherwise it stays
    required-but-blocked (never silently dropped).

    Args:
        flow: Flow inventory to plan (digital/analog/photonic/mixed).
        available_backends: Installed backend entrypoint names.

    Returns:
        Stage list with per-stage readiness (ready/blocked).

    Raises:
        ValueError: Unknown flow name.
    """
    try:
        stages = STAGES[flow]
    except KeyError:
        raise ValueError(f"Unknown flow: {flow}.") from None
    available = set(available_backends)
    planned = []
    for stage in stages:
        needed = [e for e in stage["entrypoints"] if e not in _SCRIPTED]
        readiness = "ready" if all(e in available for e in needed) else "blocked"
        planned.append({**stage, "readiness": readiness})
    return planned
