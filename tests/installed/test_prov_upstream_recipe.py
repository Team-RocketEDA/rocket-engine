"""PROV-UPSTREAM-RECIPE trio regression tests (Step 18).

Locks the upstream-README verbatim properties of
install_opensta/install_xyce/install_openems in
scripts/provision_toolchain.sh: nonlinear dep-first ordering
(CUDD-then-OpenSTA, Trilinos-then-Xyce, CSXCAD-then-openEMS),
README build tokens (autoreconf, bootstrap, serial-Trilinos
flags, CSXCAD_ROOT_DIR), repo-local installs only (never
shared prefixes, no sudo), pinfile-gated checks, and doc
URL records in docs/provision-sources.md (read-only here:
docs edits belong to the dump-13 track).
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PROV = ROOT / "scripts" / "provision_toolchain.sh"
SOURCES = ROOT / "docs" / "provision-sources.md"


def prov_text():
    """Provisioner script text.

    Returns:
        Full text of scripts/provision_toolchain.sh.
    """
    return PROV.read_text()


def func_body(text, name):
    """Slice one bash function body out of the script text.

    Args:
        text: Full script text.
        name: Bash function name (e.g. install_opensta).

    Returns:
        Body text between the def line and the next def line.
    """
    start = text.index("\n%s() {" % name)
    rest = text[start:]
    nxt = re.search(r"\n[a-zA-Z_][a-zA-Z0-9_]*\(\) \{", rest[1:])
    assert nxt, "no function follows %s" % name
    return rest[:nxt.start() + 1]


def test_opensta_builds_cudd_before_cmake():
    """CUDD dep builds before the OpenSTA cmake (nonlinear order)."""
    body = func_body(prov_text(), "install_opensta")
    assert "cuddorg/cudd" in body
    assert "autoreconf -fi" in body
    assert "cmake -DCUDD_DIR=" in body
    order = ["install opensta: building CUDD",
             "install opensta: cmake build"]
    idx = [body.index(token) for token in order]
    assert idx == sorted(idx), order


def test_opensta_gates_readme_build_deps():
    """install_opensta fail-fasts on every README build dep binary."""
    body = func_body(prov_text(), "install_opensta")
    loop = body[:body.index("missing_prereq=\"$missing_prereq")]
    for dep in ("git", "cmake", "make", "g++", "swig", "bison",
                "flex", "tclsh", "autoconf", "automake", "libtool"):
        assert dep in loop, dep
    assert "libtool libtool-bin" in body
    assert "s/\\btclsh\\b/tcl/" in body, \
        "apt remedy must map the tclsh binary to the tcl package"


def test_opensta_installs_repo_local_only():
    """OpenSTA lands under the repo-local prefix, never shared paths."""
    body = func_body(prov_text(), "install_opensta")
    assert "CMAKE_INSTALL_PREFIX=" in body
    assert "OPENSTA_PREFIX" in body
    assert not re.search(r"(?m)^\s*sudo\s", body), \
        "trio installer must never execute sudo (remedy strings excepted)"
    assert "/usr/local" not in body


def test_xyce_builds_trilinos_first_serial():
    """Trilinos builds first (serial), then Xyce via bootstrap+autotools."""
    body = func_body(prov_text(), "install_xyce")
    assert "TRILINOS_REPO" in body
    assert "XYCE_REPO" in body
    assert body.index("install xyce: building Trilinos") \
        < body.index("install xyce: cloning Xyce")
    assert "-DTPL_ENABLE_MPI=OFF" in body
    assert "-DTPL_ENABLE_gtest=OFF" in body
    assert "-DShyLU" not in body
    assert "./bootstrap" in body
    assert "--with-trilinosdir=" in body
    assert "XYCE_REF" in body
    assert not re.search(r"(?m)^\s*sudo\s", body), \
        "trio installer must never execute sudo (remedy strings excepted)"
    assert "/usr/local" not in body


def test_openems_builds_csxcad_first():
    """CSXCAD builds first, then openEMS against the CSXCAD prefix."""
    body = func_body(prov_text(), "install_openems")
    assert "CSXCAD_REPO" in body
    assert "OPENEMS_REPO" in body
    assert body.index("install openems: building CSXCAD") \
        < body.index("install openems: cloning openEMS")
    assert "-DCSXCAD_ROOT_DIR=" in body
    assert "OPENEMS_REF" in body
    assert not re.search(r"(?m)^\s*sudo\s", body), \
        "trio installer must never execute sudo (remedy strings excepted)"
    assert "/usr/local" not in body


def test_trio_checks_require_pinfiles():
    """Trio checks gate on pinfiles, never on ambient binaries alone."""
    text = prov_text()
    assert "OPENSTA_PIN" in func_body(text, "check_opensta")
    assert "XYCE_REF" in func_body(text, "check_xyce")
    assert "OPENEMS_REF" in func_body(text, "check_openems")


def test_provision_sources_records_trio_doc_urls():
    """provision-sources.md records the trio doc URLs (read-only check)."""
    text = SOURCES.read_text()
    assert "opensta.readthedocs.io" in text.lower() \
        or "OpenSTA" in text
    assert "xyce.sandia.gov" in text
    assert "docs.openEMS.de" in text
