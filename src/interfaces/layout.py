"""Folder-schema parser + validator (LAYOUT-SCHEMA).

Checks a tree against layout_schema.yaml, derives and verifies
.gitignore from tracked flags, and refuses newer-than-known version
stamps loudly instead of misreading. Policy files use the
zero-silent-defaults rule: template ships defaults, required entries
must be present and non-empty.
"""

import copy
import re
from pathlib import Path

from ruamel.yaml import YAML

from .errors import ContractError

SCHEMA_VERSION = 1

_SCHEMA_PATH = Path(__file__).parent / "layout_schema.yaml"
_VERSION_FILENAME = "layout.version"
_GITIGNORE_HEADER = (
    "# Engine exhaust (derived from layout_schema.yaml v1; do not edit by hand)."
)


class LayoutError(ContractError):
    """Layout-schema violation with a stable machine code."""


def _yaml():
    return YAML(typ="safe")


def _load_yaml_file(path):
    try:
        return _yaml().load(Path(path).read_text())
    except LayoutError:
        raise
    except Exception as exc:
        raise LayoutError(
            "invalid_yaml", f"Cannot parse {path}: {exc}."
        ) from exc


def _check_entry_struct(entry, where):
    for field in (
        "name", "type", "match", "required", "tracked",
        "created_by", "mutable", "description",
    ):
        if field not in entry:
            raise LayoutError(
                "invalid_schema", f"Entry at {where} misses field: {field}."
            )
    if entry["type"] not in ("dir", "file"):
        raise LayoutError(
            "invalid_schema", f"Entry at {where} has bad type: {entry['type']!r}."
        )
    if entry["match"] not in ("exact", "pattern"):
        raise LayoutError(
            "invalid_schema", f"Entry at {where} has bad match: {entry['match']!r}."
        )
    if entry["match"] == "pattern" and not entry.get("pattern"):
        raise LayoutError(
            "invalid_schema", f"Pattern entry at {where} needs a pattern."
        )
    if entry["type"] == "dir":
        for child in entry.get("children", []) or []:
            _check_entry_struct(child, f"{where}/{entry['name']}")
    else:
        if not entry.get("format"):
            raise LayoutError(
                "invalid_schema", f"File entry at {where} needs a format."
            )


def load_schema(path=None):
    """Load and structurally validate the folder schema."""
    schema_path = Path(path) if path is not None else _SCHEMA_PATH
    try:
        data = _yaml().load(schema_path.read_text())
    except Exception as exc:
        raise LayoutError(
            "invalid_schema", f"Cannot load schema {schema_path}: {exc}."
        ) from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise LayoutError(
            "invalid_schema",
            f"Schema {schema_path} must carry schema_version {SCHEMA_VERSION}.",
        )
    for section in ("engine_root", "linked_project"):
        entries = data.get(section)
        if not isinstance(entries, list):
            raise LayoutError(
                "invalid_schema", f"Schema section missing: {section}."
            )
        for entry in entries:
            _check_entry_struct(entry, section)
    template = data.get("policy_template") or {}
    if not isinstance(template.get("required"), list) or not isinstance(
        template.get("defaults"), dict
    ):
        raise LayoutError("invalid_schema", "policy_template needs required + defaults.")
    return data


def _is_empty(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def template_defaults(schema=None):
    """Return a copy of the policy template defaults."""
    data = schema if schema is not None else load_schema()
    return copy.deepcopy(data["policy_template"]["defaults"])


def validate_policy(policy, schema=None):
    """Enforce present + non-empty on every template-required key."""
    data = schema if schema is not None else load_schema()
    template = data["policy_template"]
    if not isinstance(policy, dict):
        raise LayoutError("invalid_policy", "Policy must be a mapping.")
    defaults = template["defaults"]
    for key in template["required"]:
        if key not in policy:
            raise LayoutError(
                "missing_policy", f"Missing required policy entry: {key}.",
                fields=[key],
            )
        if _is_empty(policy[key]):
            raise LayoutError(
                "empty_policy",
                f"Required policy entry is empty: {key}.",
                fields=[key],
            )
        default = defaults.get(key)
        value = policy[key]
        if isinstance(default, dict) and isinstance(value, dict):
            for sub in default:
                if sub not in value:
                    raise LayoutError(
                        "missing_policy",
                        f"Missing required policy entry: {key}.{sub}.",
                        fields=[f"{key}.{sub}"],
                    )
                if _is_empty(value[sub]):
                    raise LayoutError(
                        "empty_policy",
                        f"Required policy entry is empty: {key}.{sub}.",
                        fields=[f"{key}.{sub}"],
                    )
    return {"ok": True}


def _stamp_path(root, kind):
    root = Path(root)
    if kind == "engine_root":
        return root / _VERSION_FILENAME
    return root / ".rocket" / _VERSION_FILENAME


def _read_folder_version(stamp):
    try:
        text = stamp.read_text()
    except FileNotFoundError:
        raise LayoutError(
            "missing_entry", f"Missing required entry: {stamp}."
        ) from None
    if text.strip() == "":
        raise LayoutError(
            "empty_entry", f"Required entry is empty: {stamp}."
        )
    try:
        data = _yaml().load(text)
    except Exception as exc:
        raise LayoutError(
            "invalid_version", f"Bad version stamp {stamp}: {exc}."
        ) from exc
    version = data.get("schema_version") if isinstance(data, dict) else None
    if not isinstance(version, int) or isinstance(version, bool):
        raise LayoutError(
            "invalid_version",
            f"Bad version stamp {stamp}: need schema_version int.",
        )
    return version


def _check_file(target, entry):
    if target.is_dir():
        raise LayoutError(
            "type_mismatch", f"Entry must be a file, found dir: {target}."
        )
    if target.stat().st_size == 0:
        raise LayoutError("empty_entry", f"Required entry is empty: {target}.")
    if entry.get("format") == "policy":
        data = _load_yaml_file(target)
        if data is None:
            raise LayoutError(
                "empty_entry", f"Required entry is empty: {target}."
            )
        try:
            validate_policy(data)
        except LayoutError as exc:
            raise LayoutError(
                exc.code, f"{exc} ({target})", fields=exc.fields
            ) from None


def _check_entries(base, entries):
    for entry in entries:
        if entry["match"] == "exact":
            target = Path(base) / entry["name"]
            if not target.exists():
                if entry["required"]:
                    raise LayoutError(
                        "missing_entry", f"Missing required entry: {target}."
                    )
                continue
            if entry["type"] == "dir":
                if not target.is_dir():
                    raise LayoutError(
                        "type_mismatch",
                        f"Entry must be a dir, found file: {target}.",
                    )
                _check_entries(target, entry.get("children", []) or [])
            else:
                _check_file(target, entry)
        else:
            regex = re.compile(entry["pattern"])
            names = []
            if Path(base).is_dir():
                names = sorted(
                    p.name for p in Path(base).iterdir() if regex.match(p.name)
                )
            if entry["required"] and not names:
                raise LayoutError(
                    "missing_entry",
                    f"Missing required entry matching {entry['pattern']}: {base}.",
                )
            for name in names:
                target = Path(base) / name
                if entry["type"] == "dir":
                    if not target.is_dir():
                        raise LayoutError(
                            "type_mismatch",
                            f"Entry must be a dir, found file: {target}.",
                        )
                    _check_entries(target, entry.get("children", []) or [])
                else:
                    _check_file(target, entry)


def validate_tree(root, kind="engine_root", schema=None):
    """Check a tree against the schema; refuse newer stamps first."""
    if kind not in ("engine_root", "linked_project"):
        raise LayoutError("invalid_kind", f"Unknown tree kind: {kind}.")
    data = schema if schema is not None else load_schema()
    base = Path(root)
    if not base.is_dir():
        raise LayoutError(
            "missing_entry", f"Root not found or not a dir: {root}."
        )
    stamp = _stamp_path(base, kind)
    folder_version = _read_folder_version(stamp)
    if folder_version > SCHEMA_VERSION:
        raise LayoutError(
            "unsupported_version",
            f"Folder schema version {folder_version} is newer than "
            f"supported {SCHEMA_VERSION}; upgrade the engine, refusing "
            f"to misread {stamp}.",
        )
    _check_entries(base, data[kind])
    return {
        "ok": True,
        "kind": kind,
        "schema_version": SCHEMA_VERSION,
        "folder_version": folder_version,
    }


def _gitignore_patterns(entries, prefix=""):
    patterns = []
    for entry in entries:
        segment = "*" if entry["match"] == "pattern" else entry["name"]
        path = f"{prefix}{segment}"
        if not entry["tracked"]:
            patterns.append(f"{path}/" if entry["type"] == "dir" else path)
            continue
        if entry["type"] == "dir":
            patterns.extend(
                _gitignore_patterns(entry.get("children", []) or [], f"{path}/")
            )
    return patterns


def derive_gitignore(kind=None, schema=None):
    """Derive canonical gitignore lines from tracked=False entries."""
    data = schema if schema is not None else load_schema()
    if kind is not None and kind not in ("engine_root", "linked_project"):
        raise LayoutError("invalid_kind", f"Unknown tree kind: {kind}.")
    sections = [kind] if kind is not None else ["engine_root", "linked_project"]
    patterns = []
    for section in sections:
        patterns.extend(_gitignore_patterns(data[section]))
    lines = [_GITIGNORE_HEADER, *sorted(set(patterns))]
    return "\n".join(lines) + "\n"


def verify_gitignore(text, kind=None, schema=None):
    """Verify a gitignore covers every derived pattern (extras allowed)."""
    expected = derive_gitignore(kind=kind, schema=schema)
    want = [line for line in expected.splitlines() if line and not line.startswith("#")]
    have = {
        line.strip()
        for line in (text or "").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    missing = [line for line in want if line not in have]
    if missing:
        raise LayoutError(
            "gitignore_mismatch",
            f"Gitignore misses derived patterns: {', '.join(missing)}.",
        )
    return {"ok": True}
