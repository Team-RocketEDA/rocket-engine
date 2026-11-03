"""PATH-GUARD RED — path safety module (evil inputs first).

Tests assume `rocket_engine.interfaces.paths` with:
  PathError, to_unix, join_contained,
  is_slug, slugify, mint_slug, SlugStore.
Valid RED = the import itself fails: the surface does not exist yet.

Policy under test (docs/tickets/PATH-GUARD.md):
  minted-strict (slugs: strict charset, never spaces),
  encountered-robust (spaces survive, never minted, never rejected).
"""

import re

import pytest

STRICT_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def test_to_unix_folds_backslashes():
    from rocket_engine.interfaces.paths import to_unix  # RED: missing surface

    assert to_unix("sub\\dir\\file.txt") == "sub/dir/file.txt"
    assert to_unix("C:\\proj\\file.txt") == "C:/proj/file.txt"
    assert to_unix("already/unix") == "already/unix"


def test_to_unix_preserves_spaces():
    from rocket_engine.interfaces.paths import to_unix  # RED: missing surface

    assert to_unix("my dir\\my file.txt") == "my dir/my file.txt"
    assert to_unix(" spaced / name ") == " spaced / name "


def test_spaced_paths_work_contained(tmp_path):
    from rocket_engine.interfaces.paths import join_contained  # RED: missing surface

    target = tmp_path / "my dir" / "my file.txt"
    target.parent.mkdir(parents=True)
    target.write_text("spaced bytes\n")
    resolved = join_contained(tmp_path, "my dir/my file.txt")
    assert resolved.read_text() == "spaced bytes\n"


def test_backslash_join_normalized(tmp_path):
    from rocket_engine.interfaces.paths import join_contained  # RED: missing surface

    target = tmp_path / "sub" / "file.txt"
    target.parent.mkdir(parents=True)
    target.write_text("x\n")
    assert join_contained(tmp_path, "sub\\file.txt") == join_contained(
        tmp_path, "sub/file.txt"
    )


def test_dotdot_rejected(tmp_path):
    from rocket_engine.interfaces.paths import join_contained  # RED: missing surface

    for evil in ("../escape", "a/../..", "a/../../b", "..", "a/..", "a/b/../../../etc"):
        with pytest.raises(Exception) as excinfo:
            join_contained(tmp_path, evil)
        assert _code(excinfo) == "path_escape"


def test_absolute_paths_rejected(tmp_path):
    from rocket_engine.interfaces.paths import join_contained  # RED: missing surface

    for evil in ("/etc/passwd", "/tmp/x", "C:/Windows", "C:\\Windows"):
        with pytest.raises(Exception) as excinfo:
            join_contained(tmp_path, evil)
        assert _code(excinfo) == "path_escape"


def test_symlink_escape_rejected(tmp_path):
    from rocket_engine.interfaces.paths import join_contained  # RED: missing surface

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret\n")
    root = tmp_path / "root"
    root.mkdir()
    (root / "evil-link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(Exception) as excinfo:
        join_contained(root, "evil-link/secret.txt")
    assert _code(excinfo) == "path_escape"
    with pytest.raises(Exception) as excinfo:
        join_contained(root, "evil-link")
    assert _code(excinfo) == "path_escape"


def test_contained_symlink_allowed(tmp_path):
    from rocket_engine.interfaces.paths import join_contained  # RED: missing surface

    root = tmp_path / "root"
    (root / "real").mkdir(parents=True)
    (root / "real" / "ok.txt").write_text("ok\n")
    (root / "alias").symlink_to(root / "real", target_is_directory=True)
    resolved = join_contained(root, "alias/ok.txt")
    assert resolved.read_text() == "ok\n"


def test_slug_strict_charset():
    from rocket_engine.interfaces.paths import SlugStore, is_slug  # RED: missing surface

    store = SlugStore()
    for display in ("Hello World!", "ADC", "my design v2", "sky130A LVS"):
        slug = store.mint(display)
        assert " " not in slug
        assert slug == slug.lower()
        assert STRICT_SLUG_RE.match(slug), slug
        assert is_slug(slug) is True
    assert is_slug("has space") is False
    assert is_slug("UPPER") is False
    assert is_slug("") is False


def test_slugify_spaces_never_minted_never_rejected():
    from rocket_engine.interfaces.paths import slugify  # RED: missing surface

    assert slugify("my design") == "my-design"
    assert slugify("  spaced  out  ") == "spaced-out"
    assert " " not in slugify("a b c")


def test_append_only_dedup_sequence():
    from rocket_engine.interfaces.paths import SlugStore  # RED: missing surface

    store = SlugStore()
    assert store.mint("adc") == "adc"
    assert store.mint("adc") == "adc-1"
    # User digits are data: adc-2 is free, mint it verbatim.
    assert store.mint("adc-2") == "adc-2"
    # Next adc fills the gap with adc-3 (adc, adc-1, adc-2 taken).
    assert store.mint("adc") == "adc-3"


def test_append_only_never_reinterprets_digits():
    from rocket_engine.interfaces.paths import mint_slug  # RED: missing surface

    # Gap fill, not max+1: adc-1 is free even though adc-2 is taken.
    assert mint_slug("adc", {"adc", "adc-2"}) == "adc-1"
    # Taken adc-2 dedups by appending, never by bumping to adc-3.
    assert mint_slug("adc-2", {"adc-2"}) == "adc-2-1"
    assert mint_slug("adc-2", {"adc-2", "adc-2-1"}) == "adc-2-2"


def test_evil_dedup_cases_all_distinct_and_stable():
    from rocket_engine.interfaces.paths import SlugStore  # RED: missing surface

    store = SlugStore()
    slugs = [
        store.mint("adc"),
        store.mint("adc"),
        store.mint("adc-2"),
        store.mint("adc (1)"),
    ]
    assert len(set(slugs)) == 4
    assert slugs[0] == "adc"
    assert slugs[1] == "adc-1"
    assert slugs[2] == "adc-2"
    # Literal "adc (1)" slugifies onto the adc-1 base; it must dedup
    # append-only instead of colliding.
    assert slugs[3] not in slugs[:3]
    assert slugs[3].startswith("adc-1")
    # Stable: lookup renders the stored display verbatim.
    assert store.display_for(slugs[3]) == "adc (1)"
    assert store.display_for("adc") == "adc"
    assert store.display_for("adc-2") == "adc-2"


def test_render_by_lookup():
    from rocket_engine.interfaces.paths import SlugStore  # RED: missing surface

    store = SlugStore()
    slug = store.mint("My Fancy ADC!")
    assert store.display_for(slug) == "My Fancy ADC!"
    assert ("My Fancy ADC!", slug) in store.pairs()
    with pytest.raises(Exception) as excinfo:
        store.display_for("no-such-slug")
    assert _code(excinfo) == "unknown_slug"


def test_slugify_empty_raises():
    from rocket_engine.interfaces.paths import slugify  # RED: missing surface

    for bad in ("", "   ", "!!!", "---"):
        with pytest.raises(Exception) as excinfo:
            slugify(bad)
        assert _code(excinfo) == "invalid_slug"


def test_join_contained_dot_segments_allowed(tmp_path):
    from rocket_engine.interfaces.paths import join_contained  # RED: missing surface

    target = tmp_path / "sub" / "file.txt"
    target.parent.mkdir(parents=True)
    target.write_text("x\n")
    resolved = join_contained(tmp_path, "sub/./file.txt")
    assert resolved == join_contained(tmp_path, "sub/file.txt")
