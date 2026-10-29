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

__all__ = ["OPERATORS", "MutationError", "apply_operator", "operator_variant"]

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


def apply_operator(name, dest_dir, seed, src_dir):
    """Stage base files into dest_dir and mutate the target copy.

    Returns JSON-native evidence (operator, seed, variant, expected
    verdict/rules, plus operator specifics). Unknown operators raise
    KeyError; drifted probe sites raise MutationError.
    """
    entry = OPERATORS[name]
    variant = operator_variant(name, seed)
    dest = Path(dest_dir)
    src = Path(src_dir)
    dest.mkdir(parents=True, exist_ok=True)
    staged = []
    for filename in entry["files"]:
        shutil.copy(src / filename, dest / filename)
        staged.append(filename)
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
