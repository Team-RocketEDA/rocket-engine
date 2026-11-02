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
                 "YOSYS_EXPECT", "SBY_EXPECT", "CUDD_PIN",
                 "XYCE_REF", "TRILINOS_REF",
                 "OPENEMS_REF", "CSXCAD_REF"):
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


MVP_PHASE2_IDS = ("magic", "netgen", "klayout", "ngspice",
                  "xschem", "xyce", "cace")
DEFERRED_IDS = ("pymeep", "openems", "elmer", "devsim")


def test_mvp_deferred_verdict_split():
    """PROV-PHASE2 verdict covers the MVP subset only.

    Deferred packs (pymeep, openEMS, elmer, devsim) report on
    their own PROV-DEFERRED line and never gate the MVP claim
    (PROV-DEFERRED owns their line; palace stays unsourced).
    """
    proc = subprocess.run(
        ["bash", str(PROV), "--check-only"],
        capture_output=True, text=True, timeout=120, cwd=ROOT,
    )
    assert proc.returncode in (0, 1), proc.stdout + proc.stderr
    assert "PROV-PHASE2:" in proc.stdout, proc.stdout
    assert "PROV-DEFERRED:" in proc.stdout, proc.stdout
    phase2_line = next(
        line for line in proc.stdout.splitlines()
        if "PROV-PHASE2:" in line
    )
    deferred_line = next(
        line for line in proc.stdout.splitlines()
        if "PROV-DEFERRED:" in line
    )
    for deferred in DEFERRED_IDS:
        assert deferred not in phase2_line, (deferred, phase2_line)
    if proc.returncode == 0:
        assert "(7/7" in phase2_line, phase2_line
        assert "(4/4" in deferred_line, deferred_line
    else:
        assert "DEGRADED" in proc.stdout, proc.stdout
    assert "palace UNSOURCED" in proc.stdout, proc.stdout


def test_provision_sources_records_trio_pins():
    """provision-sources.md records the trio revision pins.

    UPSTREAM-RECIPE: install_opensta/install_xyce/install_openems
    copy the upstream README recipes verbatim; this doc records
    the doc URLs + pinned revisions the script encodes.
    """
    text = (ROOT / "docs" / "provision-sources.md").read_text()
    pins = read_pins()
    for name in ("OPENSTA_PIN", "CUDD_PIN", "XYCE_REF",
                 "TRILINOS_REF", "OPENEMS_REF", "CSXCAD_REF"):
        assert pins[name] in text, name


def test_gitignore_repo_local():
    """BUILD-LOCAL stage 1: repo-local dirs stay untracked."""
    text = (ROOT / ".gitignore").read_text()
    assert ".tools/" in text, "repo-local tools dir not ignored"
    assert ".stores/" in text, "repo-local engine store not ignored"


def test_repo_local_defaults():
    """BUILD-LOCAL stages 1-2: repo-local roots, explicit env wins.

    The provisioner defaults TOOLS_DIR into the repo
    ($ROOT/.tools); install.sh defaults ROCKETEDA_HOME into the
    repo ($ROOT/.stores/rocketeda). Explicit env still wins.
    """
    prov = PROV.read_text()
    assert "TOOLS_DIR:-$ROOT_DIR/.tools" in prov, \
        "provisioner TOOLS_DIR default is not repo-local"
    install = (ROOT / "scripts" / "install.sh").read_text()
    assert "ROCKETEDA_HOME:-$ROOT/.stores/rocketeda" in install, \
        "install.sh ROCKETEDA_HOME default is not repo-local"


def test_list_tools():
    """BUILD-LOCAL stage 3: --list-tools enumerates the matrix."""
    proc = subprocess.run(
        ["bash", str(PROV), "--list-tools"],
        capture_output=True, text=True, timeout=60, cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for tool_id in ("oss-cad-suite", "librelane", "opensta",
                    "magic", "netgen", "klayout", "ngspice",
                    "xyce", "xschem", "cace",
                    "pymeep", "openems", "elmer", "devsim"):
        assert tool_id in proc.stdout, tool_id


def test_only_scopes_to_one_tool(tmp_path):
    """BUILD-LOCAL stage 3: --only provisions exactly one tool."""
    tools = tmp_path / "tools"
    prefix = tools / "klayout-0.30.12"
    (prefix / "bin").mkdir(parents=True)
    stub = prefix / "bin" / "klayout"
    stub.write_text("#!/bin/sh\necho 'KLayout 0.30.12'\n",
                    encoding="utf-8")
    stub.chmod(0o755)
    (prefix / "KLAYOUT_PIN").write_text("0.30.12\n", encoding="utf-8")
    env = dict(os.environ, TOOLS_DIR=str(tools))
    proc = subprocess.run(
        ["bash", str(PROV), "--only", "klayout", "--check-only"],
        capture_output=True, text=True, timeout=120, cwd=ROOT, env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PROV-ONLY klayout: OK" in proc.stdout, proc.stdout
    assert "PROV-PHASE1:" not in proc.stdout, proc.stdout
    assert "PROV-PHASE2:" not in proc.stdout, proc.stdout
    rows = [line for line in proc.stdout.splitlines()
            if line.startswith("PROV-ROW\t")]
    assert {line.split("\t")[1] for line in rows} == {"klayout"}, rows


def test_machine_readable_verdict_rows():
    """BUILD-LOCAL stage 3: one TSV row per tool.

    Columns: id, state, version, path, remedy.
    """
    proc = subprocess.run(
        ["bash", str(PROV), "--check-only"],
        capture_output=True, text=True, timeout=120, cwd=ROOT,
    )
    assert proc.returncode in (0, 1), proc.stdout + proc.stderr
    rows = [
        line.split("\t")
        for line in proc.stdout.splitlines()
        if line.startswith("PROV-ROW\t")
    ]
    assert rows, "no PROV-ROW lines emitted"
    for fields in rows:
        assert len(fields) == 6, fields
        assert fields[1].strip(), fields
    ids = {fields[1] for fields in rows}
    for tool_id in MVP_PHASE2_IDS + DEFERRED_IDS:
        assert tool_id in ids, (tool_id, sorted(ids))


def test_collect_and_layout_doc(tmp_path):
    """BUILD-LOCAL stage 4: layout doc + collect.sh stage the bundle."""
    doc = ROOT / "docs" / "build-local.md"
    assert doc.is_file(), "docs/build-local.md missing"
    text = doc.read_text()
    for token in ("engine/", "fuel/", "ui/dist/", "tools/", "stores/"):
        assert token in text, token
    collect = ROOT / "scripts" / "collect.sh"
    assert collect.is_file(), "scripts/collect.sh missing"
    tools = tmp_path / "tools"
    (tools / "bin").mkdir(parents=True)
    (tools / "bin" / "stub").write_text("stub", encoding="utf-8")
    stores = tmp_path / "stores"
    stores.mkdir()
    env = dict(os.environ, TOOLS_DIR=str(tools),
               ROCKETEDA_HOME=str(stores))
    proc = subprocess.run(
        ["bash", str(collect), "--check"],
        capture_output=True, text=True, timeout=60, cwd=ROOT, env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    dest = tmp_path / "bundle"
    proc = subprocess.run(
        ["bash", str(collect), "--dest", str(dest)],
        capture_output=True, text=True, timeout=60, cwd=ROOT, env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (dest / "tools" / "bin" / "stub").is_file()
    assert (dest / "stores").is_dir()
    manifest = (dest / "manifest.txt").read_text()
    assert "layout_version=1" in manifest, manifest
    assert "oss_cad_suite_pin=" in manifest, manifest


def test_catalogue_mvp_entries_have_recipes():
    """cvc/openroad catalogue entries carry real recipes.

    `provisionable: false` with "no recipe yet" is not an
    accepted state for MVP-subset tooling: cvc resolves via
    the pinned oss-cad-suite bundle (ships cvc4/cvc5),
    openroad via the LibreLane supported distribution.
    """
    from ruamel.yaml import YAML
    catalogue = YAML(typ="safe").load(
        (ROOT / "src" / "interfaces" / "setup_catalogue.yaml"
         ).read_text()
    )
    entries = {entry["id"]: entry for entry in catalogue["entries"]}
    for tool_id in ("cvc", "openroad"):
        entry = entries[tool_id]
        assert entry.get("provisionable", True) is not False, tool_id
        assert "no recipe yet" not in entry["recipe"], tool_id
