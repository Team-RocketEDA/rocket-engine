"""Engine-owned design-truth settings store (SETTINGS-STORE).

Five versioned schemas hold every design decision the engine makes —
KiCad's `.kicad_pro` split, adopted as a rule, not code:

- ``chip.manifest``: project name, PDK ref+version, canvas list.
- ``design.rules``: nested ERC defaults, DRC deck ref, LVS config.
- ``net.classes``: default class plus per-net color/visibility split.
- ``text.vars``: scalar map with ClearUnknownKeys delete semantics.
- ``lib.tables``: resolve-only library refs (never written through).

Mechanics: ``meta.version`` per file, chained
``register_migration(old, new, fn)`` links, additive-params-first
migration, merge-onto-original preserving unknown keys,
future-format blocks autosave, byte-compare skip, atomic write, one
writer per key with unset-fill merge, and a resolved-config
snapshot per session/run for clients (never per-event round-trips).
"""

import copy
import io
import os
import tempfile
from pathlib import Path

from ruamel.yaml import YAML

# Design-truth kinds this engine version reads and writes.
CURRENT_VERSIONS = {
    "chip.manifest": 1,
    "design.rules": 1,
    "net.classes": 1,
    "text.vars": 1,
    "lib.tables": 1,
}

# Project-relative directory holding the five settings files.
SETTINGS_DIRNAME = "settings"

_FILENAMES = {kind: f"{kind}.yaml" for kind in CURRENT_VERSIONS}

# Data-map paths replaced wholesale by merge-onto-original: the new
# map is complete truth, so deletes inside propagate. Everywhere
# else the merge preserves original-only keys recursively, so keys
# this engine does not know survive a round-trip.
_REPLACE_PATHS = {
    "chip.manifest": frozenset(),
    "design.rules": frozenset({("erc", "checks")}),
    "net.classes": frozenset({("classes",), ("nets",)}),
    "text.vars": frozenset({("vars",)}),
    "lib.tables": frozenset({("tables",)}),
}

# (kind, old_version) -> (new_version, fn). Links chain one step at
# a time; migrate() walks from the file version to the head.
_MIGRATIONS = {}

_SCALARS = (str, int, float, bool)


class SettingsError(Exception):
    """Typed settings-store failure; `code` names the verdict.

    Codes: unknown_kind, invalid_settings, future_format,
    missing_migration, invalid_migration, migration_conflict,
    writer_conflict, unknown_library, missing_file.
    """

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _dump_yaml(data):
    """Canonical settings text (the byte-compare baseline)."""
    buf = io.StringIO()
    YAML(typ="safe").dump(copy.deepcopy(data), buf)
    return buf.getvalue()


def _load_yaml(text, path):
    """Parse settings text, failing loudly on non-mapping tops."""
    data = YAML(typ="safe").load(text)
    if not isinstance(data, dict):
        raise SettingsError(
            "invalid_settings", f"Top level must be a mapping: {path}."
        )
    return data


def _deep_merge(base, overlay):
    """Overlay wins; mappings merge recursively, lists replace."""
    if not isinstance(base, dict) or not isinstance(overlay, dict):
        return copy.deepcopy(overlay)
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _merge_onto_original(original, new, replace, path=()):
    """Merge `new` onto `original`, preserving unknown keys.

    Original-only keys survive recursively; conflicts resolve to
    `new`; data-map paths in `replace` (and every list) take `new`
    wholesale so deletes propagate there.
    """
    if path in replace or not isinstance(original, dict) or not isinstance(new, dict):
        return copy.deepcopy(new)
    result = copy.deepcopy(new)
    for key, value in original.items():
        if key not in result:
            result[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(result[key], dict):
            result[key] = _merge_onto_original(
                value, result[key], replace, path + (key,)
            )
    return result


def _require_kind(kind):
    """Fail loudly on an unknown settings kind."""
    if kind not in CURRENT_VERSIONS:
        raise SettingsError("unknown_kind", f"Unknown settings kind: {kind}.")
    return kind


def _head_version(kind):
    """Newest version this engine knows: current or migration head."""
    _require_kind(kind)
    head = CURRENT_VERSIONS[kind]
    for (reg_kind, _old), (new, _fn) in _MIGRATIONS.items():
        if reg_kind == kind and new > head:
            head = new
    return head


def _version_of(kind, data):
    """meta.version of a mapping, failing loudly when malformed."""
    meta = data.get("meta")
    version = meta.get("version") if isinstance(meta, dict) else None
    if isinstance(version, bool) or not isinstance(version, int):
        raise SettingsError(
            "invalid_settings",
            f"{kind} carries no integer meta.version.",
        )
    return version


def _is_nonempty_str(value):
    """True for non-blank strings only."""
    return isinstance(value, str) and value.strip() != ""


def _check_manifest(data):
    """Validate chip.manifest shape; unknown keys pass through."""
    if not _is_nonempty_str(data.get("name")):
        raise SettingsError(
            "invalid_settings", "chip.manifest needs a non-empty name."
        )
    pdk = data.get("pdk")
    if not isinstance(pdk, dict):
        raise SettingsError(
            "invalid_settings", "chip.manifest needs a pdk mapping."
        )
    for key in ("ref", "version"):
        if not _is_nonempty_str(pdk.get(key)):
            raise SettingsError(
                "invalid_settings",
                f"chip.manifest pdk needs a non-empty {key}.",
            )
    canvases = data.get("canvases")
    if not isinstance(canvases, list) or not canvases:
        raise SettingsError(
            "invalid_settings", "chip.manifest needs a non-empty canvas list."
        )
    for canvas in canvases:
        if not isinstance(canvas, dict) or not _is_nonempty_str(canvas.get("name")):
            raise SettingsError(
                "invalid_settings", "Every chip.manifest canvas needs a name."
            )


def _check_rules(data):
    """Validate design.rules shape; unknown keys pass through."""
    erc = data.get("erc")
    if not isinstance(erc, dict) or not isinstance(erc.get("default"), bool):
        raise SettingsError(
            "invalid_settings", "design.rules erc needs a bool default."
        )
    checks = erc.get("checks")
    if not isinstance(checks, dict):
        raise SettingsError(
            "invalid_settings", "design.rules erc needs a checks mapping."
        )
    for name, enabled in checks.items():
        if not isinstance(enabled, bool):
            raise SettingsError(
                "invalid_settings",
                f"design.rules erc check {name!r} must be on/off.",
            )
    drc = data.get("drc")
    deck = drc.get("deck") if isinstance(drc, dict) else None
    if not isinstance(deck, dict) or not _is_nonempty_str(deck.get("ref")):
        raise SettingsError(
            "invalid_settings", "design.rules drc needs a deck ref."
        )
    if not isinstance(data.get("lvs"), dict):
        raise SettingsError(
            "invalid_settings", "design.rules needs an lvs mapping."
        )


def _check_classes(data):
    """Validate net.classes shape; unknown keys pass through."""
    classes = data.get("classes")
    if not isinstance(classes, dict) or not classes:
        raise SettingsError(
            "invalid_settings", "net.classes needs a non-empty classes map."
        )
    for name, entry in classes.items():
        if not isinstance(entry, dict):
            raise SettingsError(
                "invalid_settings", f"net.classes class {name!r} must map."
            )
        if not _is_nonempty_str(entry.get("color")):
            raise SettingsError(
                "invalid_settings",
                f"net.classes class {name!r} needs a color.",
            )
        if not isinstance(entry.get("visible"), bool):
            raise SettingsError(
                "invalid_settings",
                f"net.classes class {name!r} needs visible on/off.",
            )
    if data.get("default") not in classes:
        raise SettingsError(
            "invalid_settings", "net.classes default names no known class."
        )
    nets = data.get("nets")
    if not isinstance(nets, dict):
        raise SettingsError(
            "invalid_settings", "net.classes needs a nets mapping."
        )
    for net, class_name in nets.items():
        if class_name not in classes:
            raise SettingsError(
                "invalid_settings",
                f"net.classes net {net!r} names no known class.",
            )


def _check_text_vars(data):
    """Validate text.vars scalars; unknown top-level keys pass through."""
    variables = data.get("vars")
    if not isinstance(variables, dict):
        raise SettingsError(
            "invalid_settings", "text.vars needs a vars mapping."
        )
    for name, value in variables.items():
        if not isinstance(value, _SCALARS):
            raise SettingsError(
                "invalid_settings",
                f"text.vars var {name!r} must be a scalar.",
            )


def _check_lib_tables(data):
    """Validate lib.tables refs; unknown keys pass through."""
    tables = data.get("tables")
    if not isinstance(tables, dict):
        raise SettingsError(
            "invalid_settings", "lib.tables needs a tables mapping."
        )
    for name, entry in tables.items():
        if not isinstance(entry, dict) or not _is_nonempty_str(entry.get("ref")):
            raise SettingsError(
                "invalid_settings", f"lib.tables entry {name!r} needs a ref."
            )


_CHECKS = {
    "chip.manifest": _check_manifest,
    "design.rules": _check_rules,
    "net.classes": _check_classes,
    "text.vars": _check_text_vars,
    "lib.tables": _check_lib_tables,
}


def default_settings(kind):
    """Build fresh defaults for one settings kind.

    Args:
        kind: Settings kind (one of CURRENT_VERSIONS).

    Returns:
        Valid settings mapping stamped at the current version.

    Raises:
        SettingsError: unknown_kind for an uncataloged kind.
    """
    _require_kind(kind)
    meta = {"version": CURRENT_VERSIONS[kind]}
    if kind == "chip.manifest":
        return {
            "meta": meta,
            "name": "untitled",
            "pdk": {"ref": "unassigned", "version": "unassigned"},
            "canvases": [{"name": "top"}],
        }
    if kind == "design.rules":
        return {
            "meta": meta,
            "erc": {
                "default": True,
                "checks": {
                    "short": True,
                    "open": True,
                    "unconnected_pin": True,
                    "power_pin": True,
                },
            },
            "drc": {"deck": {"ref": "unassigned", "version": "unassigned"}},
            "lvs": {"tool": "unassigned", "options": {}},
        }
    if kind == "net.classes":
        return {
            "meta": meta,
            "default": "signal",
            "classes": {
                "signal": {"color": "#3fa9f5", "visible": True},
                "power": {"color": "#e74c3c", "visible": True},
            },
            "nets": {"VDD": "power", "VSS": "power"},
        }
    if kind == "text.vars":
        return {"meta": meta, "vars": {}}
    return {"meta": meta, "tables": {}}


def fresh_project_settings(name, pdk_ref, pdk_version, canvases=()):
    """Build a fresh project's full design truth (all five kinds).

    Args:
        name: Project/chip name for the manifest.
        pdk_ref: PDK reference (e.g. sky130A).
        pdk_version: PDK version string.
        canvases: Canvas names or {name, ...} mappings; a lone
            "top" canvas when omitted.

    Returns:
        Mapping of settings kind to valid current-version data.

    Raises:
        SettingsError: invalid_settings for a blank name, PDK
            ref/version, or a canvas without a name.
    """
    if not _is_nonempty_str(name):
        raise SettingsError(
            "invalid_settings", "Fresh projects need a non-empty name."
        )
    if not _is_nonempty_str(pdk_ref) or not _is_nonempty_str(pdk_version):
        raise SettingsError(
            "invalid_settings", "Fresh projects need a PDK ref+version."
        )
    normalized = []
    for canvas in canvases:
        entry = {"name": canvas} if isinstance(canvas, str) else dict(canvas)
        if not _is_nonempty_str(entry.get("name")):
            raise SettingsError(
                "invalid_settings", "Every fresh canvas needs a name."
            )
        normalized.append(entry)
    fresh = {kind: default_settings(kind) for kind in CURRENT_VERSIONS}
    manifest = fresh["chip.manifest"]
    manifest["name"] = name
    manifest["pdk"] = {"ref": pdk_ref, "version": pdk_version}
    if normalized:
        manifest["canvases"] = normalized
    return fresh


def validate_settings(kind, data):
    """Validate one settings mapping against its kind schema.

    Unknown keys pass through untouched (merge-onto-original owns
    them); only known-key shapes and the head version are judged.

    Args:
        kind: Settings kind (one of CURRENT_VERSIONS).
        data: Settings mapping to validate.

    Returns:
        The same mapping, unchanged, when valid.

    Raises:
        SettingsError: unknown_kind for an uncataloged kind,
            invalid_settings for a non-mapping, a version that is
            not the known head, or a misshapen known key.
    """
    _require_kind(kind)
    if not isinstance(data, dict):
        raise SettingsError(
            "invalid_settings", f"{kind} settings must be a mapping."
        )
    version = _version_of(kind, data)
    head = _head_version(kind)
    if version != head:
        raise SettingsError(
            "invalid_settings",
            f"{kind} is at version {version}, want {head}.",
        )
    _CHECKS[kind](data)
    return data


def settings_version(kind, data):
    """Read one settings mapping's meta.version.

    Args:
        kind: Settings kind (one of CURRENT_VERSIONS).
        data: Settings mapping to inspect.

    Returns:
        Integer meta.version carried by the mapping.

    Raises:
        SettingsError: unknown_kind for an uncataloged kind,
            invalid_settings for a non-mapping or a version that
            is not an integer.
    """
    _require_kind(kind)
    if not isinstance(data, dict):
        raise SettingsError(
            "invalid_settings", f"{kind} settings must be a mapping."
        )
    return _version_of(kind, data)


def register_migration(kind, old, new, fn):
    """Register one chained migration link for a settings kind.

    Links chain one step at a time (new must be old + 1); migrate()
    walks them from the file version to the head. Registration is
    additive: engine upgrades add links, never rewrite old ones.

    Args:
        kind: Settings kind (one of CURRENT_VERSIONS).
        old: Source meta.version this link migrates from.
        new: Target meta.version (must be old + 1).
        fn: Callable taking the old mapping and returning the new
            mapping; additive-params-first means its output lands
            on top of defaults, so new params exist even where
            the migrator says nothing.

    Raises:
        SettingsError: unknown_kind for an uncataloged kind,
            invalid_migration for a skipped version step,
            migration_conflict when a link already leaves old.
    """
    _require_kind(kind)
    if new != old + 1:
        raise SettingsError(
            "invalid_migration",
            f"{kind} migration must step one version, got {old}->{new}.",
        )
    if (kind, old) in _MIGRATIONS:
        raise SettingsError(
            "migration_conflict",
            f"{kind} already migrates from version {old}.",
        )
    _MIGRATIONS[(kind, old)] = (new, fn)


def clear_migrations(kind=None):
    """Drop registered migration links (a test seam, not a feature).

    Args:
        kind: Drop only this kind's links; all links when omitted.

    Returns:
        Count of links dropped.

    Raises:
        SettingsError: unknown_kind for an uncataloged kind.
    """
    if kind is not None:
        _require_kind(kind)
    doomed = [key for key in _MIGRATIONS if kind is None or key[0] == kind]
    for key in doomed:
        del _MIGRATIONS[key]
    return len(doomed)


def migrate(kind, data):
    """Migrate one settings mapping to the known head version.

    Walks registered links from the mapping's meta.version upward.
    Additive-params-first: each step lands the migrator's output on
    top of defaults, so brand-new params exist even where the
    migrator says nothing. Migration is pure (no I/O); callers
    persist the result through the normal save path.

    Args:
        kind: Settings kind (one of CURRENT_VERSIONS).
        data: Settings mapping at some older meta.version.

    Returns:
        Migrated mapping stamped and validated at the head.

    Raises:
        SettingsError: unknown_kind for an uncataloged kind,
            invalid_settings for a non-mapping or a version that
            is not an integer, future_format for a mapping newer
            than the head, missing_migration for a version step
            with no registered link, invalid_migration when a
            migrator returns a non-mapping or raises.
    """
    _require_kind(kind)
    if not isinstance(data, dict):
        raise SettingsError(
            "invalid_settings", f"{kind} settings must be a mapping."
        )
    version = _version_of(kind, data)
    head = _head_version(kind)
    if version > head:
        raise SettingsError(
            "future_format",
            f"{kind} is at version {version}; this engine knows {head}.",
        )
    current = copy.deepcopy(data)
    while version < head:
        link = _MIGRATIONS.get((kind, version))
        if link is None:
            raise SettingsError(
                "missing_migration",
                f"{kind} has no migration from version {version}.",
            )
        new, fn = link
        try:
            stepped = fn(copy.deepcopy(current))
        except SettingsError:
            raise
        except Exception as exc:
            raise SettingsError(
                "invalid_migration",
                f"{kind} migration {version}->{new} failed: {exc}.",
            ) from exc
        if not isinstance(stepped, dict):
            raise SettingsError(
                "invalid_migration",
                f"{kind} migration {version}->{new} returned no mapping.",
            )
        current = _deep_merge(default_settings(kind), stepped)
        current["meta"] = {"version": new}
        version = new
    current["meta"] = {"version": head}
    return validate_settings(kind, current)


def apply_update(kind, current, update):
    """Apply a patch onto loaded settings, honoring delete semantics.

    Structured kinds deep-merge the patch (overlay wins, lists
    replace). text.vars uses ClearUnknownKeys semantics: a patch
    carrying `vars` replaces the whole map, so keys the patch omits
    are deleted. The patch never moves meta.version.

    Args:
        kind: Settings kind (one of CURRENT_VERSIONS).
        current: Loaded settings mapping (usually at the head).
        update: Patch mapping to apply.

    Returns:
        New settings mapping at the current version.

    Raises:
        SettingsError: unknown_kind for an uncataloged kind,
            invalid_settings for a non-mapping patch or a patch
            that breaks the kind schema.
    """
    _require_kind(kind)
    if not isinstance(update, dict):
        raise SettingsError(
            "invalid_settings", f"{kind} update must be a mapping."
        )
    overlay = {k: v for k, v in update.items() if k != "meta"}
    if kind == "text.vars" and "vars" in overlay:
        merged = _deep_merge(current, {k: v for k, v in overlay.items() if k != "vars"})
        merged["vars"] = copy.deepcopy(overlay["vars"])
    else:
        merged = _deep_merge(current, overlay)
    merged["meta"] = {"version": _head_version(kind)}
    return validate_settings(kind, merged)


def merge_writer_maps(base, writes):
    """Merge per-writer maps with one writer per key.

    Each top-level key may be set by at most one writer; keys no
    writer sets are filled from the base (unset-fill merge).

    Args:
        base: Baseline mapping supplying unset keys.
        writes: Mapping of writer name to that writer's map.

    Returns:
        Merged mapping: base plus every writer's keys.

    Raises:
        SettingsError: invalid_settings for a non-mapping base or
            writer map, writer_conflict when two writers set the
            same key (both writers named).
    """
    if not isinstance(base, dict):
        raise SettingsError(
            "invalid_settings", "Merge base must be a mapping."
        )
    if not isinstance(writes, dict):
        raise SettingsError(
            "invalid_settings", "Writer maps must be a mapping."
        )
    merged = copy.deepcopy(base)
    owners = {}
    for writer, mapping in writes.items():
        if not isinstance(mapping, dict):
            raise SettingsError(
                "invalid_settings", f"Writer {writer!r} set no mapping."
            )
        for key, value in mapping.items():
            if key in owners:
                raise SettingsError(
                    "writer_conflict",
                    f"Key {key!r} set by both {owners[key]!r} "
                    f"and {writer!r}.",
                )
            owners[key] = writer
            merged[key] = copy.deepcopy(value)
    return merged


def resolve_library(tables, name, roots):
    """Resolve one lib.tables entry to a path (read-only, pure read).

    lib.tables is resolve-only: refs point at libraries the store
    never writes. Absolute refs resolve in place; relative refs try
    each root in order. No probing writes anything anywhere.

    Args:
        tables: lib.tables settings mapping.
        name: Logical library name to resolve.
        roots: Candidate root directories for relative refs.

    Returns:
        Path of the first existing referent.

    Raises:
        SettingsError: unknown_library for an uncataloged name, an
            absolute ref that does not exist, or a relative ref
            found under no root.
    """
    entries = tables.get("tables") if isinstance(tables, dict) else None
    entry = entries.get(name) if isinstance(entries, dict) else None
    ref = entry.get("ref") if isinstance(entry, dict) else None
    if not _is_nonempty_str(ref):
        raise SettingsError(
            "unknown_library", f"No library cataloged as {name!r}."
        )
    if os.path.isabs(ref):
        candidate = Path(ref)
        if candidate.exists():
            return candidate
        raise SettingsError(
            "unknown_library", f"Library {name!r} ref missing: {ref}."
        )
    for root in roots:
        candidate = Path(root) / ref
        if candidate.exists():
            return candidate
    raise SettingsError(
        "unknown_library", f"Library {name!r} ref missing: {ref}."
    )


class SettingsFile:
    """One settings file on disk plus its load-time baseline.

    Args:
        kind: Settings kind (one of CURRENT_VERSIONS).
        path: File the bytes were read from.
        data: Parsed settings mapping.
        original_text: Exact bytes read (byte-compare baseline).
        future: True when the file version is newer than the head —
            reads are allowed, saves are refused.
    """

    def __init__(self, kind, path, data, original_text, future):
        self.kind = kind
        self.path = Path(path)
        self.data = data
        self.original_text = original_text
        self.future = future


def load_settings_file(path, kind=None):
    """Load one settings file with its byte baseline.

    Args:
        path: Settings file to read.
        kind: Settings kind override; derived from the
            `<kind>.yaml` filename when omitted.

    Returns:
        SettingsFile with parsed data and the original text; future
        files load with future=True for inspection.

    Raises:
        SettingsError: unknown_kind for an uncataloged kind,
            missing_file for an absent path, invalid_settings for
            unreadable YAML or a non-mapping top without an
            integer meta.version.
    """
    path = Path(path)
    if kind is None:
        stem = path.name
        stem = stem[: -len(".yaml")] if stem.endswith(".yaml") else stem
        kind = stem
    _require_kind(kind)
    if not path.is_file():
        raise SettingsError("missing_file", f"No settings file: {path}.")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SettingsError(
            "invalid_settings", f"Cannot read settings file {path}: {exc}."
        ) from exc
    try:
        data = YAML(typ="safe").load(text)
    except Exception as exc:
        raise SettingsError(
            "invalid_settings", f"Cannot parse settings file {path}: {exc}."
        ) from exc
    if not isinstance(data, dict):
        raise SettingsError(
            "invalid_settings", f"Top level must be a mapping: {path}."
        )
    version = _version_of(kind, data)
    return SettingsFile(
        kind=kind,
        path=path,
        data=data,
        original_text=text,
        future=version > _head_version(kind),
    )


def dump_settings_text(data):
    """Render canonical settings text (byte baseline + doc payload).

    Args:
        data: Settings mapping to serialize.

    Returns:
        Canonical YAML text for byte-compare and storage.
    """
    return _dump_yaml(data)


def merge_settings(kind, original, new):
    """Merge new truth onto stored truth, preserving unknown keys.

    The composition root persists settings through document CRUD,
    so it merges through this seam instead of the file saver: same
    replace-paths, same unknown-key preservation, no I/O.

    Args:
        kind: Settings kind (one of CURRENT_VERSIONS).
        original: Stored settings mapping, or None for a first
            write.
        new: Complete settings mapping at the head version.

    Returns:
        Merged mapping ready to validate and store.

    Raises:
        SettingsError: unknown_kind for an uncataloged kind,
            invalid_settings for stored or new data that breaks
            the kind schema.
    """
    _require_kind(kind)
    validate_settings(kind, new)
    if original is None:
        return copy.deepcopy(new)
    if not isinstance(original, dict):
        raise SettingsError(
            "invalid_settings", f"Stored {kind} settings must be a mapping."
        )
    return _merge_onto_original(original, new, _REPLACE_PATHS[kind])


def _atomic_write_text(path, text):
    """Write through a sibling temp file, then rename into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_settings_file(settings_file, data=None):
    """Save one settings file: merge, byte-compare, atomic write.

    Merges the data onto the original bytes (unknown keys survive),
    skips the write when the bytes are unchanged, and writes
    atomically otherwise. Future files refuse: autosave never
    clobbers a newer format.

    Args:
        settings_file: Loaded SettingsFile carrying the baseline.
        data: Settings mapping to save; the loaded data when
            omitted.

    Returns:
        Mapping with written (bool), path (str), and version.

    Raises:
        SettingsError: future_format for a file newer than the
            head, invalid_settings for data that breaks the kind
            schema.

    Caution: Rewrites the file in place when bytes differ — but
        never touches a future file, and validation runs before
        any byte is written.
    """
    if settings_file.future:
        raise SettingsError(
            "future_format",
            f"{settings_file.kind} file is newer than this engine "
            "knows; refusing autosave.",
        )
    new_data = settings_file.data if data is None else data
    validate_settings(settings_file.kind, new_data)
    original = _load_yaml(settings_file.original_text, settings_file.path)
    merged = _merge_onto_original(
        original, new_data, _REPLACE_PATHS[settings_file.kind]
    )
    text = _dump_yaml(merged)
    if text == settings_file.original_text:
        return {
            "written": False,
            "path": str(settings_file.path),
            "version": _head_version(settings_file.kind),
        }
    _atomic_write_text(settings_file.path, text)
    settings_file.data = merged
    settings_file.original_text = text
    return {
        "written": True,
        "path": str(settings_file.path),
        "version": _head_version(settings_file.kind),
    }


def snapshot_settings(settings, session_id=None, run_id=None, library_roots=()):
    """Bundle validated per-kind mappings into a resolved snapshot.

    One call returns all five kinds plus versions, so clients render
    from a single snapshot instead of per-event round-trips. Library
    entries report their ref plus the resolved path (None when
    unresolvable — resolution strictness lives in
    resolve_libraries, never breaks a read).

    Args:
        settings: Mapping covering all five settings kinds.
        session_id: Client session this snapshot serves.
        run_id: Run this snapshot was resolved for, if any.
        library_roots: Candidate roots for resolving lib refs;
            refs stay unresolved when empty.

    Returns:
        Snapshot mapping with session_id, run_id, versions,
        settings (all five kinds), and libraries (each with ref
        plus resolved path or None).

    Raises:
        SettingsError: invalid_settings when a kind is missing
            or a mapping breaks its kind schema.
    """
    if not isinstance(settings, dict) or set(settings) != set(CURRENT_VERSIONS):
        raise SettingsError(
            "invalid_settings", "A resolved snapshot covers all five kinds."
        )
    for kind, data in settings.items():
        validate_settings(kind, data)
    libraries = {}
    for name, entry in settings["lib.tables"].get("tables", {}).items():
        ref = entry.get("ref")
        resolved = None
        if library_roots and _is_nonempty_str(ref):
            try:
                resolved = str(
                    resolve_library(settings["lib.tables"], name, library_roots)
                )
            except SettingsError:
                resolved = None
        libraries[name] = {"ref": ref, "resolved": resolved}
    return {
        "session_id": session_id,
        "run_id": run_id,
        "versions": {
            kind: settings[kind]["meta"]["version"] for kind in CURRENT_VERSIONS
        },
        "settings": copy.deepcopy(settings),
        "libraries": libraries,
    }


class SettingsStore:
    """Five settings files under one project root (or in memory).

    File mode keeps `<root>/settings/<kind>.yaml` with byte-compare
    skip and atomic writes; memory mode (root None) keeps the same
    texts in a private map with identical merge semantics. Loads
    migrate in memory and never write; writes validate first, refuse
    future on-disk files, then merge-onto-original.

    Args:
        root: Project directory owning the settings files; None
            keeps an isolated in-memory store.
    """

    def __init__(self, root=None):
        self._root = Path(root) if root is not None else None
        self._memory = {} if root is None else None

    def _path(self, kind):
        """Filesystem path for one kind (file mode only)."""
        return self._root / SETTINGS_DIRNAME / _FILENAMES[kind]

    def _read_text(self, kind):
        """Current canonical text for one kind, or None when absent."""
        if self._memory is not None:
            return self._memory.get(kind)
        path = self._path(kind)
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def _store_text(self, kind, text):
        """Persist canonical text through the active backend."""
        if self._memory is not None:
            self._memory[kind] = text
            return None
        path = self._path(kind)
        _atomic_write_text(path, text)
        return str(path)

    def ensure_fresh(self, name, pdk_ref, pdk_version, canvases=()):
        """Create missing settings files from fresh project truth.

        Existing files are never touched: freshness fills gaps,
        never clobbers.

        Args:
            name: Project/chip name for the manifest.
            pdk_ref: PDK reference (e.g. sky130A).
            pdk_version: PDK version string.
            canvases: Canvas names or {name, ...} mappings.

        Returns:
            Sorted list of kinds created by this call.

        Raises:
            SettingsError: invalid_settings for a blank name, PDK
                ref/version, or a canvas without a name.

        Caution: Writes files for every missing kind — but only
            for missing kinds; existing truth is left byte-alone.
        """
        fresh = fresh_project_settings(name, pdk_ref, pdk_version, canvases)
        created = []
        for kind, data in fresh.items():
            if self._read_text(kind) is None:
                self._store_text(kind, _dump_yaml(data))
                created.append(kind)
        return sorted(created)

    def load(self, kind):
        """Load one kind, migrated in memory to the head version.

        Loads never write: migration lands in the returned mapping,
        and the next write persists it. Future on-disk files fail
        instead of serving truth this engine cannot validate.

        Args:
            kind: Settings kind (one of CURRENT_VERSIONS).

        Returns:
            Valid settings mapping at the known head version.

        Raises:
            SettingsError: unknown_kind for an uncataloged kind,
                missing_file for a kind with no stored text,
                future_format for a file newer than the head,
                missing_migration when no link covers the stored
                version, invalid_settings for unparsable text.
        """
        _require_kind(kind)
        text = self._read_text(kind)
        if text is None:
            raise SettingsError(
                "missing_file", f"No stored settings for {kind}."
            )
        data = _load_yaml(text, kind)
        version = _version_of(kind, data)
        head = _head_version(kind)
        if version > head:
            raise SettingsError(
                "future_format",
                f"{kind} is at version {version}; this engine knows {head}.",
            )
        if version < head:
            return migrate(kind, data)
        return validate_settings(kind, copy.deepcopy(data))

    def write(self, kind, data):
        """Replace one kind's truth, preserving unknown keys.

        Validates before touching anything, refuses when the stored
        file is newer than the head, merges onto the stored bytes,
        skips the write when bytes are unchanged, and writes
        atomically otherwise.

        Args:
            kind: Settings kind (one of CURRENT_VERSIONS).
            data: Complete settings mapping at the head version.

        Returns:
            Mapping with written (bool), path (str, None for the
            memory backend), and version.

        Raises:
            SettingsError: unknown_kind for an uncataloged kind,
                invalid_settings for data that breaks the kind
                schema, future_format when the stored file is
                newer than the head.

        Caution: Rewrites the stored file when bytes differ — full
            replacement of data maps (deletes propagate), unknown
            extension keys preserved, future files never touched.
        """
        _require_kind(kind)
        validate_settings(kind, data)
        stored = self._read_text(kind)
        if stored is not None:
            original = _load_yaml(stored, kind)
            if _version_of(kind, original) > _head_version(kind):
                raise SettingsError(
                    "future_format",
                    f"{kind} file is newer than this engine knows; "
                    "refusing autosave.",
                )
            merged = _merge_onto_original(
                original, data, _REPLACE_PATHS[kind]
            )
        else:
            merged = copy.deepcopy(data)
        text = _dump_yaml(merged)
        if stored is not None and text == stored:
            return {
                "written": False,
                "path": str(self._path(kind)) if self._root else None,
                "version": _head_version(kind),
            }
        path = self._store_text(kind, text)
        return {"written": True, "path": path, "version": _head_version(kind)}

    def update(self, kind, patch):
        """Patch one kind's truth (text.vars deletes propagate).

        Args:
            kind: Settings kind (one of CURRENT_VERSIONS).
            patch: Patch mapping (see apply_update).

        Returns:
            Save-result mapping (see write).

        Raises:
            SettingsError: unknown_kind for an uncataloged kind,
                missing_file for a kind with no stored truth,
                invalid_settings for a patch that breaks the kind
                schema, future_format when the stored file is
                newer than the head.

        Caution: Persists the patched truth — text.vars patches
            carrying `vars` delete omitted keys.
        """
        return self.write(kind, apply_update(kind, self.load(kind), patch))

    def merge_writes(self, kind, writes):
        """Merge one-writer-per-key maps onto one kind's truth.

        Args:
            kind: Settings kind (one of CURRENT_VERSIONS).
            writes: Mapping of writer name to that writer's map.

        Returns:
            Save-result mapping (see write).

        Raises:
            SettingsError: unknown_kind for an uncataloged kind,
                missing_file for a kind with no stored truth,
                writer_conflict when two writers set the same key,
                invalid_settings for a merged map that breaks the
                kind schema.

        Caution: Persists the merged truth.
        """
        return self.write(
            kind, merge_writer_maps(self.load(kind), writes)
        )

    def resolve_libraries(self, roots):
        """Resolve every lib.tables entry against candidate roots.

        Args:
            roots: Candidate root directories for relative refs.

        Returns:
            Mapping of logical library name to resolved Path.

        Raises:
            SettingsError: missing_file when lib.tables has no
                stored truth, unknown_library for the first entry
                found under no root — strict, no silent skip.
        """
        tables = self.load("lib.tables")
        return {
            name: resolve_library(tables, name, roots)
            for name in tables.get("tables", {})
        }

    def snapshot(self, session_id=None, run_id=None, library_roots=()):
        """Bundle the resolved config for one session/run fetch.

        One call returns all five kinds plus versions, so clients
        render from a single snapshot instead of per-event
        round-trips. Library entries report their ref plus the
        resolved path (None when unresolvable — resolution strictness
        lives in resolve_libraries, never breaks a read).

        Args:
            session_id: Client session this snapshot serves.
            run_id: Run this snapshot was resolved for, if any.
            library_roots: Candidate roots for resolving lib refs;
                refs stay unresolved when empty.

        Returns:
            Snapshot mapping with session_id, run_id, versions,
            settings (all five kinds), and libraries (each with ref
            plus resolved path or None).

        Raises:
            SettingsError: missing_file when any kind has no stored
                truth, future_format when any stored file is newer
                than the head, invalid_settings when stored truth
                breaks its kind schema.
        """
        settings = {kind: self.load(kind) for kind in CURRENT_VERSIONS}
        return snapshot_settings(
            settings,
            session_id=session_id,
            run_id=run_id,
            library_roots=library_roots,
        )
