"""Scoped testbench blocks with editable templates."""

from .blocks import (
    SOURCE_PREFIX,
    TESTBENCH_COMPONENT,
    assert_runnable,
    check_fresh,
    create_block,
    describe_block,
    design_net_pins,
    dut_digest,
    excluded_harness_instances,
    harness_instances,
    materialize_interface,
    normalize_probes,
    normalize_targets,
    probe_simulator,
    regenerate_block,
)
from .templates import (
    TEMPLATE_EXTENSIONS,
    TEMPLATE_KINDS,
    TEMPLATE_VERSION,
    describe_template,
    render,
)

__all__ = [
    "SOURCE_PREFIX",
    "TESTBENCH_COMPONENT",
    "TEMPLATE_EXTENSIONS",
    "TEMPLATE_KINDS",
    "TEMPLATE_VERSION",
    "assert_runnable",
    "check_fresh",
    "create_block",
    "describe_block",
    "describe_template",
    "design_net_pins",
    "dut_digest",
    "excluded_harness_instances",
    "harness_instances",
    "materialize_interface",
    "normalize_probes",
    "normalize_targets",
    "probe_simulator",
    "regenerate_block",
    "render",
]
