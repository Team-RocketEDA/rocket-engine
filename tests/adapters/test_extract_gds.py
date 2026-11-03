"""EXTRACT-GDS RED — run_extraction must accept GDS, not .mag-only.

Valid RED = `MagicExtractAdapter` refuses a GDS job (no `gds_file`
key: preflight raises invalid_reference for the missing .mag), so
every GDS test below fails. GREEN = the adapter stages the GDS,
reads it with `gds read` before `load`, and extracts the same
device complement as the .mag path. The .mag path stays proven by
`tests/adapters/test_extract_sky130.py` (untouched).

Known-good cell: sky130_fd_sc_hd__inv_2 from the registered PDK
(GDS lib + .mag + spice lib sliced to its subckt, all resolved via
resolve_deck so hashes are checked). Live tests skip (never
fake-green) where magic or the PDK decks are absent; preflight and
script-shape units use an injected runner and always run.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

CELL = "sky130_fd_sc_hd__inv_2"
TECH_REL = "libs.tech/magic/sky130A.tech"
GDS_LIB_REL = "libs.ref/sky130_fd_sc_hd/gds/sky130_fd_sc_hd.gds"
MAG_REL = "libs.ref/sky130_fd_sc_hd/mag/sky130_fd_sc_hd__inv_2.mag"
SPICE_LIB_REL = "libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice"

MAGIC_SAMPLE_STDOUT = """Magic 8.3 revision 685 - Compiled on Sun Oct 25 03:16:37 PM +04 2026.
Starting magic under Tcl interpreter
Using the terminal as the console.
Using NULL graphics device.
Using technology "sky130A", version 1.0.588-116-g5f09001
exttospice finished.
"""

magic_present = shutil.which("magic") is not None
needs_magic = pytest.mark.skipif(not magic_present, reason="magic not installed")


def _resolve_decks():
    try:
        from rocket_engine.interfaces.pdks import list_pdks, resolve_deck
        from rocket_engine.interfaces.paths import slugify
    except Exception:
        pytest.skip("pdk store unavailable")
    try:
        entries = list_pdks()
    except Exception:
        pytest.skip("sky130 PDK deck not registered (ROCKETEDA_HOME)")
    want_rev = os.environ.get("SKY130_PDK_REVISION")
    candidates = [
        e for e in entries if slugify(e.get("id") or "") == "sky130a"
    ]
    if want_rev:
        candidates = [e for e in candidates if e.get("revision") == want_rev]
    if not candidates:
        pytest.skip("sky130 PDK deck not registered (ROCKETEDA_HOME)")
    entry = sorted(candidates, key=lambda e: e["revision"])[0]
    decks = {}
    for key, rel in (
        ("tech", TECH_REL),
        ("gds_lib", GDS_LIB_REL),
        ("mag", MAG_REL),
        ("spice_lib", SPICE_LIB_REL),
    ):
        try:
            hit = resolve_deck(entry["id"], entry["revision"], rel)
        except Exception:
            pytest.skip(f"sky130 deck not resolved: {rel}")
        path = hit.get("path")
        if not path or not Path(path).is_file():
            pytest.skip(f"sky130 deck missing on disk: {rel}")
        decks[key] = path
    return decks


def _gds_job(decks, tmp_path, **over):
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    gds_file = workdir / "cells.gds"
    shutil.copy(decks["gds_lib"], gds_file)
    job = {
        "operation": "run_extraction",
        "cell": CELL,
        "gds_file": str(gds_file),
        "tech_file": decks["tech"],
        "workdir": str(workdir),
    }
    job.update(over)
    return job


class _FakeRunner:
    """Injected runner: records the Tcl script, answers tech probes."""

    def __init__(self, tech_banner='Using technology "sky130A"'):
        self.seen = {}
        self.tech_banner = tech_banner

    def run(self, command, workdir, timeout_s=120, extra_binds=(), input_text=None):
        self.seen["command"] = command
        self.seen["workdir"] = workdir
        self.seen["input_text"] = input_text
        return subprocess.CompletedProcess(command, 0, self.tech_banner, "")


def test_gds_preflight_accepts_gds_file_without_mag():
    from rocket_engine.adapters.extract_magic import MagicExtractAdapter

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        gds = Path(tmp) / "cells.gds"
        gds.write_bytes(b"fakegds")
        adapter = MagicExtractAdapter(runner=_FakeRunner())
        checked = adapter.preflight(
            {
                "operation": "run_extraction",
                "cell": CELL,
                "gds_file": str(gds),
                "tech": "sky130A",
                "workdir": tmp,
            }
        )
    assert checked["cell"] == CELL


def test_gds_and_mag_together_refuse_as_ambiguous():
    from rocket_engine.adapters.extract_magic import MagicExtractAdapter

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        gds = Path(tmp) / "cells.gds"
        gds.write_bytes(b"fakegds")
        mag = Path(tmp) / (CELL + ".mag")
        mag.write_text("magictimestamp 1\n")
        adapter = MagicExtractAdapter(runner=_FakeRunner())
        try:
            adapter.preflight(
                {
                    "operation": "run_extraction",
                    "cell": CELL,
                    "cell_file": str(mag),
                    "gds_file": str(gds),
                    "tech": "sky130A",
                    "workdir": tmp,
                }
            )
        except Exception as exc:
            assert getattr(exc, "code", None) == "invalid_command"
        else:
            raise AssertionError("expected invalid_command for cell_file + gds_file")


def test_gds_missing_file_refuses_invalid_reference():
    from rocket_engine.adapters.extract_magic import MagicExtractAdapter

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        adapter = MagicExtractAdapter(runner=_FakeRunner())
        try:
            adapter.preflight(
                {
                    "operation": "run_extraction",
                    "cell": CELL,
                    "gds_file": str(Path(tmp) / "no-such.gds"),
                    "tech": "sky130A",
                    "workdir": tmp,
                }
            )
        except Exception as exc:
            assert getattr(exc, "code", None) == "invalid_reference"
        else:
            raise AssertionError("expected invalid_reference for a missing GDS")


def test_gds_tcl_unsafe_path_refuses_invalid_command():
    from rocket_engine.adapters.extract_magic import MagicExtractAdapter

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        adapter = MagicExtractAdapter(runner=_FakeRunner())
        try:
            adapter.preflight(
                {
                    "operation": "run_extraction",
                    "cell": CELL,
                    "gds_file": str(Path(tmp) / "evil}.gds"),
                    "tech": "sky130A",
                    "workdir": tmp,
                }
            )
        except Exception as exc:
            assert getattr(exc, "code", None) == "invalid_command"
        else:
            raise AssertionError("expected invalid_command for a Tcl-unsafe GDS path")


def test_gds_script_reads_gds_before_load(tmp_path):
    from rocket_engine.adapters.extract_magic import MagicExtractAdapter

    runner = _FakeRunner()
    adapter = MagicExtractAdapter(runner=runner)
    gds = tmp_path / "cells.gds"
    gds.write_bytes(b"fakegds")
    proc = adapter._run_gds("sky130A", str(gds), CELL, str(tmp_path))
    assert proc.returncode == 0
    script = runner.seen["input_text"]
    assert "gds read" in script
    assert script.index("gds read") < script.index(f"load {CELL}")
    assert "ext2spice" in script


def test_gds_parse_devices_matches_mag_shape():
    from rocket_engine.adapters.extract_magic import MagicExtractAdapter

    gds_spice = (
        "* NGSPICE file created from sky130_fd_sc_hd__inv_2.ext - technology: sky130A\n"
        "\n"
        f".subckt {CELL} A Y VPB VNB VPWR VGND\n"
        "X0 Y A VPWR VPB sky130_fd_pr__pfet_01v8_hvt w=1 l=0.15\n"
        "X1 VGND A Y VNB sky130_fd_pr__nfet_01v8 w=0.65 l=0.15\n"
        "X2 Y A VGND VNB sky130_fd_pr__nfet_01v8 w=0.65 l=0.15\n"
        "X3 VPWR A Y VPB sky130_fd_pr__pfet_01v8_hvt w=1 l=0.15\n"
        ".ends\n"
    )
    result = MagicExtractAdapter().parse(
        {"stdout": MAGIC_SAMPLE_STDOUT, "spice_text": gds_spice}
    )
    assert result["device_count"] == 4
    assert result["violations"] == []
    assert {d["l"] for d in result["devices"]} == {0.15}


@needs_magic
def test_gds_extract_inv2_matches_mag_complement(tmp_path):
    from rocket_engine.adapters.extract_magic import MagicExtractAdapter

    decks = _resolve_decks()
    adapter = MagicExtractAdapter()
    native_gds = adapter.execute(_gds_job(decks, tmp_path))
    assert Path(native_gds["spice_file"]).is_file()
    result_gds = adapter.parse(native_gds)
    assert result_gds["device_count"] == 4
    assert result_gds["violations"] == []

    workdir = tmp_path / "magwork"
    workdir.mkdir(exist_ok=True)
    cell_file = workdir / f"{CELL}.mag"
    shutil.copy(decks["mag"], cell_file)
    native_mag = adapter.execute(
        {
            "operation": "run_extraction",
            "cell": CELL,
            "cell_file": str(cell_file),
            "tech_file": decks["tech"],
            "workdir": str(workdir),
        }
    )
    result_mag = adapter.parse(native_mag)
    key = lambda d: (d["name"], tuple(d["nets"]), d["class"], d["w"], d["l"])  # noqa: E731
    assert sorted(key(d) for d in result_gds["devices"]) == sorted(
        key(d) for d in result_mag["devices"]
    )
