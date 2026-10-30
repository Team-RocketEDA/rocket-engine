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
    """Path-safety violation with a stable machine code.

    Args:
        code: Stable machine-readable error code.
        message: Human-readable detail.
        fields: Itemized fields, when the error names any.
    """


def to_unix(value):
    """Fold backslashes to forward slashes; spaces survive verbatim.

    Args:
        value: Path text or Path to normalize.

    Returns:
        Unix-normalized path text.

    Raises:
        PathError: invalid_path for non-text input.
    """
    if isinstance(value, Path):
        value = str(value)
    if not isinstance(value, str):
        raise PathError("invalid_path", f"Path must be text, got {type(value).__name__}.")
    return value.replace("\\", "/")


def is_slug(value):
    """True when value matches the minted-strict slug charset.

    Args:
        value: Candidate slug text.

    Returns:
        True when the value is a valid slug.
    """
    return isinstance(value, str) and _SLUG_RE.match(value) is not None


def slugify(display_name):
    """Map a display name onto the strict slug charset.

    Never rejects spaces: runs of non-slug characters fold to one
    dash, lowercased.

    Args:
        display_name: Display text to mint from.

    Returns:
        Minted slug.

    Raises:
        PathError: invalid_slug for non-text input or a name that
            mints no slug.
    """
    if not isinstance(display_name, str):
        raise PathError(
            "invalid_slug", f"Display name must be text, got {type(display_name).__name__}."
        )
    slug = _NON_SLUG_RUN_RE.sub("-", display_name.lower()).strip("-_.")
    if not slug or _SLUG_RE.match(slug) is None:
        raise PathError("invalid_slug", f"Display name mints no slug: {display_name!r}.")
    return slug


def mint_slug(display_name, taken):
    """Mint a slug with append-only dedup (`adc-2` -> `adc-2-1`).

    Args:
        display_name: Display text to mint from.
        taken: Container of already-taken slugs.

    Returns:
        Fresh slug, suffixed when the base is taken.

    Raises:
        PathError: invalid_slug for a name that mints no slug.
    """
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
        """Mint and store a slug for one display name.

        Args:
            display_name: Display text to mint from.

        Returns:
            Fresh slug stored against the display name.

        Raises:
            PathError: invalid_slug for a name that mints no slug.
        """
        slug = mint_slug(display_name, self._by_slug)
        self._by_slug[slug] = display_name
        self._pairs.append((display_name, slug))
        return slug

    def display_for(self, slug):
        """Render the display name stored for one slug.

        Args:
            slug: Slug to look up.

        Returns:
            Stored display name.

        Raises:
            PathError: unknown_slug for an unstored slug.
        """
        try:
            return self._by_slug[slug]
        except KeyError:
            raise PathError("unknown_slug", f"Unknown slug: {slug}.") from None

    def pairs(self):
        """Stored (display_name, slug) pairs in mint order.

        Returns:
            Copy of the stored pair list.
        """
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

    Args:
        root: Root text or Path every part joins under.
        parts: Relative path parts to join.

    Returns:
        Resolved candidate path, contained in the resolved root.

    Raises:
        PathError: invalid_path for a non-text root, path_escape
            for absolute inputs, `..` segments, unresolvable joins,
            or symlink escapes.
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
