"""PROV phase-1 RED — to-GDS toolchain provisioner.

Tests assume `scripts/provision_toolchain.sh` with `--check-only`
(assert ambient, no writes, no network), `--install` (attempt
installs where network allows, else loud remedy), and usage exit
2. Valid RED = the provisioner does not exist yet.

Policy under test (docs/tickets/PROV.md + BUILD-LOCAL):
  phase 1 (oss-cad-suite pin, LibreLane AppImage, OpenSTA)
  plus phase 2 (rest of the matrix), version asserts
  everywhere, loud remedies where install is impossible.
  Offline degrades to version-asserted ambient + loud
  remedy, never fake-green. GTKWave is EXCLUDED by the
  headless rule (recorded, never installed). Palace stays
  UNSOURCED. --print-path emits the idempotent shell block
  behind the installer "add to PATH" flag.
"""

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROV = ROOT / "scripts" / "provision_toolchain.sh"
BASH = shutil.which("bash") or "bash"

YOSYS_BANNER = "Yosys 0.70+219 (git sha1 5053d0e26, stub)"
SBY_BANNER = "SBY v0.70-9-g79fc9ed (stub)"
LIBRELANE_VERSION = "3.0.17"
STA_BANNER = "OpenSTA 2.0 stub (proves liveness, pin is the hash)"


def run_prov(args, env_over=None, timeout=60):
    env = dict(os.environ)
    if env_over:
        env.update(env_over)
    return subprocess.run(
        [BASH, str(PROV), *args],
        capture_output=True, text=True, timeout=timeout,
        env=env, cwd=ROOT,
    )


def read_pins():
    """Pin values parsed from the provisioner (single source)."""
    text = PROV.read_text()
    pins = {}
    for name in (
        "OSS_CAD_SUITE_PIN", "LIBRELANE_PIN", "OPENSTA_PIN",
        "MAGIC_REF", "NETGEN_REF", "KLAYOUT_PIN", "NGSPICE_PIN",
        "XYCE_REF", "TRILINOS_REF", "XSCHEM_REF", "CACE_PIN",
        "PYMEEP_PIN", "OPENEMS_REF", "CSXCAD_REF", "DEVSIM_PIN",
    ):
        pattern = rf'^{name}="([^"]+)"'
        match = re.search(pattern, text, re.M)
        assert match, f"{name} not pinned in provisioner"
        pins[name] = match.group(1)
    return pins


def _stub(path, body):
    path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
    path.chmod(0o755)


def _bindir(tmp_path, yosys=YOSYS_BANNER, sby=SBY_BANNER):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    _stub(bindir / "yosys", f"echo '{yosys}'")
    _stub(bindir / "sby", f"echo '{sby}'")
    _stub(bindir / "librelane", f"echo '{LIBRELANE_VERSION}'")
    _stub(bindir / "sta", f"echo '{STA_BANNER}'")
    _phase2_bin_stubs(bindir)
    return bindir


def _phase2_bin_stubs(bindir):
    _stub(bindir / "magic", "echo '8.3.685'")
    _stub(bindir / "netgen", "echo 'Netgen 1.5.326 stub'")
    _stub(bindir / "klayout", "echo 'KLayout 0.30.12'")
    _stub(bindir / "ngspice", "echo 'ngspice-47'")
    _stub(bindir / "Xyce", "echo 'Xyce Release 7.10.0 stub'")
    _stub(bindir / "xschem", "echo 'XSCHEM V3.5.0 stub'")
    _stub(bindir / "openEMS", "echo 'openEMS 0.37.0 stub'")
    _stub(bindir / "ElmerSolver", "echo 'ElmerSolver 9.0 stub'")


def _prov_python(tmp_path, pins):
    """Stub interpreter answering metadata queries with the pins."""
    pydir = tmp_path / "pydir"
    pydir.mkdir(exist_ok=True)
    stub = pydir / "python"
    _stub(stub,
           "case \"$*\" in "
           f"*cace*) echo '{pins['CACE_PIN']}';; "
           f"*devsim*) echo '{pins['DEVSIM_PIN']}';; "
           "*) exit 1;; esac")
    return stub


def _pymeep_env(tools, pins):
    """Stub conda pymeep interpreter at the expected prefix path."""
    pydir = tools / "miniforge3" / "envs" / "pymeep" / "bin"
    pydir.mkdir(parents=True, exist_ok=True)
    _stub(pydir / "python",
           f"echo '{pins['PYMEEP_PIN']}'")
    return pydir / "python"


def _bundle(tmp_path, version="20261025", with_bins=False):
    bundle = tmp_path / "oss-cad-suite"
    bundle.mkdir(exist_ok=True)
    (bundle / "VERSION").write_text(version + "\n", encoding="utf-8")
    if with_bins:
        bindir = bundle / "bin"
        bindir.mkdir(exist_ok=True)
        _stub(bindir / "yosys", f"echo '{YOSYS_BANNER}'")
        _stub(bindir / "sby", f"echo '{SBY_BANNER}'")
    return bundle


def _sysbin(tmp_path):
    """Minimal system utils so stub-only PATH stays hermetic."""
    sysbin = tmp_path / "sysbin"
    sysbin.mkdir(exist_ok=True)
    for name in ("head", "cut", "tr", "grep", "mkdir", "id"):
        src = shutil.which(name)
        assert src, f"system {name} missing"
        link = sysbin / name
        if not link.exists():
            link.symlink_to(src)
    return sysbin


def _env(tmp_path, bindir, bundle):
    empty_home = tmp_path / "home"
    empty_home.mkdir(exist_ok=True)
    path = str(bindir) + os.pathsep + str(_sysbin(tmp_path))
    return {
        "PATH": path,
        "HOME": str(empty_home),
        "OSS_CAD_SUITE_DIR": str(bundle),
        "TOOLS_DIR": str(empty_home / "tools"),
    }


def test_provisioner_exists_and_executable():
    assert PROV.is_file(), "scripts/provision_toolchain.sh missing"
    assert os.access(PROV, os.X_OK), "provisioner not executable"


def test_provisioner_unknown_mode_prints_usage():
    proc = run_prov(["--bogus"])
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "usage" in proc.stderr.lower(), proc.stderr


def test_provisioner_cites_upstream_docs():
    text = PROV.read_text()
    for url in (
        "librelane.readthedocs.io/en/stable/installation",
        "appimage_installation/installation_linux.html",
        "nix_installation/installation_linux.html",
        "github.com/The-OpenROAD-Project/OpenSTA",
        "github.com/YosysHQ/oss-cad-suite-build/releases",
    ):
        assert url in text, url


def test_provisioner_pins_are_expected_values():
    pins = read_pins()
    assert pins["OSS_CAD_SUITE_PIN"] == "20261025"
    assert pins["LIBRELANE_PIN"] == "3.0.17"
    assert pins["OPENSTA_PIN"] == \
        "857316ff001b2a8dbbdc5996944d08a6d38c87ab"
    assert pins["MAGIC_REF"] == \
        "707d67e6c66e10fedf1efa7e2930017032ff6716"
    assert pins["NETGEN_REF"] == \
        "e310f3049e1f07c02d77aa509742ebc04b24f808"
    assert pins["KLAYOUT_PIN"] == "0.30.12"
    assert pins["NGSPICE_PIN"] == "47"
    assert pins["XYCE_REF"] == "Release-7.10.0"
    assert pins["TRILINOS_REF"] == "trilinos-release-17-2-1"
    assert pins["XSCHEM_REF"] == \
        "7811010c934a93b14ed07cbf2afd217fb2058ee6"
    assert pins["CACE_PIN"] == "2.13.0"
    assert pins["PYMEEP_PIN"] == "1.35.0"
    assert pins["OPENEMS_REF"] == "v0.37.0"
    assert pins["CSXCAD_REF"] == "v0.7.0"
    assert pins["DEVSIM_PIN"] == "2.11.2"


def test_downloads_retry_and_resume():
    text = PROV.read_text()
    assert "curl" in text and "--retry" in text, text
    assert "-C -" in text, text
    assert "CMAKE_INSTALL_PREFIX" in text, text
    assert "librelane --smoke-test" in text, text


def test_gtkwave_excluded_by_headless_rule():
    text = PROV.read_text()
    assert "GTKWave" in text, text
    assert "headless" in text.lower(), text
    assert "RocketIDE" in text, text


def _phase2_ok(tmp_path, env):
    """Wire phase-2 python stubs so a fully-stubbed tree is green."""
    pins = read_pins()
    env["PROV_PYTHON"] = str(_prov_python(tmp_path, pins))
    _pymeep_env(Path(env["TOOLS_DIR"]), pins)
    return env


def test_check_only_ok_with_matching_stubs(tmp_path):
    bindir = _bindir(tmp_path)
    bundle = _bundle(tmp_path)
    env = _phase2_ok(tmp_path, _env(tmp_path, bindir, bundle))
    tools = Path(env["TOOLS_DIR"])
    pins = read_pins()
    appdir = tools / f"librelane-{pins['LIBRELANE_PIN']}"
    appdir.mkdir(parents=True)
    app = appdir / "librelane-devshell-x86_64.AppImage"
    app.write_text("#!/bin/sh\necho stub\n", encoding="utf-8")
    app.chmod(0o755)
    (appdir / "LIBRELANE_PIN").write_text(
        pins["LIBRELANE_PIN"] + "\n", encoding="utf-8")
    (appdir / "tool_versions.txt").write_text(
        "opensta stub\n", encoding="utf-8")
    prefix = tools / "opensta-857316f"
    (prefix / "bin").mkdir(parents=True)
    _stub(prefix / "bin" / "sta", f"echo '{STA_BANNER}'")
    (prefix / "OPENSTA_PIN").write_text(
        pins["OPENSTA_PIN"] + "\n", encoding="utf-8")

    proc = run_prov(["--check-only"], env_over=env)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PROV-PHASE1: OK (4/4" in proc.stdout, proc.stdout
    assert "PROV-PHASE2: OK (11/11" in proc.stdout, proc.stdout
    assert "REMEDY" not in proc.stdout, proc.stdout


def test_check_only_finds_bundle_bin_without_dev_path(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _stub(bindir / "librelane", f"echo '{LIBRELANE_VERSION}'")
    _stub(bindir / "sta", f"echo '{STA_BANNER}'")
    _phase2_bin_stubs(bindir)
    bundle = _bundle(tmp_path, with_bins=True)
    env = _phase2_ok(tmp_path, _env(tmp_path, bindir, bundle))
    tools = Path(env["TOOLS_DIR"])
    pins = read_pins()
    appdir = tools / f"librelane-{pins['LIBRELANE_PIN']}"
    appdir.mkdir(parents=True)
    app = appdir / "librelane-devshell-x86_64.AppImage"
    app.write_text("#!/bin/sh\necho stub\n", encoding="utf-8")
    app.chmod(0o755)
    (appdir / "LIBRELANE_PIN").write_text(
        pins["LIBRELANE_PIN"] + "\n", encoding="utf-8")
    (appdir / "tool_versions.txt").write_text(
        "opensta stub\n", encoding="utf-8")
    prefix = tools / "opensta-857316f"
    (prefix / "bin").mkdir(parents=True)
    _stub(prefix / "bin" / "sta", f"echo '{STA_BANNER}'")
    (prefix / "OPENSTA_PIN").write_text(
        pins["OPENSTA_PIN"] + "\n", encoding="utf-8")

    proc = run_prov(["--check-only"], env_over=env)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PROV-PHASE1: OK (4/4" in proc.stdout, proc.stdout
    assert "PROV-PHASE2: OK (11/11" in proc.stdout, proc.stdout


def test_check_only_yosys_mismatch_fails_loud(tmp_path):
    bindir = _bindir(tmp_path, yosys="Yosys 0.69 (stale)")
    bundle = _bundle(tmp_path)

    proc = run_prov(["--check-only"],
                    env_over=_env(tmp_path, bindir, bundle))

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "PROV-PHASE1: DEGRADED" in proc.stdout, proc.stdout
    assert "yosys" in proc.stdout, proc.stdout
    assert "0.70" in proc.stdout and "0.69" in proc.stdout, \
        proc.stdout
    assert "REMEDY" in proc.stdout, proc.stdout
    assert "PROV-PHASE1: OK" not in proc.stdout, proc.stdout


def test_check_only_bundle_version_mismatch_fails_loud(tmp_path):
    bindir = _bindir(tmp_path)
    bundle = _bundle(tmp_path, version="20200101")

    proc = run_prov(["--check-only"],
                    env_over=_env(tmp_path, bindir, bundle))

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "20261025" in proc.stdout and "20200101" in proc.stdout, \
        proc.stdout
    assert "REMEDY" in proc.stdout, proc.stdout


def test_check_only_missing_tools_emit_loud_remedies(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    env = _env(tmp_path, empty, tmp_path / "no-bundle")

    proc = run_prov(["--check-only"], env_over=env)

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "PROV-PHASE1: DEGRADED" in proc.stdout, proc.stdout
    for tool in ("yosys", "sby", "librelane", "opensta"):
        assert tool in proc.stdout, (tool, proc.stdout)
    assert proc.stdout.count("REMEDY") >= 3, proc.stdout
    assert "see: https://" in proc.stdout, proc.stdout
    assert "next:" in proc.stdout, proc.stdout
    assert "PROV-PHASE1: OK" not in proc.stdout, proc.stdout


def test_check_only_writes_nothing(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    path = str(empty) + os.pathsep + str(_sysbin(tmp_path))
    env = {"PATH": path, "HOME": str(home),
           "OSS_CAD_SUITE_DIR": str(tmp_path / "no-bundle"),
           "TOOLS_DIR": str(home / "tools")}

    proc = run_prov(["--check-only"], env_over=env)

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert not (home / "tools").exists(), "check-only must not write"


def test_install_offline_degrades_never_fake_green(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    env = _env(tmp_path, empty, tmp_path / "no-bundle")
    env["PROV_OFFLINE"] = "1"

    proc = run_prov(["--install"], env_over=env, timeout=120)

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "PROV-PHASE1: DEGRADED" in proc.stdout, proc.stdout
    assert "offline" in proc.stdout.lower(), proc.stdout
    assert "PROV-PHASE1: OK" not in proc.stdout, proc.stdout
    assert "4/4" not in proc.stdout, proc.stdout
    tools = Path(env["TOOLS_DIR"])
    assert not tools.exists() or not any(tools.iterdir()), \
        "offline install must not fake provisioned bits"


def test_install_detects_unreachable_network(tmp_path):
    # Hermetic air-gap: a failing curl stub forces the preflight
    # down the offline path on every host (no live probing — the
    # sandbox proxy answers some hosts and 502s others, so a live
    # probe would be flaky here).
    fakedir = tmp_path / "fakebin"
    fakedir.mkdir()
    _stub(fakedir / "curl", "echo 'stub curl: offline' >&2\nexit 6")
    empty = tmp_path / "empty"
    empty.mkdir()
    env = _env(tmp_path, empty, tmp_path / "no-bundle")
    env["PATH"] = (str(fakedir) + os.pathsep + env["PATH"])

    start = time.monotonic()
    proc = run_prov(["--install"], env_over=env, timeout=120)
    elapsed = time.monotonic() - start

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "offline" in proc.stdout.lower(), proc.stdout
    assert "PROV-PHASE1: DEGRADED" in proc.stdout, proc.stdout
    assert "PROV-PHASE1: OK" not in proc.stdout, proc.stdout
    assert elapsed < 100, f"air-gap path took {elapsed:.0f}s"


def test_install_ok_when_all_asserted(tmp_path):
    bindir = _bindir(tmp_path)
    bundle = _bundle(tmp_path)
    env = _phase2_ok(tmp_path, _env(tmp_path, bindir, bundle))
    tools = Path(env["TOOLS_DIR"])
    pins = read_pins()
    appdir = tools / f"librelane-{pins['LIBRELANE_PIN']}"
    appdir.mkdir(parents=True)
    app = appdir / "librelane-devshell-x86_64.AppImage"
    app.write_text("#!/bin/sh\necho stub\n", encoding="utf-8")
    app.chmod(0o755)
    (appdir / "LIBRELANE_PIN").write_text(
        pins["LIBRELANE_PIN"] + "\n", encoding="utf-8")
    (appdir / "tool_versions.txt").write_text(
        "opensta stub\n", encoding="utf-8")
    prefix = tools / "opensta-857316f"
    (prefix / "bin").mkdir(parents=True)
    _stub(prefix / "bin" / "sta", f"echo '{STA_BANNER}'")
    (prefix / "OPENSTA_PIN").write_text(
        pins["OPENSTA_PIN"] + "\n", encoding="utf-8")

    proc = run_prov(["--install"], env_over=env, timeout=120)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PROV-PHASE1: OK (4/4" in proc.stdout, proc.stdout
    assert "PROV-PHASE2: OK (11/11" in proc.stdout, proc.stdout


def test_live_check_only_reports_a_verdict():
    proc = run_prov(["--check-only"], timeout=120)

    assert proc.returncode in (0, 1), proc.stdout + proc.stderr
    assert "PROV-PHASE1:" in proc.stdout, proc.stdout
    assert "PROV-PHASE2:" in proc.stdout, proc.stdout
    if proc.returncode == 0:
        assert "(4/4" in proc.stdout, proc.stdout
        assert "(11/11" in proc.stdout, proc.stdout
    else:
        assert "DEGRADED" in proc.stdout, proc.stdout
        assert "REMEDY" in proc.stdout, proc.stdout


def test_report_names_pins():
    report = ROOT / "docs" / "work" / "PROV" / "report.md"
    assert report.is_file(), "docs/work/PROV/report.md missing"
    text = report.read_text()
    for token in ("20261025", "3.0.17", "857316f",
                  "wiring.patch", "Integrator"):
        assert token in text, token


def test_provisioner_reports_phase2_verdict_and_palace():
    text = PROV.read_text()
    for token in ("PROV-PHASE2:", "palace UNSOURCED",
                  "UNSOURCED", "ambient-recorded", "install_magic",
                  "install_ngspice", "install_xyce", "install_cace",
                  "install_pymeep", "install_openems", "install_devsim",
                  "install_klayout", "install_xschem", "install_netgen",
                  "install_elmer"):
        assert token in text, token


def test_provisioner_cites_phase2_sources():
    text = PROV.read_text()
    for url in (
        "github.com/RTimothyEdwards/magic",
        "github.com/RTimothyEdwards/netgen",
        "github.com/StefanSchippers/xschem",
        "klayout.de",
        "ngspice.sourceforge.io",
        "xyce.sandia.gov",
        "github.com/efabless/cace",
        "meep.readthedocs.io",
        "openEMS.de",
        "pypi.org/project/devsim",
        "csc.fi/web/elmer",
    ):
        assert url in text, url
    docs = (ROOT / "docs" / "provision-sources.md").read_text()
    for url in (
        "opencircuitdesign.com/magic",
        "klayout",
        "ngspice",
        "xyce",
        "cace",
        "pymeep",
        "openems",
        "devsim",
        "elmer",
        "palace",
    ):
        assert url in docs.lower(), url


def test_wiring_patch_applies_or_is_integrated():
    patch = ROOT / "docs" / "work" / "PROV" / "wiring.patch"
    assert patch.is_file(), "docs/work/PROV/wiring.patch missing"
    hooked = "provision_toolchain.sh" in (
        ROOT / "scripts" / "install.sh").read_text()
    catalogued = "provision_toolchain.sh" in (
        ROOT / "src" / "interfaces" / "setup_catalogue.yaml"
    ).read_text()
    if hooked and catalogued:
        return  # Integrator already applied the patch.
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "apply", "--check",
         str(patch.relative_to(ROOT))],
        capture_output=True, text=True, timeout=60, cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr


def _write_env_file(tools, entries):
    env_file = tools / "prov-phase1.env"
    env_file.write_text(
        "# test fixture\n" + "".join(
            f'{key}="{value}"\n' for key, value in entries),
        encoding="utf-8")
    return env_file


def test_print_path_emits_idempotent_block(tmp_path):
    tools = tmp_path / "tools"
    oss_bin = tools / "oss-cad-suite" / "bin"
    magic_bin = tools / "magic-707d67e" / "bin"
    pymeep_bin = tools / "miniforge3" / "envs" / "pymeep" / "bin"
    for bindir in (oss_bin, magic_bin, pymeep_bin):
        bindir.mkdir(parents=True)
    _write_env_file(tools, [
        ("OSS_CAD_SUITE_DIR", str(tools / "oss-cad-suite")),
        ("MAGIC_PREFIX", str(tools / "magic-707d67e")),
        ("PYMEEP_PY", str(pymeep_bin / "python")),
        ("LIBRELANE_APPIMAGE",
         str(tools / "librelane-3.0.17"
             / "librelane-devshell-x86_64.AppImage")),
    ])
    env = {"PATH": os.environ["PATH"],
           "HOME": str(tmp_path / "home"),
           "TOOLS_DIR": str(tools),
           "OSS_CAD_SUITE_DIR": str(tools / "oss-cad-suite")}

    proc = run_prov(["--print-path"], env_over=env)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "# >>> rocketeda toolchain >>>" in proc.stdout
    assert "# <<< rocketeda toolchain <<<" in proc.stdout
    for bindir in (oss_bin, magic_bin, pymeep_bin):
        assert str(bindir) in proc.stdout, bindir
    # The AppImage dir holds no binaries: never on PATH.
    assert "librelane-3.0.17" not in proc.stdout, proc.stdout


def test_print_path_skips_absent_dirs(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    oss_bin = tools / "oss-cad-suite" / "bin"
    oss_bin.mkdir(parents=True)
    _write_env_file(tools, [
        ("OSS_CAD_SUITE_DIR", str(tools / "oss-cad-suite")),
        ("MAGIC_PREFIX", str(tools / "magic-missing")),
    ])
    env = {"PATH": os.environ["PATH"],
           "HOME": str(tmp_path / "home"),
           "TOOLS_DIR": str(tools),
           "OSS_CAD_SUITE_DIR": str(tools / "oss-cad-suite")}

    proc = run_prov(["--print-path"], env_over=env)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert str(oss_bin) in proc.stdout, proc.stdout
    assert "magic-missing" not in proc.stdout, proc.stdout


def test_print_path_without_env_file_fails_loud(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    env = {"PATH": os.environ["PATH"],
           "HOME": str(tmp_path / "home"),
           "TOOLS_DIR": str(tools),
           "OSS_CAD_SUITE_DIR": str(tools / "oss-cad-suite")}

    proc = run_prov(["--print-path"], env_over=env)

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "--install" in proc.stdout, proc.stdout
