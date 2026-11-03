"""I12 named auth surface for the MCP adapter (INVARIANT-PARTIALS).

The MCP bridge is stdio to the local harness under OS identity:
no second party, no token, no listener. This file pins the named
surface so the no-auth decision stays explicit and loud-scoped.
"""

from rocket_engine.adapters.mcp.server import TRUST_NOTE


def test_trust_note_names_stdio_local_only_no_auth():
    assert "stdio" in TRUST_NOTE
    assert "no auth" in TRUST_NOTE
    assert "localhost" in TRUST_NOTE or "local" in TRUST_NOTE
