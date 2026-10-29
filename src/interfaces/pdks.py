"""PDK store: local-dir adoption into pdks/ + manifest + verify (PDK-STORE).

The engine owns its root; callers own their files. `register_pdk`
adopts a caller-owned directory into the sole shared store
`pdks/<id>/<revision>/` (copy + manifest + verify). Entries are
immutable once verified: re-register re-verifies instead of
duplicating. Every store path goes through PATH-GUARD containment
(`join_contained`) and slug helpers; every op validates the store
layout via LAYOUT-SCHEMA (`validate_tree`). Runs pin the I28
ingredient closure (id + revision + manifest hash) via
`pdk_ingredient`. MVP scope: local-dir adoption only.

Identity (PDK-DISPLAY): slug on disk, canonical display id in
records. The store directory and manifest `id` stay the lookup slug
(`sky130A` → `sky130a`); the manifest `display_id` records the
canonical id as passed at registration, and `register_pdk` /
`verify_pdk` / `list_pdks` / `pdk_ingredient` plus drift/conflict
messages report it. Lookup stays slug-based (either spelling
resolves); pre-display manifests without `display_id` load with the
slug as fallback. `display_id` is fixed at first registration:
re-register never rewrites the manifest.
"""

import hashlib
import io
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from ruamel.yaml import YAML

from .errors import ContractError
from .layout import SCHEMA_VERSION, template_defaults, validate_tree
from .paths import join_contained, slugify, to_unix

MANIFEST_VERSION = 1
_MANIFEST_FILENAME = "manifest.yaml"
_REVISION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

_HASH_CHUNK_BYTES = 1024 * 1024


class PdkError(ContractError):
    """PDK-store violation with a stable machine code."""


def resolve_engine_root(explicit=None):
    """Resolve ENGINE_ROOT: explicit arg -> $ROCKETEDA_HOME -> XDG default."""
    if explicit is not None:
        return Path(explicit)
    env_home = os.environ.get("ROCKETEDA_HOME")
    if env_home:
        return Path(env_home)
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        return Path(xdg_data) / "rocketeda"
    return Path.home() / ".local" / "share" / "rocketeda"


def _dump_yaml(data):
    buf = io.StringIO()
    YAML(typ="safe").dump(data, buf)
    return buf.getvalue()


def ensure_engine_root(root=None):
    """Create a missing engine-root skeleton, then validate it. Idempotent."""
    resolved = resolve_engine_root(root)
    resolved.mkdir(parents=True, exist_ok=True)
    stamp = resolved / "layout.version"
    if not stamp.exists():
        stamp.write_text(_dump_yaml({"schema_version": SCHEMA_VERSION}))
    policy = resolved / "policy.yaml"
    if not policy.exists():
        policy.write_text(_dump_yaml(template_defaults()))
    for dirname in ("pdks", "cache", "projects"):
        (resolved / dirname).mkdir(parents=True, exist_ok=True)
    validate_tree(resolved, kind="engine_root")
    return resolved


def _check_revision(revision):
    if not isinstance(revision, str) or _REVISION_RE.match(revision) is None:
        raise PdkError("invalid_pdk", f"Bad PDK revision: {revision!r}.")
    return revision


def _pdk_dir(engine_root, pdk_id, revision):
    slug = slugify(pdk_id)
    _check_revision(revision)
    return join_contained(engine_root, "pdks", slug, revision)


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _scan_tree(root):
    """Hash every regular file; record symlink targets. No following."""
    root = Path(root)
    files = {}
    symlinks = {}
    stack = [root]
    while stack:
        current = stack.pop()
        with os.scandir(current) as iterator:
            for entry in iterator:
                rel = to_unix(str(Path(entry.path).relative_to(root)))
                if rel == _MANIFEST_FILENAME:
                    continue
                if entry.is_symlink():
                    symlinks[rel] = os.readlink(entry.path)
                elif entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    files[rel] = _sha256_file(entry.path)
                else:
                    raise PdkError(
                        "invalid_pdk",
                        f"Unsupported file type in PDK tree: {rel}.",
                    )
    return files, symlinks


def _tree_hash(files, symlinks):
    lines = [f"file {rel} {files[rel]}" for rel in files]
    lines += [f"link {rel} {symlinks[rel]}" for rel in symlinks]
    canonical = "".join(f"{line}\n" for line in sorted(lines))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_manifest(path):
    try:
        data = YAML(typ="safe").load(Path(path).read_text())
    except Exception as exc:
        raise PdkError(
            "invalid_pdk", f"Cannot parse PDK manifest {path}: {exc}."
        ) from exc
    if not isinstance(data, dict):
        raise PdkError(
            "invalid_pdk", f"PDK manifest must be a mapping: {path}."
        )
    for field in ("manifest_version", "id", "revision", "files", "tree_hash"):
        if field not in data:
            raise PdkError(
                "invalid_pdk", f"PDK manifest misses field {field}: {path}."
            )
    if data["manifest_version"] != MANIFEST_VERSION:
        raise PdkError(
            "invalid_pdk",
            f"PDK manifest version {data['manifest_version']} is newer than "
            f"supported {MANIFEST_VERSION}; refusing to misread {path}.",
        )
    return data


def _display_of(manifest):
    """Canonical display id; pre-display manifests fall back to the slug."""
    return manifest.get("display_id") or manifest["id"]


def _manifest_record(slug, display_id, revision, dest, source, files, symlinks):
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "id": slug,
        "display_id": display_id,
        "revision": revision,
        "source": str(source),
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "symlink_count": len(symlinks),
        "tree_hash": _tree_hash(files, symlinks),
        "files": {rel: files[rel] for rel in sorted(files)},
        "symlinks": {rel: symlinks[rel] for rel in sorted(symlinks)},
    }
    manifest_path = dest / _MANIFEST_FILENAME
    manifest_path.write_text(_dump_yaml(manifest))
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return manifest, manifest_hash


def _drift(pdk_id, revision, rel, detail):
    raise PdkError(
        "pdk_drift",
        f"PDK drift in {pdk_id}@{revision}: {rel} {detail}.",
    )


def _verify_against(dest, manifest):
    pdk_id = _display_of(manifest)
    revision = manifest["revision"]
    files, symlinks = _scan_tree(dest)
    want_files = manifest.get("files") or {}
    want_links = manifest.get("symlinks") or {}
    for rel in sorted(set(files) | set(want_files)):
        if rel not in want_files:
            _drift(pdk_id, revision, rel, "is extra on disk (not in manifest)")
        if rel not in files:
            _drift(pdk_id, revision, rel, "is missing on disk")
        if files[rel] != want_files[rel]:
            _drift(pdk_id, revision, rel, "hash mismatch")
    for rel in sorted(set(symlinks) | set(want_links)):
        if rel not in want_links:
            _drift(pdk_id, revision, rel, "is an extra symlink on disk")
        if rel not in symlinks:
            _drift(pdk_id, revision, rel, "symlink is missing on disk")
        if symlinks[rel] != want_links[rel]:
            _drift(pdk_id, revision, rel, "symlink target changed")
    if _tree_hash(files, symlinks) != manifest["tree_hash"]:
        raise PdkError(
            "pdk_drift",
            f"PDK drift in {pdk_id}@{revision}: tree hash mismatch.",
        )
    return files, symlinks


def register_pdk(source_dir, pdk_id, revision, engine_root=None):
    """Adopt a local dir into pdks/ (copy + manifest + verify).

    Re-register re-verifies the existing entry instead of duplicating.
    """
    root = ensure_engine_root(engine_root)
    source = Path(source_dir)
    if not source.is_dir():
        raise PdkError(
            "invalid_pdk", f"PDK source must be a directory: {source_dir}."
        )
    source_resolved = source.resolve()
    slug = slugify(pdk_id)
    _check_revision(revision)
    dest = join_contained(root, "pdks", slug, revision)
    if dest == source_resolved or source_resolved in dest.parents:
        raise PdkError(
            "invalid_pdk",
            f"PDK source must be outside its store entry: {source_dir}.",
        )
    if dest in source_resolved.parents:
        raise PdkError(
            "invalid_pdk",
            f"PDK store entry must be outside its source: {source_dir}.",
        )
    manifest_path = dest / _MANIFEST_FILENAME
    if dest.exists():
        if not manifest_path.is_file():
            raise PdkError(
                "invalid_pdk",
                f"PDK entry without manifest (remove and retry): {dest}.",
            )
        manifest = _load_manifest(manifest_path)
        if manifest.get("source") != str(source_resolved):
            raise PdkError(
                "pdk_conflict",
                f"PDK {_display_of(manifest)}@{revision} is already registered "
                f"from {manifest.get('source')}, not {source_resolved}.",
            )
        _verify_against(dest, manifest)
        manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        return {
            "id": _display_of(manifest),
            "revision": revision,
            "path": str(dest),
            "manifest_hash": manifest_hash,
            "tree_hash": manifest["tree_hash"],
            "file_count": manifest.get("file_count", len(manifest["files"])),
            "verified": True,
            "reverified": True,
        }
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_resolved, dest, symlinks=True, copy_function=shutil.copy2)
    files, symlinks = _scan_tree(dest)
    manifest, manifest_hash = _manifest_record(
        slug, pdk_id, revision, dest, source_resolved, files, symlinks
    )
    _verify_against(dest, manifest)
    return {
        "id": pdk_id,
        "revision": revision,
        "path": str(dest),
        "manifest_hash": manifest_hash,
        "tree_hash": manifest["tree_hash"],
        "file_count": len(files),
        "verified": True,
        "reverified": False,
    }


def verify_pdk(pdk_id, revision, engine_root=None):
    """Re-hash a registered PDK; drift fails loudly naming the file."""
    root = resolve_engine_root(engine_root)
    validate_tree(root, kind="engine_root")
    slug = slugify(pdk_id)
    _check_revision(revision)
    dest = _pdk_dir(root, slug, revision)
    manifest_path = dest / _MANIFEST_FILENAME
    if not dest.is_dir() or not manifest_path.is_file():
        raise PdkError(
            "unknown_pdk", f"Unknown PDK: {pdk_id}@{revision} (no store entry)."
        )
    manifest = _load_manifest(manifest_path)
    _verify_against(dest, manifest)
    return {
        "ok": True,
        "id": _display_of(manifest),
        "revision": revision,
        "path": str(dest),
        "manifest_hash": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "tree_hash": manifest["tree_hash"],
        "file_count": manifest.get("file_count", len(manifest["files"])),
    }


def list_pdks(engine_root=None):
    """List registered PDKs in canonical (id, revision) order."""
    root = resolve_engine_root(engine_root)
    validate_tree(root, kind="engine_root")
    pdks_root = join_contained(root, "pdks")
    entries = []
    if not pdks_root.is_dir():
        return entries
    for id_dir in sorted(pdks_root.iterdir(), key=lambda p: p.name):
        if id_dir.name.startswith(".") or not id_dir.is_dir():
            continue
        for rev_dir in sorted(id_dir.iterdir(), key=lambda p: p.name):
            if rev_dir.name.startswith(".") or not rev_dir.is_dir():
                continue
            manifest_path = rev_dir / _MANIFEST_FILENAME
            if not manifest_path.is_file():
                raise PdkError(
                    "invalid_pdk",
                    f"PDK entry without manifest (remove and retry): {rev_dir}.",
                )
            manifest = _load_manifest(manifest_path)
            entries.append({
                "id": _display_of(manifest),
                "revision": manifest["revision"],
                "path": str(rev_dir.resolve()),
                "manifest_hash": hashlib.sha256(
                    manifest_path.read_bytes()
                ).hexdigest(),
                "tree_hash": manifest["tree_hash"],
                "file_count": manifest.get("file_count", len(manifest["files"])),
                "registered_at": manifest.get("registered_at"),
            })
    return sorted(entries, key=lambda e: (e["id"], e["revision"]))


def resolve_deck(pdk_id, revision, deck, engine_root=None):
    """Resolve a deck relpath to its manifest-hashed store path.

    The file's current hash must match the manifest; drift, unknown
    decks, and unknown id/rev all raise (never silent substitute).
    """
    root = resolve_engine_root(engine_root)
    validate_tree(root, kind="engine_root")
    slug = slugify(pdk_id)
    _check_revision(revision)
    dest = _pdk_dir(root, slug, revision)
    manifest_path = dest / _MANIFEST_FILENAME
    if not dest.is_dir() or not manifest_path.is_file():
        raise PdkError(
            "unknown_pdk",
            f"Unknown PDK: {pdk_id}@{revision} (no store entry).",
        )
    manifest = _load_manifest(manifest_path)
    display = _display_of(manifest)
    # Containment first (resolved), then manifest lookup on the LEXICAL
    # rel: resolving before lookup would make every symlink deck
    # misdiagnose as its target and let swapped link targets pass.
    target = join_contained(dest, deck)
    lexical = Path(dest, to_unix(deck))
    rel = to_unix(str(lexical.relative_to(dest)))
    want_files = manifest.get("files") or {}
    want_links = manifest.get("symlinks") or {}
    if rel in want_links:
        if not lexical.is_symlink() or os.readlink(lexical) != want_links[rel]:
            _drift(display, revision, rel, "symlink target changed")
        try:
            digest = _sha256_file(target)
        except OSError:
            _drift(display, revision, rel, "symlink target missing on disk")
        return {"path": str(lexical), "sha256": digest}
    if rel not in want_files:
        raise PdkError(
            "unknown_pdk",
            f"Unknown deck for {display}@{revision}: {rel} (not in manifest).",
        )
    if lexical.is_symlink():
        _drift(display, revision, rel, "changed from file to symlink")
    if not target.is_file():
        _drift(display, revision, rel, "is missing on disk")
    current_hash = _sha256_file(target)
    if current_hash != want_files[rel]:
        _drift(display, revision, rel, "hash mismatch")
    return {"path": str(target), "sha256": current_hash}


def pdk_ingredient(pdk_id, revision, engine_root=None):
    """Return the I28 PDK ingredient closure for run records.

    Verifies freshness first: a drifted store fails loudly instead
    of recording a stale hash.
    """
    result = verify_pdk(pdk_id, revision, engine_root=engine_root)
    return {
        "pdk_id": result["id"],
        "pdk_revision": result["revision"],
        "pdk_manifest_hash": result["manifest_hash"],
    }
