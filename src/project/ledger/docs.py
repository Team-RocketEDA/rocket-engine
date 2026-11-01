"""Document path resolution and byte access."""

from ...interfaces.paths import join_contained
from ..errors import ProjectError

from .shared import _RESERVED_DOCS, _SNAPSHOTS_DIRNAME, _atomic_write_text

class _DocMixin:
    """Document byte access for ProjectService."""

    def _doc_path(self, canonical):
        """Resolve one canonical path under the project dir.

        Args:
            canonical: Canonical document path.

        Returns:
            Resolved absolute path inside the project dir.

        Raises:
            ProjectError: path_escape when containment fails.
        """
        try:
            return join_contained(self._dir, canonical)
        except Exception as exc:
            code = getattr(exc, "code", None) or "path_escape"
            raise ProjectError(code, str(exc)) from exc

    def _read_doc_text(self, canonical, original):
        """Read one document as text, or None when missing.

        Args:
            canonical: Canonical document path.
            original: Caller-supplied path for error messages.

        Returns:
            Document text, or None when the document is absent.

        Raises:
            ProjectError: invalid_command when the path names a
                directory; invalid_document when durable bytes are
                not UTF-8 text.
        """
        if self._dir is None:
            return self._docs.get(canonical)
        target = self._doc_path(canonical)
        if not target.exists():
            return None
        if target.is_dir():
            raise ProjectError(
                "invalid_command",
                f"Document path is a directory: {original!r}.",
            )
        try:
            return target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ProjectError(
                "invalid_document",
                f"Document is not UTF-8 text: {original!r} ({exc}).",
            ) from exc
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot read document {original!r}: {exc}.",
            ) from exc

    def _write_doc_text(self, canonical, content, original):
        """Write one document (parents created, atomic rename).

        Args:
            canonical: Canonical document path.
            content: UTF-8 text to store.
            original: Caller-supplied path for error messages.

        Raises:
            ProjectError: invalid_command when the path names a
                directory; invalid_ledger when the durable write
                fails.
        """
        if self._dir is None:
            self._docs[canonical] = content
            return
        target = self._doc_path(canonical)
        if target.is_dir():
            raise ProjectError(
                "invalid_command",
                f"Document path is a directory: {original!r}.",
            )
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot create document dir for {original!r}: {exc}.",
            ) from exc
        try:
            _atomic_write_text(target, content)
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot write document {original!r}: {exc}.",
            ) from exc

    def _delete_doc_path(self, canonical, original):
        """Delete one existing document file.

        Args:
            canonical: Canonical document path.
            original: Caller-supplied path for error messages.

        Raises:
            ProjectError: invalid_command when the path names a
                directory; invalid_ledger when the delete fails.
        """
        if self._dir is None:
            self._docs.pop(canonical, None)
            return
        target = self._doc_path(canonical)
        if target.is_dir():
            raise ProjectError(
                "invalid_command",
                f"Document path is a directory: {original!r}.",
            )
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot delete document {original!r}: {exc}.",
            ) from exc

    def _iter_doc_files(self):
        """Yield (canonical path, byte size) for every document.

        Returns:
            Sorted (path, bytes) pairs, engine-owned entries
            excluded.
        """
        if self._dir is None:
            return sorted(
                (path, len(text.encode("utf-8")))
                for path, text in self._docs.items()
            )
        if not self._dir.is_dir():
            return []
        found = []
        for target in sorted(self._dir.rglob("*")):
            if not target.is_file():
                continue
            try:
                rel = target.relative_to(self._dir).as_posix()
            except ValueError:
                continue
            if (
                rel in _RESERVED_DOCS
                or rel.startswith("runs/")
                or rel.startswith(_SNAPSHOTS_DIRNAME + "/")
            ):
                continue
            try:
                size = target.stat().st_size
            except OSError:
                continue
            found.append((rel, size))
        return sorted(found)
