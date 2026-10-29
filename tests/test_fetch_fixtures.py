"""fetch_fixtures.py: pinned vendor fetches + license gate (FIXTURE-FETCH).

Vendor trees live in fixtures/upstream/<name>/ (NOT the micro-fixtures
under tests/adapters/fixtures). Fetches are pinned to full commit SHAs,
idempotent on re-run (HEAD hash check), and gated to permissive
licenses only (Apache/MIT/BSD/ISC) — the two unlicensed analog repos
from the candidates report must never vendor.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

EXPECTED = {"serv", "picorv32", "sky130-bandgap", "ttsky-sigma-delta", "cspdk"}


def load_fetch():
    spec = importlib.util.spec_from_file_location(
        "fetch_fixtures_under_test", ROOT / "scripts" / "fetch_fixtures.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_git_repo(path, files):
    path.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (path / name).write_text(text)
    run = lambda *a: subprocess.run(
        ["git", *a], cwd=path, check=True, capture_output=True, text=True
    )
    run("init", "-q")
    run("add", ".")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "one")
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, check=True,
        capture_output=True, text=True,
    )
    return out.stdout.strip()


def test_catalog_pins_five_accepted_designs():
    mod = load_fetch()
    assert set(mod.FIXTURES) == EXPECTED
    for name, spec in mod.FIXTURES.items():
        rev = spec["rev"]
        assert len(rev) == 40 and all(c in "0123456789abcdef" for c in rev), name
        assert spec["url"].startswith("https://github.com/"), name
        assert spec["license"] in ("Apache-2.0", "MIT", "BSD", "ISC"), name
        assert spec["results"].strip(), name  # documented "correct" exists


def test_fetch_is_idempotent_on_rerun(tmp_path):
    mod = load_fetch()
    src = tmp_path / "src"
    sha = make_git_repo(src, {"LICENSE": "MIT marker: see below\n",
                              "top.v": "// rtl\n"})
    spec = {"url": str(src), "rev": sha, "license": "MIT",
            "results": "testbench passes"}
    vendor = tmp_path / "vendor"
    assert mod.fetch_one("demo", spec, vendor) == "fetched"
    dest = vendor / "demo"
    assert (dest / "top.v").read_text() == "// rtl\n"
    head = subprocess.run(
        ["git", "-C", str(dest), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert head == sha
    assert mod.fetch_one("demo", spec, vendor) == "up-to-date"


def test_fetch_updates_tree_when_pin_moves(tmp_path):
    mod = load_fetch()
    src = tmp_path / "src"
    sha1 = make_git_repo(src, {"LICENSE": "x\n", "top.v": "v1\n"})
    spec = {"url": str(src), "rev": sha1, "license": "MIT", "results": "tb"}
    vendor = tmp_path / "vendor"
    assert mod.fetch_one("demo", spec, vendor) == "fetched"
    (src / "top.v").write_text("v2\n")
    subprocess.run(["git", "add", ".", ], cwd=src, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-qm", "two"], cwd=src, check=True,
    )
    sha2 = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=src, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    spec = dict(spec, rev=sha2)
    assert mod.fetch_one("demo", spec, vendor) == "updated"
    assert (vendor / "demo" / "top.v").read_text() == "v2\n"


def test_fetch_failure_reports_after_retries(tmp_path):
    mod = load_fetch()
    spec = {"url": str(tmp_path / "nope"), "rev": "0" * 40,
            "license": "MIT", "results": "tb"}
    with pytest.raises(mod.FetchError):
        mod.fetch_one("demo", spec, tmp_path / "vendor", retries=2)


APACHE = "Apache License\nVersion 2.0, January 2004\nhttp://www.apache.org/licenses/\n"
MIT = "MIT License\nPermission is hereby granted, free of charge, to any person\n"
BSD = "BSD 3-Clause License\nRedistribution and use in source and binary forms\n"
ISC = ("ISC License\nPermission to use, copy, modify, and/or distribute "
       "this software for any purpose\n")


@pytest.mark.parametrize("text,want", [
    (APACHE, "Apache-2.0"), (MIT, "MIT"), (BSD, "BSD"), (ISC, "ISC"),
])
def test_license_gate_accepts_permissive_licenses(tmp_path, text, want):
    mod = load_fetch()
    tree = tmp_path / "serv"
    tree.mkdir()
    (tree / "LICENSE").write_text(text)
    assert mod.check_license(tree) == want
    assert mod.license_gate(tmp_path, ["serv"]) == []


def test_license_gate_rejects_unlicensed_tree(tmp_path):
    mod = load_fetch()
    tree = tmp_path / "sar-adc"
    tree.mkdir()
    (tree / "top.sch").write_text("unlicensed analog\n")
    assert mod.check_license(tree) is None
    violations = mod.license_gate(tmp_path, ["sar-adc"])
    assert len(violations) == 1 and "sar-adc" in violations[0]


def test_license_gate_rejects_copyleft_tree(tmp_path):
    mod = load_fetch()
    tree = tmp_path / "gplcore"
    tree.mkdir()
    (tree / "COPYING").write_text(
        "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n")
    assert mod.check_license(tree) is None
    assert mod.license_gate(tmp_path, ["gplcore"]) != []


def test_vendor_readme_notes_documented_results(tmp_path):
    mod = load_fetch()
    spec = {"url": "https://github.com/example/x", "rev": "a" * 40,
            "license": "ISC", "results": "testbench X passes, see tb/README"}
    note = mod.write_vendor_readme("xcore", spec, tmp_path)
    text = note.read_text()
    assert "a" * 40 in text
    assert "testbench X passes" in text
    assert "ISC" in text
