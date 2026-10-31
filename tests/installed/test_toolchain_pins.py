"""PROV phase-1 installed asserts — pins on the real host.

B10 gate suite: version-asserts the provisioned toolchain on the
machine under test (Ubuntu 24.04 on the gate). Pins are parsed
from `scripts/provision_toolchain.sh` (single source), so the
asserter cannot drift from the provisioner.

Absent tool on a dev box: loud skip naming the tool, the remedy,
and the gate command — the absence is still enforced by the
provisioner verdict (see test_provisioner_verdict_consistent)
and by the hermetic suite. Absent tool with PROV_GATE=1 (gate
host): hard fail. A present tool with a wrong version always
fails, on every host. Nothing here asserts "installed" for a
tool that is not there: that would be fake-green.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
PROV = ROOT / "scripts" / "provision_toolchain.sh"


def read_pins():
    """Pin values parsed from the provisioner (single source)."""
    text = PROV.read_text()
    pins = {}
    for name in ("OSS_CAD_SUITE_PIN", "LIBRELANE_PIN", "OPENSTA_PIN",
                 "YOSYS_EXPECT", "SBY_EXPECT"):
        match = re.search(rf'^{name}="([^"]+)"', text, re.M)
        assert match, f"{name} not pinned in provisioner"
        pins[name] = match.group(1)
    return pins


def dev_path():
    """Dev-PATH with the bundle + tools bins first (never bare PATH)."""
    tools = Path(os.environ.get("TOOLS_DIR",
                                str(Path.home() / "tools")))
    bundle = Path(os.environ.get(
        "OSS_CAD_SUITE_DIR", str(tools / "oss-cad-suite")))
    return (str(bundle / "bin") + os.pathsep + str(tools / "bin")
            + os.pathsep + os.environ.get("PATH", ""))


def tools_dir():
    return Path(os.environ.get("TOOLS_DIR",
                                str(Path.home() / "tools")))


def bundle_dir():
    return Path(os.environ.get(
        "OSS_CAD_SUITE_DIR", str(tools_dir() / "oss-cad-suite")))


def absent(tool, remedy):
    """Loud skip on dev, hard fail on the gate (PROV_GATE=1)."""
    if os.environ.get("PROV_GATE") == "1":
        pytest.fail(f"{tool} absent on gate host: {remedy}")
    pytest.skip(f"{tool} absent on this host (gate: PROV_GATE=1 "
                f"pytest tests/installed): {remedy}")


def run(binary, *args, timeout=60):
    env = dict(os.environ)
    env["PATH"] = dev_path()
    return subprocess.run(
        [binary, *args], capture_output=True, text=True,
        timeout=timeout, env=env, cwd=ROOT,
    )


def test_oss_cad_suite_version_pin():
    pins = read_pins()
    version_file = bundle_dir() / "VERSION"
    if not version_file.is_file():
        absent("oss-cad-suite",
               "run scripts/provision_toolchain.sh --install "
               "(pinned tarball "
               f"{pins['OSS_CAD_SUITE_PIN']}); see "
               "https://github.com/YosysHQ/oss-cad-suite-build/"
               "releases")
    got = version_file.read_text().strip()
    assert got == pins["OSS_CAD_SUITE_PIN"], \
        f"bundle {got} != pin {pins['OSS_CAD_SUITE_PIN']}"


def test_yosys_banner_pin():
    pins = read_pins()
    if shutil.which("yosys", path=dev_path()) is None:
        absent("yosys", "provision the pinned oss-cad-suite bundle: "
               "scripts/provision_toolchain.sh --install")
    proc = run("yosys", "-V")
    banner = (proc.stdout + proc.stderr).splitlines()
    assert banner, "yosys -V printed nothing"
    assert banner[0].startswith(pins["YOSYS_EXPECT"]), banner[0]


def test_sby_banner_pin():
    pins = read_pins()
    if shutil.which("sby", path=dev_path()) is None:
        absent("sby", "provision the pinned oss-cad-suite bundle: "
               "scripts/provision_toolchain.sh --install")
    proc = run("sby", "--version")
    banner = (proc.stdout + proc.stderr).splitlines()
    assert banner, "sby --version printed nothing"
    assert banner[0].startswith(pins["SBY_EXPECT"]), banner[0]


def test_librelane_appimage_pin():
    pins = read_pins()
    appdir = tools_dir() / f"librelane-{pins['LIBRELANE_PIN']}"
    appimage = appdir / "librelane-devshell-x86_64.AppImage"
    pinfile = appdir / "LIBRELANE_PIN"
    remedy = ("run scripts/provision_toolchain.sh --install "
              "(pinned AppImage per "
              "https://librelane.readthedocs.io/en/stable/"
              "installation/appimage_installation/"
              "installation_linux.html)")
    if not appimage.is_file() or not os.access(appimage, os.X_OK):
        absent("librelane", remedy)
    assert pinfile.is_file(), f"{pinfile} missing: {remedy}"
    assert pinfile.read_text().strip() == pins["LIBRELANE_PIN"]
    assert (appdir / "tool_versions.txt").is_file(), \
        "tool_versions.txt missing: re-run the provisioner"
    if shutil.which("librelane", path=dev_path()) is not None:
        proc = run("librelane", "--version")
        first = (proc.stdout + proc.stderr).splitlines()
        assert first and pins["LIBRELANE_PIN"] in first[0], first


def test_opensta_prefix_pin():
    pins = read_pins()
    short = pins["OPENSTA_PIN"][:7]
    prefix = tools_dir() / f"opensta-{short}"
    sta = prefix / "bin" / "sta"
    pinfile = prefix / "OPENSTA_PIN"
    remedy = ("run scripts/provision_toolchain.sh --install "
              "(pinned source build per "
              "https://github.com/The-OpenROAD-Project/OpenSTA)")
    if not sta.is_file() or not os.access(sta, os.X_OK):
        absent("opensta", remedy)
    assert pinfile.is_file(), f"{pinfile} missing: {remedy}"
    assert pinfile.read_text().strip() == pins["OPENSTA_PIN"]
    proc = subprocess.run(
        [str(sta), "-version"], capture_output=True, text=True,
        timeout=60, cwd=ROOT,
    )
    if proc.returncode != 0:
        proc = subprocess.run(
            [str(sta), "--version"], capture_output=True, text=True,
            timeout=60, cwd=ROOT,
        )
    assert proc.returncode == 0, proc.stderr
    assert (proc.stdout + proc.stderr).strip(), \
        "sta printed no version"


def test_provisioner_verdict_consistent():
    proc = subprocess.run(
        ["bash", str(PROV), "--check-only"],
        capture_output=True, text=True, timeout=120, cwd=ROOT,
    )
    assert proc.returncode in (0, 1), proc.stdout + proc.stderr
    assert "PROV-PHASE1:" in proc.stdout, proc.stdout
    if proc.returncode == 0:
        assert "(4/4" in proc.stdout, proc.stdout
    else:
        assert "DEGRADED" in proc.stdout, proc.stdout
        assert "REMEDY" in proc.stdout, proc.stdout
