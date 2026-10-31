"""RUN-PARAMS unit tests: explicit run.request schema.

The schema carries the xschem live-knob equivalents (netlist type,
flat/split shape, lvs flag, top-is-subckt, deck opts) as explicit
run parameters: validated at submit, frozen into the run snapshot,
unknown fields rejected loudly — never ignored. Same shape for
IDE, MCP, and console callers.
"""

import pytest

from rocket_engine.interfaces.runparams import (
    NETLIST_TYPES,
    RUN_REQUEST_DEFAULTS,
    RUN_REQUEST_FIELDS,
    RUN_REQUEST_SCHEMA,
    RunParamsError,
    freeze_run_request,
    parse_run_request,
    validate_run_request,
)


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def test_field_inventory():
    assert RUN_REQUEST_FIELDS == (
        "netlist_type",
        "flat_netlist",
        "lvs_netlist",
        "top_is_subckt",
        "deck_opts",
    )
    assert set(RUN_REQUEST_DEFAULTS) == set(RUN_REQUEST_FIELDS)
    assert set(NETLIST_TYPES) == {"spice", "spectre", "verilog", "vhdl"}


def test_missing_request_yields_all_defaults():
    assert validate_run_request(None) == {
        "netlist_type": "spice",
        "flat_netlist": False,
        "lvs_netlist": False,
        "top_is_subckt": False,
        "deck_opts": {},
    }
    assert validate_run_request({}) == validate_run_request(None)


def test_partial_request_fills_defaults():
    assert validate_run_request({"flat_netlist": True}) == {
        "netlist_type": "spice",
        "flat_netlist": True,
        "lvs_netlist": False,
        "top_is_subckt": False,
        "deck_opts": {},
    }


def test_full_shape_accepted_verbatim():
    params = {
        "netlist_type": "spectre",
        "flat_netlist": True,
        "lvs_netlist": True,
        "top_is_subckt": True,
        "deck_opts": {
            "simulator lang": "spectre",
            "scale": 1e-6,
            "threads": 4,
        },
    }
    assert validate_run_request(params) == params


def test_each_netlist_type_accepted():
    for kind in NETLIST_TYPES:
        validated = validate_run_request({"netlist_type": kind})
        assert validated["netlist_type"] == kind


def test_bad_netlist_type_rejected_with_allowed_values():
    with pytest.raises(RunParamsError) as excinfo:
        validate_run_request({"netlist_type": "hspice"})
    assert _code(excinfo) == "invalid_run_param"
    assert "netlist_type" in str(excinfo.value)
    assert "hspice" in str(excinfo.value)
    for kind in NETLIST_TYPES:
        assert kind in str(excinfo.value)
    assert excinfo.value.fields == ["netlist_type"]


@pytest.mark.parametrize(
    "flag", ["flat_netlist", "lvs_netlist", "top_is_subckt"]
)
@pytest.mark.parametrize("bad", ["true", "yes", 1, 0, None, [True]])
def test_flags_must_be_bool(flag, bad):
    with pytest.raises(RunParamsError) as excinfo:
        validate_run_request({flag: bad})
    assert _code(excinfo) == "invalid_run_param"
    assert flag in str(excinfo.value)
    assert excinfo.value.fields == [flag]


def test_unknown_field_rejected_loudly():
    with pytest.raises(RunParamsError) as excinfo:
        validate_run_request({"netlist_type": "spice", "flatten": True})
    assert _code(excinfo) == "unknown_run_param"
    assert "flatten" in str(excinfo.value)
    for field in RUN_REQUEST_FIELDS:
        assert field in str(excinfo.value)
    assert excinfo.value.fields == ["flatten"]


def test_multiple_unknown_fields_all_named():
    with pytest.raises(RunParamsError) as excinfo:
        validate_run_request({"zzz": 1, "aaa": 2})
    assert _code(excinfo) == "unknown_run_param"
    assert excinfo.value.fields == ["aaa", "zzz"]
    assert "aaa" in str(excinfo.value)
    assert "zzz" in str(excinfo.value)


@pytest.mark.parametrize("bad", [["netlist_type"], "spice", 42, True])
def test_non_mapping_request_rejected(bad):
    with pytest.raises(RunParamsError) as excinfo:
        validate_run_request(bad)
    assert _code(excinfo) == "invalid_run_request"


def test_deck_opts_must_be_mapping():
    with pytest.raises(RunParamsError) as excinfo:
        validate_run_request({"deck_opts": ["scale"]})
    assert _code(excinfo) == "invalid_run_param"
    assert excinfo.value.fields == ["deck_opts"]


def test_deck_opts_rejects_nested_values():
    with pytest.raises(RunParamsError) as excinfo:
        validate_run_request({"deck_opts": {"nested": {"deep": 1}}})
    assert _code(excinfo) == "invalid_run_param"
    assert "deck_opts.nested" in str(excinfo.value)
    with pytest.raises(RunParamsError) as excinfo:
        validate_run_request({"deck_opts": {"items": [1, 2]}})
    assert _code(excinfo) == "invalid_run_param"


def test_deck_opts_rejects_non_string_keys():
    with pytest.raises(RunParamsError) as excinfo:
        validate_run_request({"deck_opts": {42: "x"}})
    assert _code(excinfo) == "invalid_run_param"
    assert excinfo.value.fields == ["deck_opts"]


def test_deck_opts_scalars_pass_through():
    opts = {
        "name": "tt",
        "scale": 1e-6,
        "threads": 4,
        "fast": True,
        "tag": None,
    }
    assert validate_run_request({"deck_opts": opts})["deck_opts"] == opts


def test_validate_does_not_mutate_caller():
    params = {"flat_netlist": True, "deck_opts": {"scale": 1.0}}
    snapshot = {"flat_netlist": True, "deck_opts": {"scale": 1.0}}
    validated = validate_run_request(params)
    assert params == snapshot
    validated["deck_opts"]["scale"] = 2.0
    assert params == snapshot


def test_freeze_shows_every_knob():
    text = freeze_run_request(validate_run_request(None))
    assert isinstance(text, str)
    assert text.endswith("\n")
    for field in RUN_REQUEST_FIELDS:
        assert field in text


def test_freeze_replay_is_byte_identical():
    first = validate_run_request(
        {
            "top_is_subckt": True,
            "netlist_type": "verilog",
            "deck_opts": {"b": 1, "a": 2},
        }
    )
    second = validate_run_request(
        {
            "deck_opts": {"a": 2, "b": 1},
            "netlist_type": "verilog",
            "top_is_subckt": True,
        }
    )
    assert freeze_run_request(first) == freeze_run_request(second)
    assert freeze_run_request(first) == freeze_run_request(first)


def test_freeze_orders_deck_opts_deterministically():
    text = freeze_run_request(
        validate_run_request({"deck_opts": {"zebra": 1, "apple": 2}})
    )
    assert text.index("apple") < text.index("zebra")


def test_parse_round_trip():
    validated = validate_run_request(
        {"netlist_type": "vhdl", "lvs_netlist": True, "deck_opts": {"x": 1}}
    )
    assert parse_run_request(freeze_run_request(validated)) == validated


def test_parse_rejects_bad_yaml():
    with pytest.raises(RunParamsError) as excinfo:
        parse_run_request("request: [unclosed")
    assert _code(excinfo) == "invalid_run_request"


def test_parse_rejects_unknown_field():
    with pytest.raises(RunParamsError) as excinfo:
        parse_run_request("request:\n  netlist_type: spice\n  bogus: 1\n")
    assert _code(excinfo) == "unknown_run_param"


def test_schema_constant_describes_every_field():
    assert set(RUN_REQUEST_SCHEMA["properties"]) == set(RUN_REQUEST_FIELDS)
    enum = RUN_REQUEST_SCHEMA["properties"]["netlist_type"]["enum"]
    assert enum == list(NETLIST_TYPES)
    assert RUN_REQUEST_SCHEMA["additionalProperties"] is False
    for field, default in RUN_REQUEST_DEFAULTS.items():
        assert RUN_REQUEST_SCHEMA["properties"][field]["default"] == default
