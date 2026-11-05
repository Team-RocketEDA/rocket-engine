"""Render the README Requirements section from the setup catalogue.

Single source: src/interfaces/setup_catalogue.yaml. The README table
is generated, never hand-edited. Run:
    .venv/bin/python scripts/render_requirements.py [--check]

`--check` exits 1 when the README section is stale.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CATALOGUE = ROOT / "src" / "interfaces" / "setup_catalogue.yaml"
README = ROOT / "README.md"
START = "<!-- REQUIREMENTS:START -->"
END = "<!-- REQUIREMENTS:END -->"

KIND_ORDER = ["tool", "python", "pdk", "cloud"]
KIND_TITLE = {
    "tool": "Native tools (provision or PATH)",
    "python": "Python libraries (ride the wheel)",
    "pdk": "PDKs (registered trees, never in the wheel)",
    "cloud": "Cloud (opt-in only, never default)",
}


def _one_line(text):
    return re.sub(r"\s+", " ", str(text)).strip()


def _row(entry):
    kind = entry.get("kind")
    label = _one_line(entry.get("label", entry.get("id", "?")))
    if kind == "tool":
        provides = ", ".join(f"`{b}`" for b in entry.get("binaries", []))
    elif kind == "python":
        provides = ", ".join(f"`{p}`" for p in entry.get("python", []))
    elif kind == "pdk":
        decks = entry.get("decks", [])
        provides = f"`{entry.get('pdk_id', '?')}` + {len(decks)} decks"
    elif kind == "cloud":
        provides = f"BYOC: {entry.get('service', '?')}"
    else:
        provides = ""
    recipe = _one_line(entry.get("recipe", ""))
    return f"| {label} | {provides} | {recipe} |"


def render():
    data = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    lines = [
        "pip ships the engine, not the tools. Native binaries, PDK trees,",
        "and cloud keys arrive via provision recipes, your own PATH, or",
        "explicit opt-in. The engine resolves provisioned roots first, then",
        "ambient PATH, then per-job `tool_dir`; `report_capabilities` tells",
        "you exactly what resolved and the remedy for what did not.",
        "",
    ]
    for kind in KIND_ORDER:
        group = [e for e in entries if e.get("kind") == kind]
        if not group:
            continue
        lines.append(f"### {KIND_TITLE[kind]}")
        lines.append("")
        lines.append("| Capability | Provides | How to get it |")
        lines.append("|---|---|---|")
        lines.extend(_row(e) for e in group)
        lines.append("")
    return "\n".join(lines)


def main():
    body = render()
    text = README.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(START) + r".*?" + re.escape(END), re.DOTALL
    )
    replacement = f"{START}\n{body}{END}"
    if "--check" in sys.argv[1:]:
        match = pattern.search(text)
        if not match or match.group(0) != replacement:
            print("README requirements section is stale: run render_requirements.py")
            return 1
        print("README requirements section is fresh.")
        return 0
    updated, count = pattern.subn(replacement, text)
    if count != 1:
        print("README markers not found exactly once; refusing.")
        return 1
    README.write_text(updated, encoding="utf-8")
    print("README requirements section rendered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
