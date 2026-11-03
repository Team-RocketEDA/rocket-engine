"""PDK-SKY130GF RED — KLayout tech install proof for the pip package.

Valid RED = the lane profile is missing, so every proof fails on
FileNotFoundError. GREEN links the shipped klayout/ tech dir into
a scratch HOME (the real ~/.klayout is never touched) and proves
the `sky130` technology resolves in KLayout batch. Tests skip
(never fake-green) where klayout or the pip package is absent.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from ._profile import load_profile, sky130_root

TECH_PROBE = """import pya
names = list(pya.Technology.technology_names())
print("TECHS:", names)
print("HAS_SKY130:", "sky130" in names)
"""

klayout_present = shutil.which("klayout") is not None
needs_klayout = pytest.mark.skipif(
    not klayout_present, reason="klayout not installed"
)


def _require_tech():
    profile = load_profile()  # RED: missing profile.yaml
    root = sky130_root()
    if root is None:
        pytest.skip("sky130 pip package not installed (see recipe.md)")
    tech = profile["variants"]["sky130"]["tech"]
    klayout_dir = root / tech["klayout_dir"]
    assert klayout_dir.is_dir()
    return tech, klayout_dir


def test_tech_names_sky130():
    tech, _ = _require_tech()
    assert tech["tech_name"] == "sky130"


@needs_klayout
def test_klayout_tech_link_resolves(tmp_path):
    _, klayout_dir = _require_tech()
    fakehome = tmp_path / "fakehome"
    tech_home = fakehome / ".klayout" / "tech"
    tech_home.mkdir(parents=True)
    (tech_home / "sky130gf").symlink_to(klayout_dir)
    probe = tmp_path / "probe_tech.py"
    probe.write_text(TECH_PROBE)
    env = dict(os.environ)
    env["HOME"] = str(fakehome)
    proc = subprocess.run(
        ["klayout", "-b", "-r", str(probe)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=tmp_path,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert "HAS_SKY130: True" in proc.stdout


@needs_klayout
def test_shipped_lyd25_is_not_a_batch_deck(tmp_path):
    # Honesty guard: the only deck-like file in the pip package is a
    # d25 GUI macro. It must NOT be mistaken for a runnable batch
    # deck — batch execution fails, so the profile keeps deck: null
    # and DRC authority stays with the sky130A tree.
    profile = load_profile()  # RED: missing profile.yaml
    root = sky130_root()
    if root is None:
        pytest.skip("sky130 pip package not installed (see recipe.md)")
    tech = profile["variants"]["sky130"]["tech"]
    lyd25 = root / tech["d25"]
    assert lyd25.is_file()
    assert profile["variants"]["sky130"]["drc"]["deck"] is None
    gds = Path(__file__).parent / "fixtures" / "nfet_01v8.gds"
    if not gds.is_file():
        pytest.skip("lane fixture not landed yet (RED)")
    proc = subprocess.run(
        [
            "klayout",
            "-b",
            "-rd",
            f"input={gds}",
            "-rd",
            f"report={tmp_path / 'out.lyrdb'}",
            "-r",
            str(lyd25),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=tmp_path,
    )
    assert proc.returncode != 0
    assert "2.5d" in (proc.stdout + proc.stderr).lower()
