"""Raw asset serving (API-GENERALIZE/I29): verbatim PDK bytes, hash-checked.

The engine serves PDK store bytes exactly as they sit on disk — a
single `.sym` as-is, metadata listings, bulk manifests — with no
conversion and no rendering; parsing and styling stay frontend-side.
Every serve carries hash-checked identity (sha256 over the raw bytes),
and every path goes through PATH-GUARD containment, so escapes and
missing files fail loudly instead of leaking neighboring bytes.

Transport note: `serve_asset` base64-encodes the verbatim bytes for
JSON duplex channels; the sha256 is computed over the raw bytes, so
decoding and re-hashing always reproduces the served identity.
"""

import base64
import hashlib

from ruamel.yaml import YAML

try:
    from .errors import ContractError
    from .paths import join_contained, slugify
    from .pdks import resolve_engine_root
except ImportError:  # standalone verification before install
    from rocket_engine.interfaces.errors import ContractError
    from rocket_engine.interfaces.paths import join_contained, slugify
    from rocket_engine.interfaces.pdks import resolve_engine_root

ASSET_VERSION = 1
_HASH_CHUNK_BYTES = 1024 * 1024

_yaml = YAML(typ="safe")


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pdk_dir(engine_root, pdk_id, revision):
    root = resolve_engine_root(engine_root)
    try:
        return join_contained(root, "pdks", slugify(pdk_id), revision)
    except Exception as exc:
        raise ContractError(
            "invalid_reference", f"Unknown PDK: {pdk_id} {revision}."
        ) from exc


def _display_id(pdk_dir, pdk_id):
    manifest = pdk_dir / "manifest.yaml"
    try:
        text = manifest.read_text(encoding="utf-8")
    except OSError:
        return slugify(pdk_id)
    try:
        doc = _yaml.load(text)
    except Exception:
        return slugify(pdk_id)
    if not isinstance(doc, dict):
        return slugify(pdk_id)
    return str(doc.get("display_id") or doc.get("id") or slugify(pdk_id))


def _canon_relpath(relpath):
    if not isinstance(relpath, str):
        raise ContractError(
            "invalid_reference",
            f"Asset path must be text, got {relpath!r}.",
        )
    unix = relpath.replace("\\", "/")
    if unix == "" or unix.startswith("/") or unix.endswith("/"):
        raise ContractError(
            "invalid_reference", f"Bad asset path: {relpath!r}."
        )
    parts = [part for part in unix.split("/") if part not in ("", ".")]
    if not parts or ".." in parts:
        raise ContractError(
            "invalid_reference", f"Asset path escapes: {relpath!r}."
        )
    return "/".join(parts)


def _scan_files(pdk_dir):
    """Sorted (relpath, sha256, size) for regular files; symlinks named."""
    files = []
    symlinks = []
    for target in sorted(pdk_dir.rglob("*")):
        if not target.is_symlink() and not target.is_file():
            continue
        try:
            rel = target.relative_to(pdk_dir).as_posix()
        except ValueError:
            continue
        if target.is_symlink():
            try:
                resolves = target.resolve().is_relative_to(pdk_dir.resolve())
            except OSError:
                resolves = False
            symlinks.append({"path": rel, "resolves": resolves})
            continue
        files.append(
            {"path": rel, "sha256": _sha256_file(target),
             "size": target.stat().st_size}
        )
    files.sort(key=lambda e: e["path"])
    symlinks.sort(key=lambda e: e["path"])
    return files, symlinks


def serve_asset(pdk_id, revision, path, engine_root=None):
    """Serve one PDK file's bytes verbatim with hash-checked identity.

    Args:
        pdk_id: PDK id (either display spelling resolves).
        revision: PDK revision pin.
        path: Store-relative file path (single `.sym` as-is, any
            depth).
        engine_root: Explicit store root; resolved when omitted.

    Returns:
        Mapping with asset_version, pdk_id, display_id, revision,
            canonical path, size, sha256 over the raw bytes, and
            the verbatim bytes base64-encoded for JSON channels.

    Raises:
        ContractError: invalid_reference for an unknown PDK, a
            missing file, a directory path, or an escaping path.
    """
    pdk_dir = _pdk_dir(engine_root, pdk_id, revision)
    if not pdk_dir.is_dir():
        raise ContractError(
            "invalid_reference", f"Unknown PDK: {pdk_id} {revision}."
        )
    canonical = _canon_relpath(path)
    try:
        target = join_contained(pdk_dir, *canonical.split("/"))
    except Exception as exc:
        raise ContractError(
            "invalid_reference", f"Asset path escapes: {path!r}."
        ) from exc
    if not target.is_file() or target.is_symlink():
        # Symlinks resolve through list_assets metadata, never here:
        # serving follows no link the caller cannot see.
        raise ContractError(
            "invalid_reference", f"No such asset: {path!r}."
        )
    raw = target.read_bytes()
    return {
        "asset_version": ASSET_VERSION,
        "pdk_id": slugify(pdk_id),
        "display_id": _display_id(pdk_dir, pdk_id),
        "revision": revision,
        "path": canonical,
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "content_b64": base64.b64encode(raw).decode("ascii"),
    }


def list_assets(pdk_id, revision, prefix=None, engine_root=None):
    """List PDK file metadata with per-file hash identity.

    Args:
        pdk_id: PDK id (either display spelling resolves).
        revision: PDK revision pin.
        prefix: Optional store-relative prefix filter; everything
            when omitted.
        engine_root: Explicit store root; resolved when omitted.

    Returns:
        Mapping with asset_version, pdk_id, display_id, revision,
            sorted file entries (path, size, sha256), symlink
            entries (path, resolves), and the file count.

    Raises:
        ContractError: invalid_reference for an unknown PDK or an
            escaping prefix.
    """
    pdk_dir = _pdk_dir(engine_root, pdk_id, revision)
    if not pdk_dir.is_dir():
        raise ContractError(
            "invalid_reference", f"Unknown PDK: {pdk_id} {revision}."
        )
    want = ""
    if prefix:
        want = _canon_relpath(prefix.rstrip("/") or prefix)
    files, symlinks = _scan_files(pdk_dir)
    if want:
        files = [
            entry for entry in files
            if entry["path"] == want
            or entry["path"].startswith(want + "/")
        ]
        symlinks = [
            entry for entry in symlinks
            if entry["path"] == want
            or entry["path"].startswith(want + "/")
        ]
    return {
        "asset_version": ASSET_VERSION,
        "pdk_id": slugify(pdk_id),
        "display_id": _display_id(pdk_dir, pdk_id),
        "revision": revision,
        "files": files,
        "symlinks": symlinks,
        "count": len(files),
    }


def asset_manifest(pdk_id, revision, prefix=None, engine_root=None):
    """Build a bulk manifest with tree-level hash identity.

    Args:
        pdk_id: PDK id (either display spelling resolves).
        revision: PDK revision pin.
        prefix: Optional store-relative prefix filter; the whole
            tree when omitted.
        engine_root: Explicit store root; resolved when omitted.

    Returns:
        Listing mapping plus tree_sha256 over the sorted
            `sha256:path` lines — one hash pinning the bulk bytes.

    Raises:
        ContractError: invalid_reference for an unknown PDK or an
            escaping prefix.
    """
    listing = list_assets(
        pdk_id, revision, prefix=prefix, engine_root=engine_root
    )
    digest = hashlib.sha256()
    for entry in listing["files"]:
        digest.update(f"{entry['sha256']}:{entry['path']}\n".encode("utf-8"))
    return {**listing, "tree_sha256": digest.hexdigest()}
