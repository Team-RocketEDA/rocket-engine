"""PDK-ASAP7 cell inventory: Verilog/LEF/techlef/LIB goldens (stdlib + 7z).

Proves the 7.5-track library census without any EDA flow tool:
per-group Verilog module counts, LEF macro counts, the exact
Verilog⊆LEF cross-check (+ the 10 named physical-only cells),
the tech-LEF layer list, the compressed LIB archive census, and
one real LIB extraction (tiny TBUF NLDM → 1 cell, 0.7 V).
"""

import re
import subprocess

from ._profile import find_lib_root, load_profile, require_tool

GROUP_COUNTS = {
    "AO": 42,
    "INVBUF": 37,
    "OA": 34,
    "SEQ": 33,
    "SIMPLE": 56,
    "TBUF": 1,
}
VTS = ["LVT", "RVT", "SLVT", "SRAM"]

PHYSICAL_ONLY_R = [
    "DECAPx1_ASAP7_75t_R",
    "DECAPx2_ASAP7_75t_R",
    "DECAPx2b_ASAP7_75t_R",
    "DECAPx4_ASAP7_75t_R",
    "DECAPx6_ASAP7_75t_R",
    "DECAPx10_ASAP7_75t_R",
    "FILLER_ASAP7_75t_R",
    "FILLERxp5_ASAP7_75t_R",
    "TAPCELL_ASAP7_75t_R",
    "TAPCELL_WITH_FILLER_ASAP7_75t_R",
]

HEADLINE_CELLS_R = [
    "INVx1_ASAP7_75t_R",
    "BUFx2_ASAP7_75t_R",
    "NAND2x1_ASAP7_75t_R",
    "DFFHQNx1_ASAP7_75t_R",
    "TBUFx1_ASAP7_75t_R",
]

TECHLEF_LAYERS = [
    "nwell", "pwell", "Gate", "Active",
    "V0", "M1", "V1", "M2", "V2", "M3", "V3", "M4",
    "V4", "M5", "V5", "M6", "V6", "M7", "V7", "M8",
    "V8", "M9", "V9", "Pad",
]


def _verilog_modules(path):
    mods = []
    for line in path.read_text().splitlines():
        m = re.match(r"module\s+([A-Za-z0-9_]+)", line)
        if m:
            mods.append(m.group(1))
    return mods


def _lef_macros(path):
    return [
        line.split()[1]
        for line in path.read_text().splitlines()
        if line.startswith("MACRO ")
    ]


def test_verilog_group_counts_and_total():
    load_profile()  # RED: missing profile.yaml
    root = find_lib_root()
    assert root is not None, "asap7 lib tree unavailable"
    total = 0
    files = sorted((root / "Verilog").glob("*.v"))
    assert len(files) == 24
    for path in files:
        group = path.name.split("_")[1]
        mods = _verilog_modules(path)
        assert len(mods) == GROUP_COUNTS[group], path.name
        total += len(mods)
    assert total == 812


def test_verilog_headline_cells_present():
    load_profile()  # RED: missing profile.yaml
    root = find_lib_root()
    assert root is not None, "asap7 lib tree unavailable"
    names = set()
    for path in (root / "Verilog").glob("*RVT*.v"):
        names.update(_verilog_modules(path))
    assert len(names) == 203
    for cell in HEADLINE_CELLS_R:
        assert cell in names, cell


def test_lef_macro_counts():
    load_profile()  # RED: missing profile.yaml
    root = find_lib_root()
    assert root is not None, "asap7 lib tree unavailable"
    files = sorted((root / "LEF").glob("*.lef"))
    assert len(files) == 4
    for path in files:
        assert len(_lef_macros(path)) == 213, path.name


def test_lef_verilog_cross_rvt_exact():
    load_profile()  # RED: missing profile.yaml
    root = find_lib_root()
    assert root is not None, "asap7 lib tree unavailable"
    verilog = set()
    for path in (root / "Verilog").glob("*RVT*.v"):
        verilog.update(_verilog_modules(path))
    lef = set(_lef_macros(root / "LEF" / "asap7sc7p5t_28_R_1x_220121a.lef"))
    assert verilog <= lef, sorted(verilog - lef)
    assert sorted(lef - verilog) == sorted(PHYSICAL_ONLY_R)


def test_techlef_layer_list():
    load_profile()  # RED: missing profile.yaml
    root = find_lib_root()
    assert root is not None, "asap7 lib tree unavailable"
    profile = load_profile()
    techlef = root / profile["variants"]["sc7p5t_28"]["tech"]["techlef"]
    layers = [
        line.split()[1]
        for line in techlef.read_text().splitlines()
        if line.startswith("LAYER ")
    ]
    assert layers == TECHLEF_LAYERS


def test_lib_archive_census():
    load_profile()  # RED: missing profile.yaml
    root = find_lib_root()
    assert root is not None, "asap7 lib tree unavailable"
    nldm = sorted((root / "LIB" / "NLDM").glob("*.lib.7z"))
    ccs = sorted((root / "LIB" / "CCS").glob("*.lib.7z"))
    # NLDM also carries an uncompressed IO_cell/ subdir (inventoried,
    # not part of the archive census).
    assert (root / "LIB" / "NLDM" / "IO_cell").is_dir()
    assert len(nldm) == 73
    assert len(ccs) == 218
    pat = re.compile(
        r"asap7sc7p5t_[A-Z]+\_(LVT|RVT|SLVT|SRAM)\_(TT|SS|FF)\_"
        r"(nldm|ccs|ccsa|ccsn)_\d+\.lib\.7z"
    )
    for arc in nldm + ccs:
        assert pat.fullmatch(arc.name), arc.name


def test_lib_archives_are_single_entry():
    load_profile()  # RED: missing profile.yaml
    root = find_lib_root()
    assert root is not None, "asap7 lib tree unavailable"
    seven_z = require_tool("7z")
    for rel in (
        "LIB/NLDM/asap7sc7p5t_SIMPLE_RVT_TT_nldm_211120.lib.7z",
        "LIB/NLDM/asap7sc7p5t_TBUF_RVT_TT_nldm_260831.lib.7z",
    ):
        proc = subprocess.run(
            [seven_z, "l", str(root / rel)],
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        assert "1 files" in proc.stdout
        want = rel.rsplit("/", 1)[1][: -len(".7z")]
        assert want in proc.stdout


def test_lib_extract_tbuf_single_cell():
    load_profile()  # RED: missing profile.yaml
    root = find_lib_root()
    assert root is not None, "asap7 lib tree unavailable"
    seven_z = require_tool("7z")
    import tempfile

    arc = root / "LIB/NLDM/asap7sc7p5t_TBUF_RVT_TT_nldm_260831.lib.7z"
    with tempfile.TemporaryDirectory(prefix="asap7lane_") as tmp:
        proc = subprocess.run(
            [seven_z, "x", f"-o{tmp}", "-y", str(arc)],
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        libs = list(__import__("pathlib").Path(tmp).glob("*.lib"))
        assert len(libs) == 1
        text = libs[0].read_text()
    cells = re.findall(r"cell\s+\(([A-Za-z0-9_]+)\)", text)
    assert cells == ["TBUFx1_ASAP7_75t_R"]
    assert "nom_voltage : 0.7" in text
