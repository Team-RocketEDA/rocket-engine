# adapters/ipc — JSON command handler for desktop IPC

`IpcTransport.handle(text)` accepts one JSON envelope with `project_id`, `operation`, optional `arguments`, and optional `request_id`. It enforces an optional project binding and delegates the call to `Engine.submit`.

The current class does not implement the planned length-prefixed framing, persistent Electron child process, reconnect handling, or pushed event stream. Clients can read ordered changes through `get_events_since`. Keep desktop process lifecycle and renderer code outside the engine package.

## Boundaries

This adapter owns JSON envelope parsing, request IDs, and project-scope checks. It does not own project logic or solver behavior. Shared shapes live in [`interfaces/`](../../interfaces/README.md); the transport overview is in [`adapters/`](../README.md).
