"""Shared loaders for the PDK-VTT lane tests (stdlib + ruamel only)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ruamel.yaml import YAML

LANE_DIR = Path(__file__).resolve().parent
DOCS_DIR = LANE_DIR.parent.parent / "docs" / "pdk" / "vtt"
FIXTURES_DIR = LANE_DIR / "fixtures"

PROFILE_PATH = DOCS_DIR / "profile.yaml"
LAYERS_FIXTURE_PATH = FIXTURES_DIR / "layers.yaml"


def load_yaml(path: Path) -> dict:
    yaml = YAML(typ="safe")
    with open(path, encoding="utf-8") as fh:
        data = yaml.load(fh)
    assert isinstance(data, dict), f"{path} must parse to a mapping"
    return data


def load_profile() -> dict:
    assert PROFILE_PATH.is_file(), f"missing lane profile: {PROFILE_PATH}"
    return load_yaml(PROFILE_PATH)


def load_layers_fixture() -> dict:
    assert LAYERS_FIXTURE_PATH.is_file(), f"missing fixture: {LAYERS_FIXTURE_PATH}"
    return load_yaml(LAYERS_FIXTURE_PATH)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
