"""Packaging smoke: every declared module imports with zero logic.

This is the bundled-build gate before any behavior lands. Per-module RED
tests arrive with the first feature for that module (see module READMEs).
"""

import importlib

MODULES = [
    "rocket_engine",
    "rocket_engine.interfaces",
    "rocket_engine.project",
    "rocket_engine.execution",
    "rocket_engine.library",
    "rocket_engine.workflows",
    "rocket_engine.adapters",
]


def test_all_modules_import():
    for name in MODULES:
        assert importlib.import_module(name) is not None
