"""MUTATE-HARNESS: systematic incorrect-design generator.

Each operator stages scratch COPIES of its base fixture files, then
mutates the copy — vendored and committed fixture trees are never
touched in place. Variant selection is `seed % len(variants)`, so
every mutation is reproducible from its seed. The OPERATORS table is
the operator→verdict map: each entry declares the engine operation
that rechecks it plus the expected verdict and rules.
"""

import shutil
from pathlib import Path

from . import operators
from .operators import MutationError

__all__ = [
    "OPERATORS",
    "SERV_WATCHDOG_UNITS",
    "MutationError",
    "apply_operator",
    "copy_base_files",
    "operator_variant",
    "stage_design_extras",
    "stage_good_design",
]

# VALIDATE-D staging watchdog for SERV runs. The good hello run
# finishes below 4M units (bisected: PASS at 4M, watchdog at 3M), so
# 5M keeps a margin over good while holding mutant sims to seconds
# instead of the 200M-harness default (33 s per hang).
SERV_WATCHDOG_UNITS = 5000000

# SERV sim file list (VALIDATE-D): vendored rel paths under
# fixtures/upstream/serv, mirrored by the committed
# tests/adapters/fixtures/hdl/serv_sources.txt manifest (a validate
# test asserts the two stay equal). Staged with structure kept.
_SERV_FILES = [
    "rtl/serv_aligner.v",
    "rtl/serv_alu.v",
    "rtl/serv_bufreg2.v",
    "rtl/serv_bufreg.v",
    "rtl/serv_compdec.v",
    "rtl/serv_csr.v",
    "rtl/serv_ctrl.v",
    "rtl/serv_debug.v",
    "rtl/serv_decode.v",
    "rtl/serv_immdec.v",
    "rtl/serv_mem_if.v",
    "rtl/serv_rf_if.v",
    "rtl/serv_rf_ram_if.v",
    "rtl/serv_rf_ram.v",
    "rtl/serv_rf_top.v",
    "rtl/serv_state.v",
    "rtl/serv_synth_wrapper.v",
    "rtl/serv_top.v",
    "servile/servile_arbiter.v",
    "servile/servile_mux.v",
    "servile/servile_rf_mem_if.v",
    "servile/servile.v",
    "servant/servant.v",
    "servant/servant_mux.v",
    "servant/servant_ram.v",
    "servant/servant_timer.v",
    "servant/servant_gpio.v",
    "bench/servant_sim.v",
    "bench/uart_decoder.v",
]

_PICO_FILES = ["picorv32.v", "testbench_ez.v"]

# VALIDATE-A bandgap snapshot (2amlogic sky130-bandgap): the
# output-voltage-tc netlist that the signoff envelope 1a grades
# 45/45 PASS on DR-005 [1.176, 1.224] V. Staged flat.
_BANDGAP_SNAPSHOT = "20260817-015751-13476b7.spice"
_BANDGAP_FILES = [_BANDGAP_SNAPSHOT]
_BANDGAP_BASE = (
    "fixtures/upstream/sky130-bandgap/sim/output-voltage-tc/netlist-snapshots"
)
# DR-005 ratified accuracy row: 1.20 V +/-2% untrimmed.
_BANDGAP_VREF_MIN = 1.176
_BANDGAP_VREF_MAX = 1.224

# VALIDATE-P MZI pair: the SAX-notebook balanced circuit
# (tests/adapters/fixtures/sax/mzi.yml) plus the cspdk reference
# si340 MZI GDS as layout truth. Documented CORNERSTONE min rules
# for GDS 3/0: 350 nm feature, 200 nm gap (49th-call guidelines
# section 5.3-5.4, Table 4). Staged flat as mzi.yml + mzi_ref.gds.
_MZI_CIRCUIT = "mzi.yml"
_MZI_REF_GDS = "fixtures/upstream/cspdk/tests/gds_ref_si340/mzi.gds"
_MZI_STAGED_GDS = "mzi_ref.gds"
_MZI_TECH = "cornerstone-si340"
_MZI_CELL = "mzi"
_MZI_RULES = {"layer": [3, 0], "width_um": 0.35, "space_um": 0.2}
_MZI_RULES_REF = (
    "CORNERSTONE-49th-Call-Design-Guidelines-1.pdf section 5.3-5.4 "
    "Table 4 (vendored cspdk references/)"
)
_MZI_TIMEOUT_S = 120

# VALIDATE-M sigma-delta seam pairs: the digital wrapper sdm_rx.v
# (fixtures/upstream/ttsky-sigma-delta/rtl) plus the committed
# Verilog bench and the cleaned PEX bitstream vector (the one-way
# seam handoff), and the analog macro sd_top PEX netlist
# (fixtures/upstream/ttsky-sigma-delta/spice). Staged flat.
_SDM_FILES = ["sdm_rx.v"]
_SDM_BASE = "fixtures/upstream/ttsky-sigma-delta/rtl"
_SDM_BENCH = "tests/adapters/fixtures/hdl/sdm_rx_bench.v"
_SDM_VECTOR = "fixtures/upstream/ttsky-sigma-delta/rtl/tb/vectors/pex_bits.txt"
_SDM_STAGED_VECTOR = "pex_bits_clean.txt"
_SDM_TIMEOUT_S = 120
_SDTOP_SNAPSHOT = "sd_top_pex.spice"
_SDTOP_FILES = [_SDTOP_SNAPSHOT]
_SDTOP_BASE = "fixtures/upstream/ttsky-sigma-delta/spice"
# Integrator monitor UA1 DC ~0.9 V mean (docs/09b Phase 1.1).
_SDTOP_INT_MIN = 0.8
_SDTOP_INT_MAX = 1.0

OPERATORS = {
    "digital_reset_break": {
        "domain": "digital",
        "operation": "run_hdl_test",
        "target_file": "counter.v",
        "files": ["counter.v", "tb_pass.v"],
        "base": "tests/adapters/fixtures/hdl",
        "expected_verdict": "FAIL",
        "expected_rules": ["assert_fatal"],
        "variants": 2,
        "doc": "Break the async reset (inverted or stuck); tb $fatal fires.",
    },
    "digital_truncation": {
        "domain": "digital",
        "operation": "run_hdl_test",
        "target_file": "counter.v",
        "files": ["counter.v", "tb_pass.v"],
        "base": "tests/adapters/fixtures/hdl",
        "expected_verdict": "FAIL",
        "expected_rules": ["assert_fatal"],
        "variants": 3,
        "doc": "Narrow the count update; the sequence never reaches 10.",
    },
    "digital_unconnected_port": {
        "domain": "digital",
        "operation": "run_hdl_test",
        "target_file": "tb_pass.v",
        "files": ["counter.v", "tb_pass.v"],
        "base": "tests/adapters/fixtures/hdl",
        "expected_verdict": "FAIL",
        "expected_rules": ["assert_fatal"],
        "variants": 2,
        "doc": "Leave a DUT port open in the harness; the count mismatches.",
    },
    "serv_reset_break": {
        "domain": "digital",
        "design": "serv",
        "operation": "run_hdl_test",
        "target_file": "servant/servant.v",
        "files": list(_SERV_FILES),
        "base": "fixtures/upstream/serv",
        "expected_verdict": "FAIL",
        "expected_rules": ["assert_fatal"],
        "variants": 2,
        "doc": "Hold the servant CPU in reset (stuck or inverted); watchdog fires.",
    },
    "serv_truncation": {
        "domain": "digital",
        "design": "serv",
        "operation": "run_hdl_test",
        "target_file": "rtl/serv_bufreg.v",
        "files": list(_SERV_FILES),
        "base": "fixtures/upstream/serv",
        "expected_verdict": "FAIL",
        "expected_rules": ["assert_fatal"],
        "variants": 3,
        "doc": "Narrow the data-bus address; MMIO unreachable, no HALT.",
    },
    "serv_unconnected_port": {
        "domain": "digital",
        "design": "serv",
        "operation": "run_hdl_test",
        "target_file": "servant/servant.v",
        "files": list(_SERV_FILES),
        "base": "fixtures/upstream/serv",
        "expected_verdict": "FAIL",
        "expected_rules": ["assert_fatal"],
        "variants": 2,
        "doc": "Leave a servant CPU port open; firmware never boots.",
    },
    "picorv32_reset_break": {
        "domain": "digital",
        "design": "picorv32",
        "operation": "run_hdl_test",
        "target_file": "testbench_ez.v",
        "files": list(_PICO_FILES),
        "base": "fixtures/upstream/picorv32",
        "expected_verdict": "FAIL",
        "expected_rules": ["assert_fatal"],
        "variants": 2,
        "doc": "Hold test_ez in reset (stuck or re-asserted); no progress.",
    },
    "picorv32_truncation": {
        "domain": "digital",
        "design": "picorv32",
        "operation": "run_hdl_test",
        "target_file": "picorv32.v",
        "files": list(_PICO_FILES),
        "base": "fixtures/upstream/picorv32",
        "expected_verdict": "FAIL",
        "expected_rules": ["assert_fatal"],
        "variants": 3,
        "doc": "Narrow the ALU add path; the ez counter never reaches 10.",
    },
    "picorv32_unconnected_port": {
        "domain": "digital",
        "design": "picorv32",
        "operation": "run_hdl_test",
        "target_file": "testbench_ez.v",
        "files": list(_PICO_FILES),
        "base": "fixtures/upstream/picorv32",
        "expected_verdict": "FAIL",
        "expected_rules": ["assert_fatal"],
        "variants": 2,
        "doc": "Leave a CPU port open in the ez bench; fetches stall.",
    },
    "analog_sizing_out_of_spec": {
        "domain": "analog",
        "operation": "run_spice",
        "target_file": "rc_divider.spice",
        "files": ["rc_divider.spice"],
        "base": "tests/adapters/fixtures/ngspice",
        "expected_verdict": "FAIL",
        "expected_rules": ["measurement"],
        "variants": 3,
        "doc": "Move R2 off nominal; Vout leaves its [1.199, 1.201] V bound.",
    },
    "analog_open_net": {
        "domain": "analog",
        "operation": "run_spice",
        "target_file": "rc_divider.spice",
        "files": ["rc_divider.spice"],
        "base": "tests/adapters/fixtures/ngspice",
        "expected_verdict": "FAIL",
        "expected_rules": ["measurement"],
        "variants": 2,
        "doc": "Lift R2 from the divider; out rises to the 1.8 V rail.",
    },
    "layout_drc_violation": {
        "domain": "layout",
        "operation": "run_drc",
        "target_file": "good.mag",
        "files": ["good.mag"],
        "base": "tests/adapters/fixtures/drc",
        "expected_verdict": "FAIL",
        "expected_rules": ["spacing", "width"],
        "variants": 2,
        "doc": "Shift/shrink a rect into an scmos spacing/width violation.",
    },
    "netlist_lvs_mismatch": {
        "domain": "layout",
        "operation": "run_lvs",
        "target_file": "schematic.spice",
        "files": ["layout.spice", "schematic.spice"],
        "base": "tests/mutate/fixtures/lvs_inv",
        "expected_verdict": "FAIL",
        "expected_rules": ["lvs_net_mismatch"],
        "variants": 2,
        "doc": "Rename a schematic bulk net; layout vs schematic mismatch.",
    },
    "photonic_geometry_mistune": {
        "domain": "photonic",
        "design": "mzi",
        "operation": "run_optical",
        "target_file": "mzi.yml",
        "files": ["mzi.yml"],
        "base": "tests/adapters/fixtures/sax",
        "expected_verdict": "FAIL",
        "expected_rules": ["transmission"],
        "variants": 2,
        "doc": "Lengthen the MZI bottom arm; cross-port target misses.",
    },
    "photonic_circuit_mistune": {
        "domain": "photonic",
        "design": "mzi",
        "operation": "run_optical",
        "target_file": "mzi.yml",
        "files": ["mzi.yml"],
        "base": "tests/adapters/fixtures/sax",
        "expected_verdict": "FAIL",
        "expected_rules": ["transmission"],
        "variants": 1,
        "doc": "Detune the output coupler; cross-port target misses.",
    },
    "bandgap_sizing_out_of_spec": {
        "domain": "analog",
        "design": "bandgap",
        "operation": "run_spice",
        "target_file": _BANDGAP_SNAPSHOT,
        "files": list(_BANDGAP_FILES),
        "base": _BANDGAP_BASE,
        "expected_verdict": "FAIL",
        "expected_rules": ["measurement"],
        "variants": 3,
        "doc": "Move n_r2 off 51; Vref leaves DR-005 [1.176, 1.224] V.",
    },
    "bandgap_open_net": {
        "domain": "analog",
        "design": "bandgap",
        "operation": "run_spice",
        "target_file": _BANDGAP_SNAPSHOT,
        "files": list(_BANDGAP_FILES),
        "base": _BANDGAP_BASE,
        "expected_verdict": "FAIL",
        "expected_rules": ["measurement"],
        "variants": 2,
        "doc": "Lift XR2A from VOUT; feedback cut, Vref misses.",
    },
    "sdm_reset_break": {
        "domain": "digital",
        "design": "sdm_rx",
        "operation": "run_hdl_test",
        "target_file": "sdm_rx.v",
        "files": list(_SDM_FILES),
        "base": _SDM_BASE,
        "expected_verdict": "FAIL",
        "expected_rules": ["assert_fatal"],
        "variants": 2,
        "doc": "Break the sinc3-path reset (inverted or stuck); bench $fatal fires.",
    },
    "sdm_truncation": {
        "domain": "digital",
        "design": "sdm_rx",
        "operation": "run_hdl_test",
        "target_file": "sdm_rx.v",
        "files": list(_SDM_FILES),
        "base": _SDM_BASE,
        "expected_verdict": "FAIL",
        "expected_rules": ["assert_fatal"],
        "variants": 3,
        "doc": "Narrow data_fast; DC full scale never reaches 25^3.",
    },
    "sdm_unconnected_port": {
        "domain": "digital",
        "design": "sdm_rx",
        "operation": "run_hdl_test",
        "target_file": "sdm_rx.v",
        "files": list(_SDM_FILES),
        "base": _SDM_BASE,
        "expected_verdict": "FAIL",
        "expected_rules": ["assert_fatal"],
        "variants": 2,
        "doc": "Break the bitstream input path (bit_ce/bit_i as if unconnected).",
    },
    "sdtop_sizing_out_of_spec": {
        "domain": "analog",
        "design": "sd_top",
        "operation": "run_spice",
        "target_file": _SDTOP_SNAPSHOT,
        "files": list(_SDTOP_FILES),
        "base": _SDTOP_BASE,
        "expected_verdict": "FAIL",
        "expected_rules": ["measurement"],
        "variants": 3,
        "doc": "Move RIN l off 102.57; integrator DC leaves [0.8, 1.0] V.",
    },
    "sdtop_open_net": {
        "domain": "analog",
        "design": "sd_top",
        "operation": "run_spice",
        "target_file": _SDTOP_SNAPSHOT,
        "files": list(_SDTOP_FILES),
        "base": _SDTOP_BASE,
        "expected_verdict": "FAIL",
        "expected_rules": ["measurement"],
        "variants": 2,
        "doc": "Lift X64 from UA0; input open, integrator DC misses.",
    },
}


def operator_variant(name, seed):
    """Variant index for (operator, seed): seed mod variant count."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise MutationError(f"{name}: seed must be an int, got {seed!r}.")
    return seed % OPERATORS[name]["variants"]


def copy_base_files(entry, src_dir, dest_dir):
    """Copy an entry's base files into dest_dir; return staged names.

    Repo-relative paths (SERV rtl/ + servile/ + servant/ + bench/)
    keep their structure under dest_dir; flat fixtures stay flat.
    """
    src = Path(src_dir)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    staged = []
    for filename in entry["files"]:
        out = dest / filename
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src / filename, out)
        staged.append(filename)
    return staged


def apply_operator(name, dest_dir, seed, src_dir):
    """Stage base files into dest_dir and mutate the target copy.

    Returns JSON-native evidence (operator, seed, variant, expected
    verdict/rules, plus operator specifics). Unknown operators raise
    KeyError; drifted probe sites raise MutationError.
    """
    entry = OPERATORS[name]
    variant = operator_variant(name, seed)
    dest = Path(dest_dir)
    staged = copy_base_files(entry, src_dir, dest)
    target = dest / entry["target_file"]
    mutate = getattr(operators, name)
    mutated, extra = mutate(target.read_text(encoding="utf-8"), variant)
    target.write_text(mutated, encoding="utf-8")
    evidence = {
        "operator": name,
        "domain": entry["domain"],
        "operation": entry["operation"],
        "seed": seed,
        "variant": variant,
        "target_file": entry["target_file"],
        "staged_files": staged,
        "expected_verdict": entry["expected_verdict"],
        "expected_rules": list(entry["expected_rules"]),
        "expected_rule": extra.pop("expected_rule", entry["expected_rules"][0]),
    }
    evidence.update(extra)
    return evidence


# VALIDATE-D/A/P/M design staging: base files come from
# apply_operator / copy_base_files; the extras below (committed
# harness or monitor or bench, vendored firmware or vector, watchdog,
# defines, the bandgap/sd_top run_spice job shapes, or the mzi
# circuit+layout pair) complete a runnable sim dir. Shared by
# tests/validate, scripts/mutate.py, and scripts/scenarios.py.

_DESIGNS = ("serv", "picorv32", "bandgap", "mzi", "sdm_rx", "sd_top")
_HARNESS = "tests/adapters/fixtures/hdl/serv_harness.v"
_MONITOR = "tests/adapters/fixtures/hdl/picorv32_monitor.v"
_FIRMWARE = "fixtures/upstream/serv/sw/hello_uart.hex"
_WATCHDOG_DEFAULT = "parameter watchdog_units = 200000000"


def _design_entry(design):
    for entry in OPERATORS.values():
        if entry.get("design") == design:
            return entry
    raise KeyError(f"unknown vendored design: {design!r}.")


def stage_design_extras(design, dest_dir, root):
    """Copy a design's extras into a staged sim dir; return job args.

    Base files must already be staged (via apply_operator for a
    mutant). Digital designs return sources/defines/timeout_s/
    workdir for a run_hdl_test job (plus watchdog_units for SERV);
    the bandgap/sd_top return sources/measurements/analyses/options/
    params/corner/temp_c/timeout_s/workdir for a run_spice job
    (the PDK pin is resolved by the caller from its own store, so
    a missing store skips loudly at the call site, never here);
    the mzi returns sources/workdir/timeout_s for a run_optical
    job plus a layout sidecar (staged reference GDS + documented
    CORNERSTONE rules) for a run_drc job; sdm_rx pairs the vendored
    DUT with the committed Verilog bench + the cleaned PEX vector.
    Missing pieces raise FileNotFoundError; a drifted harness
    watchdog raises MutationError — never a silent
    unmutated-shaped run.
    """
    if design not in _DESIGNS:
        raise KeyError(f"unknown vendored design: {design!r}.")
    root = Path(root)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    if design == "mzi":
        sources = [str(dest / name) for name in _staged_names(design, dest)]
        ref_gds = root / _MZI_REF_GDS
        if not ref_gds.is_file():
            raise FileNotFoundError(
                f"mzi staging: cspdk reference GDS missing: {ref_gds} "
                "(scripts/fetch_fixtures.py --only cspdk)"
            )
        staged_gds = dest / _MZI_STAGED_GDS
        shutil.copy(ref_gds, staged_gds)
        return {
            "sources": sources,
            "workdir": str(dest),
            "timeout_s": _MZI_TIMEOUT_S,
            "layout": {
                "gds_file": str(staged_gds),
                "cell": _MZI_CELL,
                "tech": _MZI_TECH,
                "rules": {
                    "layer": list(_MZI_RULES["layer"]),
                    "width_um": _MZI_RULES["width_um"],
                    "space_um": _MZI_RULES["space_um"],
                },
                "rules_ref": _MZI_RULES_REF,
            },
        }
    if design == "bandgap":
        sources = [str(dest / name) for name in _staged_names(design, dest)]
        return {
            "sources": sources,
            "workdir": str(dest),
            "timeout_s": 300,
            "measurements": [
                {
                    "name": "vref",
                    "expr": "v(vref)",
                    "unit": "V",
                    "min": _BANDGAP_VREF_MIN,
                    "max": _BANDGAP_VREF_MAX,
                }
            ],
            "analyses": ["op"],
            "options": ["wnflag=1"],
            "params": {"vsup": 3.3},
            "corner": "tt",
            "temp_c": 27,
        }
    if design == "sd_top":
        sources = [str(dest / name) for name in _staged_names(design, dest)]
        return {
            "sources": sources,
            "workdir": str(dest),
            "timeout_s": 300,
            "measurements": [
                {
                    "name": "int_dc",
                    "expr": "v(ua1)",
                    "unit": "V",
                    "min": _SDTOP_INT_MIN,
                    "max": _SDTOP_INT_MAX,
                }
            ],
            "analyses": ["op"],
            "options": ["wnflag=1"],
            "params": {"vsup": 3.3},
            "corner": "tt",
            "temp_c": 27,
        }
    if design == "sdm_rx":
        bench_src = root / _SDM_BENCH
        if not bench_src.is_file():
            raise FileNotFoundError(f"sdm_rx bench missing: {bench_src}")
        bench_dest = dest / Path(_SDM_BENCH).name
        shutil.copy(bench_src, bench_dest)
        vector_src = root / _SDM_VECTOR
        if not vector_src.is_file():
            raise FileNotFoundError(f"sdm_rx PEX vector missing: {vector_src}")
        lines = vector_src.read_text(encoding="utf-8").splitlines()
        clean = [line.strip() for line in lines[1:] if line.strip() in ("0", "1")]
        if len(clean) != 2048:
            raise MutationError(
                f"sdm_rx staging: PEX vector has {len(clean)} bits, want 2048."
            )
        (dest / _SDM_STAGED_VECTOR).write_text("\n".join(clean) + "\n", encoding="utf-8")
        # iverilog-14 elaboration shim (behavior-preserving, no value
        # change): the vendored sdm_rx.v declares `fast_strobe /
        # prec_strobe` after their first use (line 172 vs 135), which
        # the vendor's older iverilog accepted but oss-cad-suite
        # iverilog 14.0 rejects ("declaration after use"). Move the
        # declaration earlier in the STAGED copy only (vendored bytes
        # stay pristine); mutants patch the same way after apply_operator.
        dut_path = dest / "sdm_rx.v"
        dut_text = dut_path.read_text(encoding="utf-8")
        strobe_decl = "    reg fast_strobe, prec_strobe;\n"
        anchor = "    reg [15:0] osr_fast, osr_prec;      // active copies, load on clear\n"
        if dut_text.count(strobe_decl) != 1 or dut_text.count(anchor) != 1:
            raise MutationError(
                "sdm_rx staging: strobe-decl shim site drifted "
                f"({dut_text.count(strobe_decl)}x decl, {dut_text.count(anchor)}x anchor)."
            )
        dut_text = dut_text.replace(strobe_decl, "")
        dut_text = dut_text.replace(anchor, anchor + strobe_decl)
        dut_path.write_text(dut_text, encoding="utf-8")
        sources = [str(dest / name) for name in _staged_names(design, dest)]
        sources.append(str(bench_dest))
        return {
            "sources": sources,
            "defines": [],
            "timeout_s": _SDM_TIMEOUT_S,
            "watchdog_units": None,
            "workdir": str(dest),
        }
    if design == "serv":
        harness_src = root / _HARNESS
        if not harness_src.is_file():
            raise FileNotFoundError(f"SERV harness missing: {harness_src}")
        text = harness_src.read_text(encoding="utf-8")
        if text.count(_WATCHDOG_DEFAULT) != 1:
            raise MutationError(
                f"serv staging: watchdog site occurs "
                f"{text.count(_WATCHDOG_DEFAULT)}x, want 1."
            )
        text = text.replace(
            _WATCHDOG_DEFAULT,
            f"parameter watchdog_units = {SERV_WATCHDOG_UNITS}",
        )
        harness_dest = dest / Path(_HARNESS).name
        harness_dest.write_text(text, encoding="utf-8")
        hex_src = root / _FIRMWARE
        if not hex_src.is_file():
            raise FileNotFoundError(f"SERV firmware missing: {hex_src}")
        shutil.copy(hex_src, dest / Path(_FIRMWARE).name)
        sources = [str(dest / name) for name in _staged_names(design, dest)]
        sources.append(str(harness_dest))
        return {
            "sources": sources,
            "defines": [],
            "timeout_s": 300,
            "watchdog_units": SERV_WATCHDOG_UNITS,
            "workdir": str(dest),
        }
    monitor_src = root / _MONITOR
    if not monitor_src.is_file():
        raise FileNotFoundError(f"picorv32 monitor missing: {monitor_src}")
    monitor_dest = dest / Path(_MONITOR).name
    shutil.copy(monitor_src, monitor_dest)
    sources = [str(dest / name) for name in _staged_names(design, dest)]
    sources.append(str(monitor_dest))
    return {
        "sources": sources,
        "defines": ["COMPRESSED_ISA"],
        "timeout_s": 120,
        "watchdog_units": None,
        "workdir": str(dest),
    }


def _staged_names(design, dest):
    entry = _design_entry(design)
    names = []
    for filename in entry["files"]:
        name = filename
        if not (Path(dest) / name).is_file():
            raise FileNotFoundError(f"{design} staging: base file missing: {name}")
        names.append(name)
    return names


def stage_good_design(design, dest_dir, root):
    """Stage an unmutated design sim dir; return runnable job args."""
    entry = _design_entry(design)
    dest = Path(dest_dir)
    copy_base_files(entry, Path(root) / entry["base"], dest)
    return stage_design_extras(design, dest, root)
