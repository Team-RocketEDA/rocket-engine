"""No-cloud guard: engine code must never import cloud clients.

gsim drags gdsfactoryplus in as a transitive dep; it rides unused.
MEOW pulls tidy3d the same way. This pins the rule: src/ and
scripts/ import neither, so no account/key/subscription can sit on
any engine hot path.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_checker():
    # RED: scripts/check_no_cloud.py does not exist yet.
    spec = importlib.util.spec_from_file_location(
        "check_no_cloud", ROOT / "scripts" / "check_no_cloud.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_cloud_imports_in_src_and_scripts():
    checker = _load_checker()
    violations = checker.scan([ROOT / "src", ROOT / "scripts"])
    assert violations == [], violations


def test_scanner_flags_planted_import(tmp_path):
    checker = _load_checker()
    planted = tmp_path / "evil.py"
    planted.write_text(
        "import gdsfactoryplus.gcloud as g\n", encoding="utf-8"
    )
    assert checker.scan_file(planted) != []
