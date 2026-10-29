"""One mutation function per MUTATE-HARNESS operator.

Each function takes the base file text plus a variant index and
returns (mutated_text, extra_evidence). Every site is probe-guarded:
the expected base string must occur exactly once, else MutationError
— a fixture that drifted must fail loudly, never silently pass
through unmutated. Variant selection is `seed % len(variants)`,
computed by the caller, so every mutation is reproducible from seed.
"""

import math


class MutationError(ValueError):
    """A mutation site is missing or ambiguous (fixture drift)."""


def _once(text, old, operator):
    found = text.count(old)
    if found != 1:
        raise MutationError(
            f"{operator}: probe site {old!r} occurs {found}x, want 1."
        )
    return found


def digital_reset_break(text, variant):
    """Break the async reset: inverted condition or stuck active."""
    old = "if (!rst_n)"
    _once(text, old, "digital_reset_break")
    new = ["if (rst_n)", "if (1'b1)"][variant % 2]
    desc = [
        "reset condition inverted (counts in reset, clears on release)",
        "reset stuck active (count held at zero)",
    ][variant % 2]
    return text.replace(old, new), {"variant_desc": desc}


def digital_truncation(text, variant):
    """Narrow the count update so the sequence never reaches 10."""
    old = "count <= count + 4'd1;"
    _once(text, old, "digital_truncation")
    alts = [
        ("count <= (count + 4'd1) & 4'h7;", "count masked to 3 bits (max 7)"),
        ("count <= (count + 4'd1) & 4'h3;", "count masked to 2 bits (max 3)"),
        (
            "count <= {1'b0, count[2:0]} + 4'd1;",
            "count zero-extended from 3 bits (max 8)",
        ),
    ]
    new, desc = alts[variant % len(alts)]
    return text.replace(old, new), {"variant_desc": desc}


def digital_unconnected_port(text, variant):
    """Leave a DUT port unconnected in the harness instantiation."""
    alts = [
        (".rst_n(rst_n)", ".rst_n()", "reset input left unconnected (floats)"),
        (".clk(clk)", ".clk()", "clock input left unconnected (no edges)"),
    ]
    old, new, desc = alts[variant % len(alts)]
    _once(text, old, "digital_unconnected_port")
    return text.replace(old, new), {"variant_desc": desc}


def serv_reset_break(text, variant):
    """Break the servant CPU reset: stuck in reset or inverted."""
    old = ".i_rst        (wb_rst),"
    _once(text, old, "serv_reset_break")
    alts = [
        (
            ".i_rst        (1'b1),",
            "CPU reset stuck active (firmware never boots, watchdog fires)",
        ),
        (
            ".i_rst        (~wb_rst),",
            "CPU reset inverted (held in reset while the system runs)",
        ),
    ]
    new, desc = alts[variant % len(alts)]
    return text.replace(old, new), {"variant_desc": desc}


def serv_truncation(text, variant):
    """Narrow the servile data-bus address so MMIO is unreachable."""
    old = "assign o_dbus_adr = {data[31:2], 2'b00};"
    _once(text, old, "serv_truncation")
    alts = [
        (
            "assign o_dbus_adr = 32'b0;",
            "data-bus address zeroed (GPIO/HALT stores hit RAM, no halt)",
        ),
        (
            "assign o_dbus_adr = {data[31:2] & 30'h0FFFFFFF, 2'b00};",
            "address top 2 bits dropped (0x4/0x9xxxxxxx unreachable)",
        ),
        (
            "assign o_dbus_adr = {data[31:2] & 30'h00FFFFFF, 2'b00};",
            "address top 6 bits dropped (0x4/0x9xxxxxxx unreachable)",
        ),
    ]
    new, desc = alts[variant % len(alts)]
    return text.replace(old, new), {"variant_desc": desc}


def serv_unconnected_port(text, variant):
    """Leave a servant CPU port unconnected in the SoC wiring."""
    alts = [
        (
            ".i_clk        (wb_clk),",
            ".i_clk        (),",
            "CPU clock left unconnected (no edges, firmware never runs)",
        ),
        (
            ".i_rst        (wb_rst),",
            ".i_rst        (),",
            "CPU reset left unconnected (floats, firmware never boots)",
        ),
    ]
    old, new, desc = alts[variant % len(alts)]
    _once(text, old, "serv_unconnected_port")
    return text.replace(old, new), {"variant_desc": desc}


def picorv32_reset_break(text, variant):
    """Break the test_ez reset: stuck in reset or re-asserted."""
    if variant % 2 == 0:
        old = "resetn <= 1;"
        _once(text, old, "picorv32_reset_break")
        new = "resetn <= 0;"
        desc = "reset stuck active (CPU never fetches, counter stays put)"
    else:
        old = "repeat (1000) @(posedge clk);"
        _once(text, old, "picorv32_reset_break")
        new = (
            "repeat (100) @(posedge clk); "
            "resetn <= 0; repeat (900) @(posedge clk);"
        )
        desc = "reset re-asserted after 100 cycles (run aborted early)"
    return text.replace(old, new), {"variant_desc": desc}


def picorv32_truncation(text, variant):
    """Narrow the ALU add path so the ez counter never reaches 10."""
    old = "alu_add_sub = instr_sub ? reg_op1 - reg_op2 : reg_op1 + reg_op2;"
    _once(text, old, "picorv32_truncation")
    alts = [
        (
            "alu_add_sub = instr_sub ? reg_op1 - reg_op2 : "
            "((reg_op1 + reg_op2) & 32'h00000007);",
            "ALU add masked to 3 bits (max 7)",
        ),
        (
            "alu_add_sub = instr_sub ? reg_op1 - reg_op2 : "
            "((reg_op1 + reg_op2) & 32'h00000003);",
            "ALU add masked to 2 bits (max 3)",
        ),
        (
            "alu_add_sub = instr_sub ? reg_op1 - reg_op2 : "
            "{29'b0, reg_op1[2:0] + reg_op2[2:0]};",
            "ALU add zero-extended from 3 bits (max 8)",
        ),
    ]
    new, desc = alts[variant % len(alts)]
    return text.replace(old, new), {"variant_desc": desc}


def picorv32_unconnected_port(text, variant):
    """Leave a picorv32 port unconnected in the ez bench wiring."""
    alts = [
        (
            ".clk         (clk        ),",
            ".clk         (),",
            "CPU clock left unconnected (no edges, trap unresolved)",
        ),
        (
            ".mem_rdata   (mem_rdata  )",
            ".mem_rdata   ()",
            "memory read data left unconnected (fetches unknown)",
        ),
    ]
    old, new, desc = alts[variant % len(alts)]
    _once(text, old, "picorv32_unconnected_port")
    return text.replace(old, new), {"variant_desc": desc}


def analog_sizing_out_of_spec(text, variant):
    """Move R2 off its 8k nominal so Vout leaves [1.199, 1.201] V."""
    old = "R2 out 0 8k"
    _once(text, old, "analog_sizing_out_of_spec")
    r2 = ["4k", "2k", "16k"][variant % 3]
    ohms = {"2k": 2000.0, "4k": 4000.0, "16k": 16000.0}[r2]
    expected_vout = 1.8 * ohms / (4000.0 + ohms)
    extra = {
        "variant_desc": f"R2 8k -> {r2} (divider ratio out of spec)",
        "resistor": r2,
        "expected_vout": expected_vout,
    }
    return text.replace(old, f"R2 out 0 {r2}"), extra


def analog_open_net(text, variant):
    """Open the divider: R2 lifted from `out`, which rises to the rail."""
    old = "R2 out 0 8k"
    _once(text, old, "analog_open_net")
    alts = [
        ("R2 out_open 0 8k", "R2 high side lifted onto out_open"),
        (
            "* R2 out 0 8k (MUTATE-HARNESS analog_open_net: device lifted)",
            "R2 commented out (device lifted)",
        ),
    ]
    new, desc = alts[variant % len(alts)]
    return text.replace(old, new), {"variant_desc": desc}


def layout_drc_violation(text, variant):
    """Shift or shrink a rect into an scmos DRC violation."""
    if variant % 2 == 0:
        old, new = "rect 6 0 9 3", "rect 4 0 7 3"
        rule, desc = "spacing", "second rect shifted left (1λ spacing)"
    else:
        old, new = "rect 0 0 3 3", "rect 0 0 1 5"
        rule, desc = "width", "first rect narrowed (1λ width)"
    _once(text, old, "layout_drc_violation")
    return text.replace(old, new), {"variant_desc": desc, "expected_rule": rule}


def netlist_lvs_mismatch(text, variant):
    """Rename one device bulk net on the schematic side only."""
    alts = [
        (
            "Y A VPWR VPB sky130_fd_pr__pfet_01v8_hvt",
            "Y A VPWR VPB_BAD sky130_fd_pr__pfet_01v8_hvt",
            "VPB_BAD",
            "pfet bulk VPB renamed to VPB_BAD",
        ),
        (
            "Y A VGND VNB sky130_fd_pr__nfet_01v8",
            "Y A VGND VNB_BAD sky130_fd_pr__nfet_01v8",
            "VNB_BAD",
            "nfet bulk VNB renamed to VNB_BAD",
        ),
    ]
    old, new, bad_net, desc = alts[variant % len(alts)]
    _once(text, old, "netlist_lvs_mismatch")
    return text.replace(old, new), {"variant_desc": desc, "bad_net": bad_net}


def _db(linear):
    return round(10.0 * math.log10(linear), 3)


def photonic_geometry_mistune(text, variant):
    """Lengthen the MZI bottom arm; cross-port transmission collapses.

    Expected values verified against sax 0.18.2 (in0 -> out1 @1550nm):
    +0.2 um -> 0.33972 (-4.689 dB), +0.4 um -> 0.10276 (-9.882 dB).
    """
    old = "s_bot: {component: straight, settings: {length: 10.0}}"
    _once(text, old, "photonic_geometry_mistune")
    delta, linear = [(0.2, 0.33972), (0.4, 0.10276)][variant % 2]
    new = (
        "s_bot: {component: straight, settings: "
        f"{{length: {10.0 + delta:.1f}}}}}"
    )
    extra = {
        "variant_desc": f"bottom arm lengthened by {delta} um",
        "arm_delta_um": delta,
        "expected_linear": linear,
        "expected_db": _db(linear),
    }
    return text.replace(old, new), extra


def photonic_circuit_mistune(text, variant):
    """Detune the output coupler; cross-port transmission drops.

    Expected value verified against sax 0.18.2 (in0 -> out1 @1550nm):
    coupling 0.1 -> 0.8 (-0.969 dB).
    """
    old = "c2: {component: coupler_ideal, settings: {coupling: 0.5}}"
    _once(text, old, "photonic_circuit_mistune")
    _ = variant
    linear = 0.8
    new = "c2: {component: coupler_ideal, settings: {coupling: 0.1}}"
    extra = {
        "variant_desc": "output coupler coupling 0.5 -> 0.1",
        "coupling": 0.1,
        "expected_linear": linear,
        "expected_db": _db(linear),
    }
    return text.replace(old, new), extra
