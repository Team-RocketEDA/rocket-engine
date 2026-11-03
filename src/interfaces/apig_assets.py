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

PRD aliases: the PRD names `list_pdk_assets`/`get_pdk_asset` are
thin wrappers over `list_assets`/`serve_asset` with identical
payloads — the wire always carries the PDK's own identifiers, and
humans and agents may query by either spelling. The canonical
functions stay the transport names until the adapt lane catalogs
the aliases in the vocabulary and composition wiring (see
`PRD_ALIASES`); this module pins the alias behavior meanwhile.

Serving guards (MC-43): single-asset serves refuse over
`max_bytes` with `too_large` instead of encoding unbounded bulk,
and bulk listings page with `limit`/`cursor` following the v1
Page convention (`next_cursor`, `has_more`-style termination via
a null cursor).
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

#: Largest single asset `serve_asset` will encode; larger files
#: refuse with `too_large` so a blind read never swallows bulk.
MAX_SERVE_BYTES = 4 * 1024 * 1024

#: Largest single `list_assets` page; larger limits refuse loudly.
MAX_LIST_LIMIT = 1000

#: PRD-name alias -> canonical transport name. The adapt lane
#: catalogs these in the vocabulary and composition wiring; until
#: then transports serve the canonical names and this table pins
#: the alias contract at the module layer.
PRD_ALIASES = {
    "list_pdk_assets": "list_assets",
    "get_pdk_asset": "serve_asset",
}

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


def _check_max_bytes(max_bytes):
    if max_bytes is None:
        return None
    if (
        isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or max_bytes <= 0
    ):
        raise ContractError(
            "invalid_command",
            f"max_bytes must be a positive int, got {max_bytes!r}.",
        )
    return max_bytes


def serve_asset(pdk_id, revision, path, engine_root=None,
                max_bytes=MAX_SERVE_BYTES):
    """Serve one PDK file's bytes verbatim with hash-checked identity.

    Args:
        pdk_id: PDK id (either display spelling resolves).
        revision: PDK revision pin.
        path: Store-relative file path (single `.sym` as-is, any
            depth).
        engine_root: Explicit store root; resolved when omitted.
        max_bytes: Largest encodable size; larger files refuse
            with too_large instead of encoding bulk. None opts
            out (bulk reads belong to selective calls, never a
            blind loop).

    Returns:
        Mapping with asset_version, pdk_id, display_id, revision,
            canonical path, size, sha256 over the raw bytes, and
            the verbatim bytes base64-encoded for JSON channels.

    Raises:
        ContractError: invalid_reference for an unknown PDK, a
            missing file, a directory path, or an escaping path;
            invalid_command for a malformed max_bytes; too_large
            when the file exceeds max_bytes.
    """
    cap = _check_max_bytes(max_bytes)
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
    size = target.stat().st_size
    if cap is not None and size > cap:
        raise ContractError(
            "too_large",
            f"Asset {canonical!r} is {size} bytes, over "
            f"max_bytes={cap}; narrow with list_assets prefix "
            "filtering and serve selectively, never in a blind loop.",
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


def get_pdk_asset(pdk_id, revision, path, engine_root=None,
                  max_bytes=MAX_SERVE_BYTES):
    """Serve one PDK file verbatim under its PRD name.

    Alias for `serve_asset`: identical arguments, identical
    payload — the wire always carries the PDK's own identifiers.

    Args:
        pdk_id: PDK id (either display spelling resolves).
        revision: PDK revision pin.
        path: Store-relative file path.
        engine_root: Explicit store root; resolved when omitted.
        max_bytes: Largest encodable size; None opts out.

    Returns:
        Serve mapping, exactly as `serve_asset` returns.

    Raises:
        ContractError: Whatever `serve_asset` raises.
    """
    return serve_asset(
        pdk_id, revision, path, engine_root=engine_root,
        max_bytes=max_bytes,
    )


def _check_limit(limit):
    if limit is None:
        return None
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= MAX_LIST_LIMIT
    ):
        raise ContractError(
            "invalid_command",
            f"limit must be an int 1..{MAX_LIST_LIMIT}, "
            f"got {limit!r}.",
        )
    return limit


def _check_cursor(cursor, total):
    if cursor is None:
        return 0
    if not isinstance(cursor, str) or not cursor.isdigit():
        raise ContractError(
            "invalid_command",
            f"cursor must be an opaque page token from a prior "
            f"listing, got {cursor!r}.",
        )
    start = int(cursor)
    if start > total:
        raise ContractError(
            "invalid_command",
            f"Unknown cursor {cursor!r} for {total} files.",
        )
    return start


def list_assets(pdk_id, revision, prefix=None, engine_root=None,
                limit=None, cursor=None):
    """List PDK file metadata with per-file hash identity.

    Args:
        pdk_id: PDK id (either display spelling resolves).
        revision: PDK revision pin.
        prefix: Optional store-relative prefix filter; everything
            when omitted.
        engine_root: Explicit store root; resolved when omitted.
        limit: Maximum file entries in this page; the whole
            filtered set when omitted.
        cursor: Opaque page token from a prior listing; the
            first page when omitted.

    Returns:
        Mapping with asset_version, pdk_id, display_id, revision,
            sorted file entries for this page (path, size,
            sha256), symlink entries (path, resolves, unpaged),
            the total file count, and the paging echo (limit,
            cursor, next_cursor; next_cursor is None on the last
            page, following the v1 Page convention).

    Raises:
        ContractError: invalid_reference for an unknown PDK or an
            escaping prefix; invalid_command for a malformed
            limit or cursor.
    """
    page_limit = _check_limit(limit)
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
    start = _check_cursor(cursor, len(files))
    if page_limit is None:
        page = files
        next_cursor = None
    else:
        page = files[start:start + page_limit]
        ahead = start + len(page)
        next_cursor = str(ahead) if ahead < len(files) else None
    return {
        "asset_version": ASSET_VERSION,
        "pdk_id": slugify(pdk_id),
        "display_id": _display_id(pdk_dir, pdk_id),
        "revision": revision,
        "files": page,
        "symlinks": symlinks,
        "count": len(files),
        "limit": page_limit,
        "cursor": cursor,
        "next_cursor": next_cursor,
    }


def list_pdk_assets(pdk_id, revision, prefix=None, engine_root=None,
                    limit=None, cursor=None):
    """List PDK file metadata under its PRD name.

    Alias for `list_assets`: identical arguments, identical
    payload — the wire always carries the PDK's own identifiers.

    Args:
        pdk_id: PDK id (either display spelling resolves).
        revision: PDK revision pin.
        prefix: Optional store-relative prefix filter.
        engine_root: Explicit store root; resolved when omitted.
        limit: Maximum file entries in this page.
        cursor: Opaque page token from a prior listing.

    Returns:
        Listing mapping, exactly as `list_assets` returns.

    Raises:
        ContractError: Whatever `list_assets` raises.
    """
    return list_assets(
        pdk_id, revision, prefix=prefix, engine_root=engine_root,
        limit=limit, cursor=cursor,
    )


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
