"""Durable revisions, persistence, and rewind snapshots."""

import os
import shutil
import uuid
from pathlib import Path

from ...interfaces.paths import join_contained
from ..errors import ProjectError

from .shared import (
    _EVENTS_FILENAME,
    _LEDGER_FILENAME,
    _LINKED_CARVEOUT,
    _SNAPSHOTS_DIRNAME,
    _atomic_write_bytes,
    _atomic_write_text,
    _dump_yaml,
)

class _SnapshotMixin:
    """Durable revisions and snapshots for ProjectService."""

    def _read_ledger_file(self, path):
        """Parse one durable file; missing reads as None, corrupt refuses."""
        try:
            text = Path(path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger", f"Cannot read ledger file {path}: {exc}."
            ) from exc
        try:
            data = self._yaml.load(text)
        except Exception as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot parse ledger file {path}: {exc}.",
            ) from exc
        if data is None:
            raise ProjectError(
                "invalid_ledger", f"Ledger file is empty: {path}."
            )
        return data

    def _load(self):
        """Refresh head + log from durable files (absent files read empty)."""
        ledger = self._read_ledger_file(self._dir / _LEDGER_FILENAME)
        if ledger is not None:
            if not isinstance(ledger, dict):
                raise ProjectError(
                    "invalid_ledger",
                    f"Ledger head must be a mapping: {self._dir}.",
                )
            revision = ledger.get("current_revision")
            requests = ledger.get("requests")
            if not isinstance(revision, str) or not revision:
                raise ProjectError(
                    "invalid_ledger",
                    f"Ledger head carries no revision: {self._dir}.",
                )
            if not isinstance(requests, dict):
                raise ProjectError(
                    "invalid_ledger",
                    f"Ledger head carries no request map: {self._dir}.",
                )
            for request_id, entry in requests.items():
                if (
                    not isinstance(entry, dict)
                    or not isinstance(entry.get("command_text"), str)
                    or not isinstance(entry.get("ack"), dict)
                ):
                    raise ProjectError(
                        "invalid_ledger",
                        f"Ledger request is malformed: {request_id}.",
                    )
            owner = ledger.get("project_id")
            if owner is not None and owner != self._project_id:
                raise ProjectError(
                    "invalid_ledger",
                    f"Ledger belongs to {owner}, not {self._project_id}.",
                )
            self._current_revision = revision
            self._requests = {
                request_id: (entry["command_text"], entry["ack"])
                for request_id, entry in requests.items()
            }
        events = self._read_ledger_file(self._dir / _EVENTS_FILENAME)
        if events is not None:
            if not isinstance(events, list):
                raise ProjectError(
                    "invalid_ledger",
                    f"Event log must be a sequence: {self._dir}.",
                )
            for entry in events:
                if (
                    not isinstance(entry, dict)
                    or not isinstance(entry.get("seq"), int)
                    or isinstance(entry.get("seq"), bool)
                    or not isinstance(entry.get("event"), str)
                ):
                    raise ProjectError(
                        "invalid_ledger",
                        f"Event record is malformed in {self._dir}.",
                    )
            self._events = events
            self._trim()

    def _persist(self):
        """Rewrite both durable files; events first, then the head."""
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            (self._dir / "runs").mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot create ledger dir {self._dir}: {exc}.",
            ) from exc
        try:
            _atomic_write_text(
                self._dir / _EVENTS_FILENAME, _dump_yaml(self._events)
            )
            _atomic_write_text(
                self._dir / _LEDGER_FILENAME,
                _dump_yaml(
                    {
                        "project_id": self._project_id,
                        "current_revision": self._current_revision,
                        "requests": {
                            request_id: {
                                "command_text": command_text,
                                "ack": ack,
                            }
                            for request_id, (command_text, ack)
                            in self._requests.items()
                        },
                    }
                ),
            )
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot persist ledger under {self._dir}: {exc}.",
            ) from exc

    def _refresh_durable(self):
        if self._dir is not None:
            self._load()

    def _persist_after_mutation(self):
        if self._dir is not None:
            self._persist()

    def _snapshot_exists(self, revision):
        """True when a restorable snapshot exists for a revision."""
        if self._dir is None:
            return revision in self._snapshots
        try:
            path = join_contained(
                self._dir, _SNAPSHOTS_DIRNAME, revision
            )
        except Exception:
            return False
        return path.is_dir()

    def _capture_snapshot(self, revision):
        """Store the current managed bytes under one revision id.

        Overwrites any previous capture for that id; empty trees
        leave an empty marker dir so the revision stays restorable.
        The copy lands in a sibling temp dir and renames into
        place, so a crash never leaves a partial snapshot behind.
        """
        if self._dir is None:
            self._snapshots[revision] = dict(self._docs)
            return
        try:
            dest = join_contained(
                self._dir, _SNAPSHOTS_DIRNAME, revision
            )
        except Exception as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot snapshot revision {revision}: {exc}.",
            ) from exc
        base = self._dir / _SNAPSHOTS_DIRNAME
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot snapshot revision {revision}: {exc}.",
            ) from exc
        for stale in base.glob(".cap.*"):
            try:
                if stale.is_symlink() or stale.is_file():
                    stale.unlink()
                elif stale.is_dir():
                    shutil.rmtree(stale)
            except OSError:
                pass
        tmp = base / f".cap.{uuid.uuid4().hex}.tmp"
        try:
            tmp.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise ProjectError(
                "invalid_ledger",
                f"Cannot snapshot revision {revision}: {exc}.",
            ) from exc
        try:
            for rel, _size in self._iter_doc_files():
                try:
                    data = self._doc_path(rel).read_bytes()
                except OSError as exc:
                    raise ProjectError(
                        "invalid_ledger",
                        f"Cannot snapshot {rel}: {exc}.",
                    ) from exc
                target = tmp / rel
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    _atomic_write_bytes(target, data)
                except OSError as exc:
                    raise ProjectError(
                        "invalid_ledger",
                        f"Cannot snapshot {rel}: {exc}.",
                    ) from exc
            if dest.is_symlink() or dest.is_file():
                dest.unlink()
            elif dest.is_dir():
                shutil.rmtree(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp, dest)
        except ProjectError:
            try:
                shutil.rmtree(tmp, ignore_errors=True)
            except OSError:
                pass
            raise
        except OSError as exc:
            try:
                shutil.rmtree(tmp, ignore_errors=True)
            except OSError:
                pass
            raise ProjectError(
                "invalid_ledger",
                f"Cannot snapshot revision {revision}: {exc}.",
            ) from exc

    def _ensure_snapshot(self, revision):
        if not self._snapshot_exists(revision):
            self._capture_snapshot(revision)

    def _load_snapshot(self, revision):
        """Current snapshot bytes, or None when unrestorable."""
        if self._dir is None:
            snap = self._snapshots.get(revision)
            return dict(snap) if snap is not None else None
        try:
            src_dir = join_contained(
                self._dir, _SNAPSHOTS_DIRNAME, revision
            )
        except Exception:
            return None
        if not src_dir.is_dir():
            return None
        found = {}
        for target in sorted(src_dir.rglob("*")):
            if not target.is_file():
                continue
            try:
                rel = target.relative_to(src_dir).as_posix()
            except ValueError:
                continue
            try:
                found[rel] = target.read_bytes()
            except OSError as exc:
                raise ProjectError(
                    "invalid_ledger",
                    f"Cannot read snapshot {revision}/{rel}: {exc}.",
                ) from exc
        return found

    def _current_bytes(self):
        """All managed bytes for rollback staging."""
        found = {}
        for rel, _size in self._iter_doc_files():
            try:
                found[rel] = self._doc_path(rel).read_bytes()
            except OSError as exc:
                raise ProjectError(
                    "invalid_ledger",
                    f"Cannot stage {rel}: {exc}.",
                ) from exc
        return found

    def _clear_docs(self):
        """Delete every managed file, then prune emptied doc dirs."""
        for rel, _size in self._iter_doc_files():
            target = self._doc_path(rel)
            try:
                target.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise ProjectError(
                    "invalid_ledger",
                    f"Cannot clear {rel}: {exc}.",
                ) from exc
        for target in sorted(self._dir.rglob("*"), reverse=True):
            if not target.is_dir() or target == self._dir:
                continue
            try:
                rel = target.relative_to(self._dir).as_posix()
            except ValueError:
                continue
            if rel == "runs" or rel.startswith("runs/"):
                continue
            if rel == _SNAPSHOTS_DIRNAME or rel.startswith(
                _SNAPSHOTS_DIRNAME + "/"
            ):
                continue
            try:
                target.rmdir()
            except OSError:
                pass

    def _write_bytes_map(self, mapping):
        for rel, data in mapping.items():
            target = self._doc_path(rel)
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write_bytes(target, data)
            except OSError as exc:
                raise ProjectError(
                    "invalid_ledger",
                    f"Cannot restore {rel}: {exc}.",
                ) from exc

    def _restore_snapshot_bytes(self, snapshot, pre):
        """Replace managed bytes; best-effort rollback to pre."""
        try:
            self._clear_docs()
            self._write_bytes_map(snapshot)
        except ProjectError:
            try:
                self._clear_docs()
                self._write_bytes_map(pre)
            except Exception:
                pass
            raise

    def _linked_external_files(self):
        """Caller files outside `.rocket/`, sorted, never touched."""
        if self._linked_root is None:
            return []
        root = self._linked_root
        try:
            if not root.is_dir():
                return []
        except OSError:
            return []
        found = []
        try:
            targets = sorted(root.rglob("*"))
        except OSError:
            return []
        for target in targets:
            try:
                if not target.is_file():
                    continue
                rel = target.relative_to(root).as_posix()
            except (OSError, ValueError):
                continue
            if rel == _LINKED_CARVEOUT or rel.startswith(
                _LINKED_CARVEOUT + "/"
            ):
                continue
            try:
                size = target.stat().st_size
            except OSError:
                continue
            found.append({"path": rel, "bytes": size})
        return sorted(found, key=lambda e: e["path"])
