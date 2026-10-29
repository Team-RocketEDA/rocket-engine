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
        "operation": "run_optical",
        "target_file": "mzi.yml",
        "files": ["mzi.yml"],
        "base": "tests/adapters/fixtures/sax",
        "expected_verdict": "FAIL",
        "expected_rules": ["transmission"],
        "variants": 1,
        "doc": "Detune the output coupler; cross-port target misses.",
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


# VALIDATE-D design staging: base files come from apply_operator /
# copy_base_files; the extras below (committed harness or monitor,
# vendored firmware, watchdog, defines) complete a runnable sim dir.
# Shared by tests/validate, scripts/mutate.py, and scripts/scenarios.py.

_DESIGNS = ("serv", "picorv32")
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
    mutant). Returns sources/defines/timeout_s/workdir for a
    run_hdl_test job, plus watchdog_units for SERV. Missing pieces
    raise FileNotFoundError; a drifted harness watchdog raises
    MutationError — never a silent unmutated-shaped run.
    """
    if design not in _DESIGNS:
        raise KeyError(f"unknown vendored design: {design!r}.")
    root = Path(root)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
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
    """Stage an unmutated design sim dir; return run_hdl_test job args."""
    entry = _design_entry(design)
    dest = Path(dest_dir)
    copy_base_files(entry, Path(root) / entry["base"], dest)
    return stage_design_extras(design, dest, root)
