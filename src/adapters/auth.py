"""Named caller-trust surface (I12): local trust, remote deferred.

The engine is caller-blind (ADR-005): stdio, MCP, IPC, and HTTP serve
one API with no per-transport policy. Local callers run on this machine
under OS identity with no auth step because there is no second party;
for HTTP the loopback interface is the trust boundary (ADR-006) and the
listener refuses non-loopback binds. Remote or multi-user access needs
a separate authenticated adapter — deferred scope owned by REMOTE-EXEC,
never this surface with a flag.
"""

import ipaddress

from .errors import AdapterError

__all__ = [
    "LOCAL_TRANSPORTS",
    "LOOPBACK_HOSTS",
    "REMOTE_AUTH_OWNER",
    "TRUST_MODEL",
    "caller_context",
    "describe_trust",
    "is_local_caller",
    "require_local_caller",
]

LOCAL_TRANSPORTS = frozenset({"stdio", "mcp", "ipc", "http"})

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

REMOTE_AUTH_OWNER = "REMOTE-EXEC"

TRUST_MODEL = (
    "Local-only trust: stdio, MCP, IPC, and HTTP callers run on this "
    "machine under OS identity with no auth step because there is no "
    "second party (ADR-005 caller-blind engine, ADR-006 localhost-only "
    "HTTP). Remote or multi-user access needs a separate authenticated "
    "adapter — deferred scope owned by REMOTE-EXEC, never this surface "
    "with a flag."
)


def caller_context(transport, remote_addr=None):
    """Describe one caller for a trust decision.

    Args:
        transport: Calling transport name (stdio, mcp, ipc, http).
        remote_addr: Peer address for socket transports, or None for
            in-process calls and transports without a socket.

    Returns:
        Caller context mapping with transport and remote_addr.
    """
    return {"transport": transport, "remote_addr": remote_addr}


def _is_loopback(host):
    """Check whether a host string is a loopback address."""
    if host in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_local_caller(context):
    """Check whether a caller carries local trust.

    stdio, MCP, and IPC are local by construction (no socket, no
    second party). HTTP is local only for loopback peers; an unknown
    transport is never local.

    Args:
        context: Caller context from caller_context.

    Returns:
        True for local-trust callers, False otherwise.
    """
    transport = context.get("transport")
    if transport in ("stdio", "mcp", "ipc"):
        return True
    if transport == "http":
        remote_addr = context.get("remote_addr")
        return remote_addr is None or _is_loopback(remote_addr)
    return False


def require_local_caller(context):
    """Admit local-trust callers; refuse remote callers loudly.

    Args:
        context: Caller context from caller_context.

    Returns:
        The context unchanged when the caller is local.

    Raises:
        AdapterError: remote_auth_deferred for a non-local caller —
            remote/multi-user auth is deferred scope owned by
            REMOTE-EXEC and no credentials are accepted here.

    Caution: Refusal is terminal, never a credential prompt — there is
        no token check to fall back to on this surface.
    """
    if is_local_caller(context):
        return context
    raise AdapterError(
        "remote_auth_deferred",
        f"Refused {context.get('transport')} caller from "
        f"{context.get('remote_addr')}: remote/multi-user engine access "
        "needs a separate authenticated adapter (deferred scope owned "
        f"by {REMOTE_AUTH_OWNER}, ADR-006) — no credentials are "
        "accepted here.",
    )


def describe_trust():
    """Name the trust rule for every caller kind.

    Returns:
        Mapping of caller kind (stdio, mcp, ipc, http, remote) to its
            trust rule text.
    """
    return {
        "stdio": (
            "local OS identity, no auth step — no second party "
            "(see stdio_console.TRUST_NOTE)"
        ),
        "mcp": (
            "local stdio bridge, no auth step — same caller-blind API "
            "(ADR-005)"
        ),
        "ipc": (
            "local Electron stdio, no auth step — same caller-blind API "
            "(ADR-005)"
        ),
        "http": (
            "localhost-only, no auth — the loopback interface is the "
            "trust boundary (ADR-006)"
        ),
        "remote": (
            "unsupported: remote/multi-user auth is deferred scope "
            f"owned by {REMOTE_AUTH_OWNER}"
        ),
    }
