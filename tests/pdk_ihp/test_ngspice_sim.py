"""PDK-IHP RED — ngspice sims: passive divider + SiGe HBT op point.

Valid RED = profile missing (FileNotFoundError) or ngspice/IHP
model tree unavailable (loud skip). GREEN runs stock ngspice-42
batch DC operating points against the wrapper's own corner libs:
a ptap1 divider (v(mid) = 0.9 V) and an npn13G2 VBIC device at
Vbe = 0.85 V / Vce = 1.0 V (Ic = 577 uA golden). MOS/resistor
compact models need Verilog-A modules stock ngspice lacks — the
profile records that as an honest n/a, not a promise.
"""

import re
import shutil
import subprocess

import pytest

from ._profile import require_ihp_root, load_profile

ngspice_present = shutil.which("ngspice") is not None
needs_ng = pytest.mark.skipif(
    not ngspice_present, reason="ngspice binary not on PATH"
)

# Goldens captured with ngspice-42 (KLU build) on the pinned libs.
DIV_MID_V = 0.9
DIV_VDD_V = 1.8
HBT_IC_A = -5.76845e-04
HBT_VB_V = 0.85


def _models_dir():
    profile = load_profile()  # RED: missing profile.yaml
    root = require_ihp_root()
    rel = profile["variants"]["bicmos"]["models"]["ngspice_dir"]
    models = root / rel
    assert models.is_dir()
    return profile, models


def _run_deck(deck_text, models_dir, tmp_path, name):
    deck = tmp_path / name
    deck.write_text(deck_text)
    log = tmp_path / (name + ".log")
    proc = subprocess.run(
        ["ngspice", "-b", "-o", str(log), str(deck)],
        cwd=str(models_dir),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    text = log.read_text()
    assert "Simulation interrupted" not in text, text[-2000:]
    return text


def _parse_prints(text):
    return {m.group(1): float(m.group(2)) for m in re.finditer(r"(?m)^(\S+)\s*=\s*(\S+)", text)}


@needs_ng
def test_ptap1_divider_dc_op(tmp_path):
    profile, models = _models_dir()  # RED: missing profile.yaml
    corner = profile["variants"]["bicmos"]["models"]["corners"]["res_typ"]
    deck = (
        "* IHP SG13G2 ptap1 divider (lane proof)\n"
        f".lib {corner['file']} {corner['section']}\n"
        "VDD vdd 0 DC 1.8\n"
        "Xt1 vdd mid ptap1 R=1000\n"
        "Xt2 mid 0 ptap1 R=1000\n"
        ".op\n.control\nop\nprint v(mid) v(vdd)\n.endc\n.end\n"
    )
    values = _parse_prints(_run_deck(deck, models, tmp_path, "ptap_div.cir"))
    assert values["v(mid)"] == pytest.approx(DIV_MID_V, abs=1e-9)
    assert values["v(vdd)"] == pytest.approx(DIV_VDD_V, abs=1e-9)


@needs_ng
def test_npn13g2_hbt_dc_op(tmp_path):
    profile, models = _models_dir()  # RED: missing profile.yaml
    corner = profile["variants"]["bicmos"]["models"]["corners"]["hbt_typ"]
    deck = (
        "* IHP SG13G2 npn13G2 op point (lane proof)\n"
        f".lib {corner['file']} {corner['section']}\n"
        "VCC c 0 DC 1.0\n"
        "VBB b 0 DC 0.85\n"
        "Xhbt c b 0 0 npn13G2 Nx=1\n"
        ".op\n.control\nop\nprint i(VCC) v(b)\n.endc\n.end\n"
    )
    values = _parse_prints(_run_deck(deck, models, tmp_path, "hbt_op.cir"))
    assert values["v(b)"] == pytest.approx(HBT_VB_V, abs=1e-9)
    assert values["i(vcc)"] == pytest.approx(HBT_IC_A, rel=1e-4)
