#!/usr/bin/env python3
"""Vendor accepted D/A/M fixtures at pinned commits (FIXTURE-FETCH).

Accepted set (locked): SERV + picorv32 (digital), 2amlogic
sky130-bandgap (analog), pthomas ttsky-sigma-delta (mixed-signal).
Each ships prior verification (testbenches / spec + sims / measured
numbers) — see docs/asic-fixture-candidates.md.

Layout: shallow clones at pinned SHAs under fixtures/upstream/<name>/
(NOT tests/adapters/fixtures, which holds hand-made micro-fixtures).
Per-design notes (url, pin, license, what "correct" means) land next
to the trees as fixtures/upstream/<name>.md so they commit while the
fetched trees stay git-ignored.

License gate: Apache-2.0 / MIT / BSD / ISC only. Anything else —
including unlicensed trees like the two excluded analog repos — fails
the gate and must never vendor.

Usage:
    python scripts/fetch_fixtures.py [--only NAME] [--retries N]
    python scripts/fetch_fixtures.py --check [--vendor-dir DIR]
"""

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = ROOT / "fixtures" / "upstream"

# Pins resolved 2026-10-29 via `git ls-remote <url> HEAD`.
FIXTURES = {
    "serv": {
        "url": "https://github.com/olofk/serv",
        "rev": "f200eb2ed7b69ac1c6b8eddd47654522aeee5ce8",
        "license": "ISC",
        "kind": "D",
        "results": (
            "Bit-serial RISC-V core; ships Verilog + testbenches. "
            "Correct = its testbenches/regression pass under "
            "Icarus/Verilator (see test/ in the vendored tree)."
        ),
    },
    "picorv32": {
        "url": "https://github.com/YosysHQ/picorv32",
        "rev": "ef203c2b0a3fb793280f5114941416c425c5b461",
        "license": "ISC",
        "kind": "D",
        "results": (
            "Canonical small RISC-V core; ships Verilog + testbenches. "
            "Correct = its testbenches pass under Icarus/Verilator "
            "(see the vendored tree's testbench + firmware tests)."
        ),
    },
    "sky130-bandgap": {
        "url": "https://github.com/2amlogic/sky130-bandgap",
        "rev": "1f470499ca83acd8d2a6a133e5a7f0878f158666",
        "license": "Apache-2.0",
        "kind": "A",
        "results": (
            "sky130 bandgap reference; claims spec + xschem + ngspice "
            "+ GDS + DRC/LVS reports. Correct = ngspice sims reproduce "
            "the spec'd reference voltage across corners; verify the "
            "claimed artifacts exist on fetch (efabless RDAC is the "
            "fallback if this canary is immature)."
        ),
    },
    "ttsky-sigma-delta": {
        "url": "https://github.com/pthomas/ttsky-sigma-delta",
        "rev": "f868b8118b9f9645cd817684a62f0fb488c20040",
        "license": "Apache-2.0",
        "kind": "M",
        "results": (
            "Continuous-time sigma-delta ADC (TinyTapeout sky130); "
            "ships design doc + measured results. Correct = sims match "
            "the documented/measured numbers in the vendored tree."
        ),
    },
}

ACCEPTED = ("Apache-2.0", "MIT", "BSD", "ISC")

LICENSE_FILES = (
    "LICENSE", "LICENSE.txt", "LICENSE.md", "LICENCE", "LICENCE.txt",
    "LICENCE.md", "COPYING", "COPYING.md", "COPYING.txt", "COPYRIGHT",
)
README_FALLBACKS = ("README", "README.md", "README.rst", "README.txt")

MARKERS = (
    # (license id, required lowercase substrings)
    ("Apache-2.0", ("apache license", "version 2.0")),
    ("MIT", ("permission is hereby granted, free of charge",)),
    ("BSD", ("redistribution and use in source and binary forms",)),
    ("ISC", ("permission to use, copy, modify, and/or distribute this software",)),
)


class FetchError(Exception):
    """A fixture fetch failed (network, missing rev, or gate violation)."""


def _git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=str(cwd), check=True,
        capture_output=True, text=True,
    )


def _head(dest):
    if not (dest / ".git").exists():
        return None
    try:
        out = _git("rev-parse", "HEAD", cwd=dest)
    except subprocess.CalledProcessError:
        return None
    return out.stdout.strip()


def _fetch_rev_at(dest, url, rev):
    dest.mkdir(parents=True, exist_ok=True)
    if not (dest / ".git").exists():
        _git("init", "-q", cwd=dest)
        _git("remote", "add", "origin", url, cwd=dest)
    else:
        _git("remote", "set-url", "origin", url, cwd=dest)
    _git("fetch", "-q", "--depth", "1", "origin", rev, cwd=dest)
    _git("checkout", "-q", "--detach", rev, cwd=dest)


def fetch_one(name, spec, vendor_dir=VENDOR_DIR, retries=3):
    """Fetch one fixture at its pinned rev. Idempotent on re-run.

    Returns "fetched", "updated", or "up-to-date" (HEAD already equals
    the pin — reruns are a hash-check no-op). Raises FetchError after
    ``retries`` failed attempts (network flakes).
    """
    dest = Path(vendor_dir) / name
    if _head(dest) == spec["rev"]:
        return "up-to-date"
    updating = (dest / ".git").exists()
    last = None
    for attempt in range(max(1, retries)):
        try:
            if not updating:
                shutil.rmtree(dest, ignore_errors=True)
            _fetch_rev_at(dest, spec["url"], spec["rev"])
            return "updated" if updating else "fetched"
        except subprocess.CalledProcessError as exc:
            last = exc
            if not updating:
                shutil.rmtree(dest, ignore_errors=True)
            time.sleep(2 ** attempt)
    raise FetchError(f"{name}: fetch failed after {retries} attempts: {last}")


def check_license(tree):
    """Identify a vendored tree's license; None if not accepted/found."""
    tree = Path(tree)
    candidates = [tree / f for f in LICENSE_FILES]
    candidates += [tree / f for f in README_FALLBACKS]
    texts = []
    for path in candidates:
        if path.is_file():
            try:
                texts.append(path.read_text(errors="replace").lower())
            except OSError:
                continue
    for lic, markers in MARKERS:
        if any(all(m in text for m in markers) for text in texts):
            return lic
    return None


def license_gate(vendor_dir=VENDOR_DIR, names=None):
    """Return a violation message per fixture lacking an accepted license."""
    vendor_dir = Path(vendor_dir)
    violations = []
    for name in names if names is not None else sorted(FIXTURES):
        tree = vendor_dir / name
        if not tree.is_dir():
            violations.append(f"{name}: not vendored under {vendor_dir}")
            continue
        found = check_license(tree)
        if found not in ACCEPTED:
            violations.append(
                f"{name}: no accepted license found "
                f"(want one of: {', '.join(ACCEPTED)})"
            )
    return violations


def write_vendor_readme(name, spec, vendor_dir=VENDOR_DIR):
    """Write the per-design note: pin, license, what 'correct' means."""
    vendor_dir = Path(vendor_dir)
    vendor_dir.mkdir(parents=True, exist_ok=True)
    note = vendor_dir / f"{name}.md"
    note.write_text(
        f"# Vendored fixture: {name}\n\n"
        f"- upstream: {spec['url']}\n"
        f"- pinned rev: `{spec['rev']}`\n"
        f"- license: {spec['license']}\n"
        f"- domain: {spec.get('kind', '?')}\n\n"
        f"## Documented results (what 'correct' means)\n\n"
        f"{spec['results'].strip()}\n\n"
        f"Fetched by `scripts/fetch_fixtures.py` (FIXTURE-FETCH). "
        f"Do not hand-edit the tree under `{name}/`; re-pin by updating "
        f"`FIXTURES` and re-running the fetch.\n"
    )
    return note


def fetch_all(vendor_dir=VENDOR_DIR, only=None, retries=3):
    """Fetch each fixture (or a subset) and write its note."""
    status = {}
    want = [n for n in FIXTURES if only is None or n in only]
    for name in want:
        status[name] = fetch_one(name, FIXTURES[name], vendor_dir, retries)
        write_vendor_readme(name, FIXTURES[name], vendor_dir)
    return status


def main(argv=None):
    parser = argparse.ArgumentParser(description="Vendor pinned fixtures.")
    parser.add_argument("--vendor-dir", default=str(VENDOR_DIR))
    parser.add_argument("--only", action="append", default=None,
                        help="fetch only this fixture (repeatable)")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--check", action="store_true",
                        help="license-gate only, no fetching")
    args = parser.parse_args(argv)
    if args.only:
        unknown = [n for n in args.only if n not in FIXTURES]
        if unknown:
            print(f"unknown fixture(s): {', '.join(unknown)}", file=sys.stderr)
            return 2
    if args.check:
        violations = license_gate(args.vendor_dir, args.only)
        for msg in violations:
            print(msg, file=sys.stderr)
        return 1 if violations else 0
    try:
        status = fetch_all(args.vendor_dir, args.only, args.retries)
    except FetchError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for name, state in status.items():
        print(f"{name}: {state}")
    violations = license_gate(args.vendor_dir,
                              args.only if args.only else None)
    for msg in violations:
        print(msg, file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
