"""Project canvas: editable design intent (`canvas.toml`).

The canvas states what the design must achieve — clocks, power,
analog specs, photonic targets, tool knobs — versioned,
closure-hashed, and failing loudly on any rule violation. It
builds on PDK data but never regurgitates it. The compiler
(SDC/decks) is CANVAS-CST-COMPILE scope; this package is the
foundation: schema tables, validation, closure, emission.
"""

from .schema import (
    CANVAS_SCHEMA,
    GENERIC_TOOL_KNOBS,
    HDL_LANGUAGES,
    KNOWN_METRICS,
    KNOWN_UNITS,
    OPERATORS,
    REF_SCOPES,
    TOOL_KNOBS,
)
from .validate import (
    CANVAS_FILENAME,
    CANVAS_VERSION,
    LEGACY_FILENAME,
    CanvasError,
    canvas_closure,
    dump_canvas_toml,
    load_project_canvas,
    validate_canvas,
)
from . import compile as compile_mod
from . import integrate as integrate_mod
from . import templates as templates_mod

__all__ = [
    "CANVAS_FILENAME",
    "CANVAS_SCHEMA",
    "CANVAS_VERSION",
    "GENERIC_TOOL_KNOBS",
    "HDL_LANGUAGES",
    "KNOWN_METRICS",
    "KNOWN_UNITS",
    "LEGACY_FILENAME",
    "OPERATORS",
    "REF_SCOPES",
    "TOOL_KNOBS",
    "CanvasError",
    "canvas_closure",
    "compile_mod",
    "dump_canvas_toml",
    "integrate_mod",
    "load_project_canvas",
    "templates_mod",
    "validate_canvas",
]
