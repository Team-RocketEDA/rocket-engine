"""Runtime-modifiable project templates (TEMPLATE-RUNTIME).

The engine ships one versioned base shape; PDKs and power users
extend it with extra named areas and custom config without forking
the engine. Extensions land only where allowed: unknown top-level
keys fail loudly naming the key, area entries admit exactly name
plus label, and the `engine.` config namespace stays reserved for
the engine. Older templates migrate through registered one-step
links; newer-than-known templates refuse with future_format and
unlinked steps name their missing_migration.
"""

from __future__ import annotations

import copy
import re

from ruamel.yaml import YAML

from .errors import TemplateError

TEMPLATE_VERSION = 1

BASE_TEMPLATE_ID = "default"

_TOP_LEVEL_KEYS = frozenset(
    {"template_version", "id", "base", "description", "areas", "config"}
)

_AREA_KEYS = frozenset({"name", "label"})

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")

_RESERVED_CONFIG_PREFIX = "engine."

_SCALARS = (str, int, float, bool)

_MIGRATIONS = {}


def register_migration(old, new, fn):
    """Register one chained migration link between template versions.

    Links chain one step at a time (new must be old + 1); migrate
    walks them from the template version to the head. Registration
    is additive: engine upgrades add links, never rewrite old ones.

    Args:
        old: Source template_version this link migrates from.
        new: Target template_version (must be old + 1).
        fn: Callable taking the old mapping and returning the new
            mapping.

    Raises:
        TemplateError: invalid_migration for a skipped version
            step or a conflicting link, invalid_template when fn
            is not callable.
    """
    if not callable(fn):
        raise TemplateError(
            "invalid_template",
            f"Template migrator {old}->{new} is not callable.",
        )
    if new != old + 1:
        raise TemplateError(
            "invalid_migration",
            f"Template migration must step one version, got {old}->{new}.",
        )
    if old in _MIGRATIONS:
        raise TemplateError(
            "invalid_migration",
            f"Template already migrates from version {old}.",
        )
    _MIGRATIONS[old] = (new, fn)


def clear_migrations():
    """Drop registered migration links (a test seam, not a feature).

    Returns:
        Count of dropped links.
    """
    count = len(_MIGRATIONS)
    _MIGRATIONS.clear()
    return count


def _check_id(value, what):
    if not isinstance(value, str) or not _SLUG_RE.match(value):
        raise TemplateError(
            "invalid_template", f"Template {what} must be a slug: {value!r}."
        )


def _check_areas(areas):
    if not isinstance(areas, list):
        raise TemplateError(
            "invalid_template",
            f"Template areas must be a list: {areas!r}.",
        )
    for index, area in enumerate(areas):
        if not isinstance(area, dict):
            raise TemplateError(
                "invalid_template",
                f"Template areas[{index}] must be a mapping: {area!r}.",
            )
        unknown = set(area) - _AREA_KEYS
        if unknown:
            raise TemplateError(
                "invalid_template",
                f"Template areas[{index}] allows only "
                f"{sorted(_AREA_KEYS)}, got: {sorted(unknown)}.",
            )
        name = area.get("name")
        if not isinstance(name, str) or not _SLUG_RE.match(name):
            raise TemplateError(
                "invalid_template",
                f"Template areas[{index}] needs a slug name: {area!r}.",
            )
        label = area.get("label")
        if label is not None and not isinstance(label, str):
            raise TemplateError(
                "invalid_template",
                f"Template areas[{index}] label must be text: {area!r}.",
            )


def _check_config(config):
    if not isinstance(config, dict):
        raise TemplateError(
            "invalid_template",
            f"Template config must be a mapping: {config!r}.",
        )
    for key, value in config.items():
        if not isinstance(key, str) or not key:
            raise TemplateError(
                "invalid_template",
                f"Template config keys must be text: {key!r}.",
            )
        if key.startswith(_RESERVED_CONFIG_PREFIX):
            raise TemplateError(
                "invalid_template",
                f"Template config key {key!r} is engine-reserved "
                f"({_RESERVED_CONFIG_PREFIX}* namespace).",
            )
        if not isinstance(value, _SCALARS):
            raise TemplateError(
                "invalid_template",
                f"Template config {key!r} must be a scalar: {value!r}.",
            )


def validate_template(data):
    """Check one head-version template mapping against the base.

    Extensions land only where allowed: the fixed top-level key
    set, name-plus-label area entries, and scalar config outside
    the engine-reserved namespace.

    Args:
        data: Template mapping already at TEMPLATE_VERSION.

    Returns:
        Validated deep copy of the template mapping.

    Raises:
        TemplateError: invalid_template for a non-mapping,
            unknown key, bad id/base, or malformed area/config.
    """
    if not isinstance(data, dict):
        raise TemplateError(
            "invalid_template",
            f"Template must be a mapping: {data!r}.",
        )
    unknown = set(data) - _TOP_LEVEL_KEYS
    if unknown:
        raise TemplateError(
            "invalid_template",
            f"Template allows only {sorted(_TOP_LEVEL_KEYS)}, "
            f"got: {sorted(unknown)}.",
        )
    _check_id(data.get("id"), "id")
    base = data.get("base")
    if not isinstance(base, str) or not base:
        raise TemplateError(
            "invalid_template",
            f"Template base must name its base template: {base!r}.",
        )
    description = data.get("description")
    if description is not None and not isinstance(description, str):
        raise TemplateError(
            "invalid_template",
            f"Template description must be text: {description!r}.",
        )
    _check_areas(data.get("areas", []))
    _check_config(data.get("config", {}))
    return copy.deepcopy(data)


def migrate_template(data):
    """Migrate one template mapping to the known head version.

    Walks registered one-step links from the mapping's version
    upward; each step's output re-enters the chain so multi-step
    upgrades compose. Migration is pure (no I/O).

    Args:
        data: Template mapping at some older template_version.

    Returns:
        Migrated mapping stamped at TEMPLATE_VERSION.

    Raises:
        TemplateError: invalid_template for a non-mapping or a
            non-integer version, future_format for a mapping
            newer than the head, missing_migration for a version
            step with no registered link, invalid_migration when
            a migrator returns a non-mapping or raises.
    """
    if not isinstance(data, dict):
        raise TemplateError(
            "invalid_template",
            f"Template must be a mapping: {data!r}.",
        )
    version = data.get("template_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise TemplateError(
            "invalid_template",
            f"Template version must be an integer: {version!r}.",
        )
    if version > TEMPLATE_VERSION:
        raise TemplateError(
            "future_format",
            f"Template is at version {version}; "
            f"this engine knows {TEMPLATE_VERSION}.",
        )
    current = copy.deepcopy(data)
    while version < TEMPLATE_VERSION:
        link = _MIGRATIONS.get(version)
        if link is None:
            raise TemplateError(
                "missing_migration",
                f"No template migration from version {version}.",
            )
        new, fn = link
        try:
            current = fn(current)
        except TemplateError:
            raise
        except Exception as exc:
            raise TemplateError(
                "invalid_migration",
                f"Template migrator {version}->{new} failed: {exc}.",
            ) from exc
        if not isinstance(current, dict):
            raise TemplateError(
                "invalid_migration",
                f"Template migrator {version}->{new} "
                "did not return a mapping.",
            )
        current["template_version"] = new
        version = new
    return current


def load_template(data):
    """Migrate then validate one custom template mapping.

    Args:
        data: Custom template mapping at any known version.

    Returns:
        Validated template mapping at TEMPLATE_VERSION.

    Raises:
        TemplateError: future_format, missing_migration,
            invalid_migration, or invalid_template naming the
            violating key, area, or config entry.
    """
    return validate_template(migrate_template(data))


def loads_template(text):
    """Parse YAML text then migrate and validate one template.

    Args:
        text: YAML text of a custom template document.

    Returns:
        Validated template mapping at TEMPLATE_VERSION.

    Raises:
        TemplateError: invalid_template when the text is not a
            YAML mapping, plus every load_template verdict.
    """
    try:
        data = YAML(typ="safe").load(text)
    except Exception as exc:
        raise TemplateError(
            "invalid_template",
            f"Template is not YAML: {exc}.",
        ) from exc
    return load_template(data)
