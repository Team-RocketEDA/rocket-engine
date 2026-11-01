"""Entity-record projection and backfill reads."""

from ...interfaces import engine_ecs_store
from ..errors import ProjectError

from .shared import _MAX_DOC_BYTES

class _EntityMixin:
    """Entity projection helpers for ProjectService."""

    def _entity_records(self):
        """Decode every entity record into world-snapshot entries."""
        records = []
        for rel, _size in self._iter_doc_files():
            entity = engine_ecs_store.entity_from_doc_path(rel)
            if entity is None:
                continue
            text = self._read_doc_text(rel, rel)
            if text is None:
                raise ProjectError(
                    "invalid_document",
                    f"Entity record vanished mid-read: {rel}.",
                )
            try:
                decoded = engine_ecs_store.decode_entity_doc(text, rel)
            except engine_ecs_store.EcsError as exc:
                raise ProjectError(exc.code, str(exc)) from exc
            records.append(
                {
                    "components": decoded["components"],
                    "id": decoded["entity"],
                    "kind": decoded["kind"],
                }
            )
        return records

    def _backfill_records(self):
        """Project every non-entity doc as a virtual entity."""
        entries = [
            {"bytes": size, "path": rel}
            for rel, size in self._iter_doc_files()
        ]
        return engine_ecs_store.backfill_entities(entries)

    def _find_backfill(self, entity):
        """Return the virtual record for one backfilled id."""
        for record in self._backfill_records():
            if record["id"] == entity:
                return record
        raise ProjectError("unknown_entity", f"No such entity: {entity}.")

    def _read_backfill_component(self, entity, component):
        """Serve one projected doc component for a backfilled id."""
        record = self._find_backfill(entity)
        if component != engine_ecs_store.BACKFILL_COMPONENT:
            raise ProjectError(
                "unknown_component",
                f"No component {component!r} on {entity}.",
            )
        data = record["components"][engine_ecs_store.BACKFILL_COMPONENT]
        return {
            "address": engine_ecs_store.format_address(entity, component),
            "component": component,
            "current_revision": self._current_revision,
            "data": dict(data),
            "entity": entity,
            "path": data["path"],
            "project_id": self._project_id,
        }

    def _read_entity_record(self, entity):
        """Return (path, decoded) for one live entity id."""
        path = engine_ecs_store.entity_doc_path(entity)
        text = self._read_doc_text(path, path)
        if text is None:
            raise ProjectError(
                "unknown_entity", f"No such entity: {entity}."
            )
        try:
            decoded = engine_ecs_store.decode_entity_doc(text, path)
        except engine_ecs_store.EcsError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        if decoded["entity"] != entity:
            raise ProjectError(
                "invalid_document",
                f"Entity record id drift at {path}.",
            )
        return path, decoded

    def _store_entity_record(self, path, entity, kind, components):
        """Encode and persist one entity record under its path."""
        text = engine_ecs_store.encode_entity_doc(entity, kind, components)
        if len(text.encode("utf-8")) > _MAX_DOC_BYTES:
            raise ProjectError(
                "invalid_command",
                f"Entity record exceeds the size limit: {path}.",
            )
        self._write_doc_text(path, text, path)

    def _ecs_response(self, request_id, previous, diff, record, extra):
        """CRUD-shaped mutation mapping for one entity change."""
        response = {
            "project_id": self._project_id,
            "previous_revision": previous,
            "current_revision": self._current_revision,
            "revision_transition": {
                "from": previous,
                "to": self._current_revision,
            },
            "actor": self._actor,
            "diff_summary": diff,
            "rewind_handle": {
                "project_id": self._project_id,
                "revision": previous,
                "request_id": request_id,
            },
            "events": [record],
            "event_cursor": self._cursor(),
            "request_id": request_id,
        }
        response.update(extra)
        return response
