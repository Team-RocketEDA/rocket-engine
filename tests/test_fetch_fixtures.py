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


# --- FETCH-HARDEN slice 1: pin re-verification (RED) ---

def _make_remote_with_history(tmp_path):
    """Local 'upstream' with two commits serving reachable SHAs (like GitHub)."""
    src = tmp_path / "upstream"
    sha1 = make_git_repo(src, {"LICENSE": MIT, "top.v": "v1\n"})
    (src / "top.v").write_text("v2\n")
    subprocess.run(["git", "add", "."], cwd=src, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-qm", "two"], cwd=src, check=True,
    )
    sha2 = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=src, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "config", "uploadpack.allowReachableSHA1InWant", "true"],
        cwd=src, check=True,
    )
    return src, sha1, sha2


def test_verify_pins_current_pin(tmp_path):
    mod = load_fetch()
    src, _, head = _make_remote_with_history(tmp_path)
    report = mod.verify_pins({"demo": {"url": str(src), "rev": head}})
    assert report["demo"]["status"] == "current"
    assert report["demo"]["head"] == head


def test_verify_pins_drifted_pin(tmp_path):
    mod = load_fetch()
    src, old, head = _make_remote_with_history(tmp_path)
    report = mod.verify_pins({"demo": {"url": str(src), "rev": old}})
    assert report["demo"]["status"] == "drifted"
    assert report["demo"]["head"] == head
    assert report["demo"]["pin"] == old


def test_verify_pins_orphaned_pin(tmp_path):
    mod = load_fetch()
    src, _, head = _make_remote_with_history(tmp_path)
    dead = "d" * 40
    report = mod.verify_pins({"demo": {"url": str(src), "rev": dead}})
    assert report["demo"]["status"] == "orphaned"
    assert report["demo"]["pin"] == dead
    assert report["demo"]["head"] == head


def test_verify_pins_unreachable_url(tmp_path):
    mod = load_fetch()
    report = mod.verify_pins(
        {"demo": {"url": str(tmp_path / "nope"), "rev": "a" * 40}}
    )
    assert report["demo"]["status"] == "unreachable"


def test_verify_pins_cli_exit_codes(tmp_path, monkeypatch, capsys):
    mod = load_fetch()
    src, _, head = _make_remote_with_history(tmp_path)
    monkeypatch.setattr(
        mod, "FIXTURES",
        {"demo": {"url": str(src), "rev": head, "license": "MIT",
                 "results": "tb"}},
    )
    assert mod.main(["--verify-pins"]) == 0
    monkeypatch.setattr(
        mod, "FIXTURES",
        {"demo": {"url": str(src), "rev": "d" * 40, "license": "MIT",
                 "results": "tb"}},
    )
    assert mod.main(["--verify-pins"]) == 1
    out = capsys.readouterr().out
    assert "d" * 40 in out
    assert "orphan" in out.lower()


def test_vendor_readme_notes_documented_results(tmp_path):
    mod = load_fetch()
    spec = {"url": "https://github.com/example/x", "rev": "a" * 40,
            "license": "ISC", "results": "testbench X passes, see tb/README"}
    note = mod.write_vendor_readme("xcore", spec, tmp_path)
    text = note.read_text()
    assert "a" * 40 in text
    assert "testbench X passes" in text
    assert "ISC" in text
