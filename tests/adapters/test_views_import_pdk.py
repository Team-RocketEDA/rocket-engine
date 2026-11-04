"""VIEWS-IMPORT-NO-PDK RED — import_gds activates a PDK before reading GDS.

Valid RED = the staged driver returns ``unreadable_source`` (No active
PDK) for import_gds jobs, because ``_activate`` returns early on
``doc is None`` without activating anything. The fix activates a PDK
on the import path (generic at minimum; the project cspdk tree when
the adapter already carries ``cspdk_path``), so a valid GDS returns
mappings plus the usual pin fallback instead.

Live tests (need the installed gdsfactory plus the vendored cspdk
tree for the GDS bytes); they fail loudly, never fake-green, where
the solver is absent.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
DRIVER = ROOT / "src" / "adapters" / "gdsfactory" / "_driver.py"
VENDORED_CSPDK = ROOT / "fixtures" / "upstream" / "cspdk"
SI340_GDS = (
    VENDORED_CSPDK
    / "cspdk"
    / "si340"
    / "gds"
    / "SOI340nm_1310nm_TE_STRIP_Waveguide.gds"
)

gf_present = importlib.util.find_spec("gdsfactory") is not None
needs_gf = pytest.mark.skipif(
    not gf_present,
    reason="gdsfactory not installed (uv sync)",
)
needs_gds = pytest.mark.skipif(
    not SI340_GDS.is_file(),
    reason="vendored si340 GDS unavailable "
    "(scripts/fetch_fixtures.py --only cspdk)",
)


def _run_import_job(tmp_path, cspdk_path=None):
    """Stage one import_gds job (no view spec) and run the driver."""
    job = {
        "recipe": "import_gds",
        "spec": "",
        "text": "",
        "doc": None,
        "gds_sources": [str(SI340_GDS)],
        "pin_map_path": None,
        "pin_map_doc": None,
        "cspdk_path": cspdk_path,
    }
    job_path = tmp_path / "gf_views_job.json"
    job_path.write_text(json.dumps(job), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(DRIVER), str(job_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=180,
    )
    begin = proc.stdout.find("ROCKETEDA_ENVELOPE_BEGIN")
    end = proc.stdout.find("ROCKETEDA_ENVELOPE_END")
    assert begin != -1 and end != -1, proc.stdout + proc.stderr
    return proc.returncode, json.loads(
        proc.stdout[begin:].splitlines()[1]
    )


@needs_gf
@needs_gds
def test_import_gds_without_spec_returns_mappings(tmp_path):
    """Import path activates the generic PDK: mappings, not no-PDK."""
    code, envelope = _run_import_job(tmp_path)
    assert code == 0, envelope
    assert envelope["ok"] is True, envelope
    result = envelope["result"]
    assert result["active_pdk"] == "generic"
    assert len(result["mappings"]) == 1
    assert result["mappings"][0]["source"] == SI340_GDS.name


@needs_gf
@needs_gds
def test_import_gds_with_cspdk_tree_reports_project_pdk(tmp_path):
    """Import path honors the carried cspdk tree: project PDK active."""
    code, envelope = _run_import_job(tmp_path, cspdk_path=str(VENDORED_CSPDK))
    assert code == 0, envelope
    assert envelope["ok"] is True, envelope
    result = envelope["result"]
    assert result["active_pdk"] == "cornerstone_si340"
    assert result["cspdk_version"] is not None
    assert len(result["mappings"]) == 1
