"""Path safety: unix normalization, containment, slug minting (PATH-GUARD).

Policy: minted-strict, encountered-robust. Names the engine mints
(slugs) use a strict lowercase charset and never contain spaces;
paths the engine meets keep their spaces and are never rejected
for them. All joins are root-join only: relative parts under a
root, `..` rejected outright, absolute inputs rejected, and the
resolved candidate must stay inside the resolved root (symlink
escapes fail closed). Dedup is append-only: a taken base gains
`-1`, `-2`, … without ever reinterpreting trailing digits.
"""

import re
from pathlib import Path

from .errors import ContractError

SLUG_PATTERN = r"^[a-z0-9][a-z0-9_.-]*$"
_SLUG_RE = re.compile(SLUG_PATTERN)
_NON_SLUG_RUN_RE = re.compile(r"[^a-z0-9_.-]+")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


class PathError(ContractError):
    """Path-safety violation with a stable machine code."""


def to_unix(value):
    """Fold backslashes to forward slashes; spaces survive verbatim."""
    if isinstance(value, Path):
        value = str(value)
    if not isinstance(value, str):
        raise PathError("invalid_path", f"Path must be text, got {type(value).__name__}.")
    return value.replace("\\", "/")


def is_slug(value):
    """True when value matches the minted-strict slug charset."""
    return isinstance(value, str) and _SLUG_RE.match(value) is not None


def slugify(display_name):
    """Map a display name onto the strict slug charset (never rejects spaces)."""
    if not isinstance(display_name, str):
        raise PathError(
            "invalid_slug", f"Display name must be text, got {type(display_name).__name__}."
        )
    slug = _NON_SLUG_RUN_RE.sub("-", display_name.lower()).strip("-_.")
    if not slug or _SLUG_RE.match(slug) is None:
        raise PathError("invalid_slug", f"Display name mints no slug: {display_name!r}.")
    return slug


def mint_slug(display_name, taken):
    """Mint a slug with append-only dedup (`adc-2` -> `adc-2-1`)."""
    base = slugify(display_name)
    if base not in taken:
        return base
    index = 1
    while f"{base}-{index}" in taken:
        index += 1
    return f"{base}-{index}"


class SlugStore:
    """Stored (display_name, slug) pairs; render displays by lookup."""

    def __init__(self):
        self._by_slug = {}
        self._pairs = []

    def mint(self, display_name):
        slug = mint_slug(display_name, self._by_slug)
        self._by_slug[slug] = display_name
        self._pairs.append((display_name, slug))
        return slug

    def display_for(self, slug):
        try:
            return self._by_slug[slug]
        except KeyError:
            raise PathError("unknown_slug", f"Unknown slug: {slug}.") from None

    def pairs(self):
        return list(self._pairs)

    def __contains__(self, slug):
        return slug in self._by_slug

    def __len__(self):
        return len(self._pairs)


def _check_part(part):
    text = to_unix(part)
    if text == "":
        return None
    if text.startswith("/") or _DRIVE_RE.match(text):
        raise PathError("path_escape", f"Absolute path rejected under root-join: {part!r}.")
    for segment in text.split("/"):
        if segment == "..":
            raise PathError("path_escape", f"'..' rejected under root-join: {part!r}.")
    return text


def join_contained(root, *parts):
    """Join relative parts under root; resolve and enforce containment.

    Backslashes are folded, spaces survive, `.` segments pass through,
    and the resolved candidate must stay inside the resolved root.
    """
    if isinstance(root, Path):
        root_text = str(root)
    elif isinstance(root, str):
        root_text = root
    else:
        raise PathError("invalid_path", f"Root must be text, got {type(root).__name__}.")
    cleaned = []
    for part in parts:
        text = _check_part(part)
        if text is not None:
            cleaned.append(text)
    try:
        root_resolved = Path(root_text).resolve()
        candidate_resolved = Path(root_text, *cleaned).resolve()
    except PathError:
        raise
    except Exception as exc:
        raise PathError("path_escape", f"Cannot resolve under root: {exc}.") from exc
    try:
        candidate_resolved.relative_to(root_resolved)
    except ValueError:
        raise PathError(
            "path_escape", f"Path escapes root: {candidate_resolved}."
        ) from None
    return candidate_resolved
