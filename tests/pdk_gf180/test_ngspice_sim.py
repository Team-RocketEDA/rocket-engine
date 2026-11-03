"""PDK-GF180 RED — lane proof: ngspice inverter sim with goldens.

Valid RED = the lane profile does not exist yet, so the proof
fails on FileNotFoundError before touching ngspice. GREEN builds
an inverter netlist from the profile's model relpaths (same W/L
as the layout fixture: Wn/L = 0.5/0.28 um, Wp/L = 1.0/0.28 um),
runs a DC sweep on ngspice, and pins the transfer goldens: rail
at both ends plus the switching window. The include strategy
adapts to the provision path (corner wrappers exist in the
post-release source tree only). Skips LOUDLY (never fake-green)
where ngspice or the PDK is absent.
"""

import re
import shutil
import subprocess

import pytest

from ._profile import load_profile, pdk_root, require_pdk

ROW_RE = re.compile(r"^\s*\d+\s+(\S+)\s+(\S+)\s*$")


def _include_lines(root, models):
    """Model include lines for whichever provision path resolved."""
    ngspice_dir = root / models["dir"]
    wrapper = ngspice_dir / "fets.lib"
    vendor = ngspice_dir / "sm141064.ngspice"
    if wrapper.is_file():
        return [f".lib '{wrapper}' typical"]
    return [
        ".param sw_stat_global=0 sw_stat_mismatch=0",
        ".param mc_skew=3 res_mc_skew=3 cap_mc_skew=3 fnoicor=0",
        f".lib '{vendor}' typical",
    ]


def _run_sweep(models, tmp_path):
    root = pdk_root()
    lines = [
        "* gf180 lane inverter (typical corner)",
        *_include_lines(root, models),
        "VDD vdd 0 3.3",
        "VIN in 0 0",
        "XM1 out in 0 0 nmos_3p3 w=0.5u l=0.28u",
        "XM2 out in vdd vdd pmos_3p3 w=1.0u l=0.28u",
        ".DC VIN 0 3.3 0.33",
        ".control",
        "run",
        "print v(out)",
        ".endc",
        ".end",
        "",
    ]
    netlist = tmp_path / "lane_inv.cir"
    netlist.write_text("\n".join(lines))
    proc = subprocess.run(
        ["ngspice", "-b", str(netlist)],
        capture_output=True, text=True, timeout=300, cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    sweep = []
    for line in proc.stdout.splitlines():
        match = ROW_RE.match(line)
        if match:
            sweep.append((float(match.group(1)), float(match.group(2))))
    assert len(sweep) == 11, proc.stdout[-2000:]
    return sweep


def test_lane_ngspice_inverter_matches_goldens(tmp_path):
    profile = load_profile()  # RED: missing profile.yaml
    require_pdk()  # skip LOUDLY when gf180mcu is truly absent
    if shutil.which("ngspice") is None:
        pytest.skip("gf180 lane live: ngspice not installed")
    goldens = profile["proofs"]["sim"]
    sweep = _run_sweep(profile["variants"]["mcu"]["models"], tmp_path)
    assert sweep[0][1] == pytest.approx(goldens["vout_at_0V"], abs=1e-3)
    assert sweep[-1][1] == pytest.approx(goldens["vout_at_3p3V"], abs=1e-3)
    low, high = goldens["threshold_window_V"]
    below = [vin for vin, vout in sweep if vout > 2.0]
    above = [vin for vin, vout in sweep if vout < 1.0]
    assert below and max(below) <= low + 1e-9
    assert above and min(above) >= high - 1e-9
