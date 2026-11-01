"""Event cursor, retention, and append machinery."""


class _EventMixin:
    """Event cursor and retention for ProjectService."""

    def _cursor(self):
        return self._events[-1]["seq"] if self._events else 0

    def _retained_head(self):
        return self._events[0]["seq"] if self._events else 0

    def _trim(self):
        over = len(self._events) - self._max_retained_events
        if over > 0:
            del self._events[:over]

    def _append_event(self, event, request_id, data):
        record = {
            "seq": self._cursor() + 1,
            "event": event,
            "request_id": request_id,
            "project_id": self._project_id,
            "actor": self._actor,
            "data": data,
        }
        self._events.append(record)
        self._trim()
        return record
