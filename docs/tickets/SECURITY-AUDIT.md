# SECURITY-AUDIT: Local-trust boundary audit

*Status: Backlog · Design: behavior-invariants.yaml LOCAL-SINGLE-USER*

## Why

The engine is on-device, single local user, stdio/loopback only — so engine-side restrictions that jail the local user from their own files are user-hostile, not security. But the RCE caution is real: the audit must draw the exact line between user freedom and remote-triggered execution, and verify every layer honors it.

## What (audit, then fix findings as own units)

- Inventory every place the engine refuses or restricts a *locally-initiated* file read/write (path guards, containment, console/project file ops) and rule whether each restriction protects the project store / agent-confusion cases or merely jails the user. Keep the former, remove the latter.
- Verify serve binds: HTTP adapter defaults and banners bind 127.0.0.1; no 0.0.0.0 anywhere (code, scripts, docs, docker/Demo paths). Fail closed on non-loopback.
- Verify no inbound funnel into python execution exists except user-controlled admission: no webhooks, callbacks, or remote-triggered routes that reach python_execute / cell admission. MCP/HTTP/stdio all require local-caller control.
- Reconcile with PATH-GUARD (normalization + project-store protection stay) and I22-AMEND (agent safety at fuel client edge, not engine user restrictions).
- Record findings; each fix lands as its own TDD unit, never bundled with feature work.

## Acceptance

Audit doc committed listing each boundary with keep/remove verdict + evidence; follow-up fix tickets filed for every remove; full suite + gate green.
