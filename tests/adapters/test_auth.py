"""I12 named auth surface: local trust needs no credentials, remote is deferred (F5)."""

import pytest

from rocket_engine.adapters import auth


def test_local_transports_need_no_credentials():
    for transport in ("stdio", "mcp", "ipc"):
        context = auth.caller_context(transport)
        assert auth.is_local_caller(context) is True
        assert auth.require_local_caller(context) == context


def test_http_loopback_is_local():
    for host in ("127.0.0.1", "localhost", "::1", "127.0.0.2", None):
        context = auth.caller_context("http", remote_addr=host)
        assert auth.is_local_caller(context) is True, host
        assert auth.require_local_caller(context) == context


def test_http_remote_is_deferred_loudly():
    for host in ("0.0.0.0", "192.168.1.10", "203.0.113.7", "example.com"):
        context = auth.caller_context("http", remote_addr=host)
        assert auth.is_local_caller(context) is False, host
        with pytest.raises(Exception) as excinfo:
            auth.require_local_caller(context)
        assert getattr(excinfo.value, "code", None) == "remote_auth_deferred"
        assert "REMOTE-EXEC" in str(excinfo.value)


def test_unknown_transport_fails_closed():
    context = auth.caller_context("carrier-pigeon")
    assert auth.is_local_caller(context) is False
    with pytest.raises(Exception) as excinfo:
        auth.require_local_caller(context)
    assert getattr(excinfo.value, "code", None) == "remote_auth_deferred"


def test_describe_trust_names_every_caller_kind():
    trust = auth.describe_trust()
    assert set(trust) == {"stdio", "mcp", "ipc", "http", "remote"}
    assert "no auth" in trust["stdio"]
    assert "ADR-005" in trust["mcp"]
    assert "ADR-006" in trust["http"]
    assert "REMOTE-EXEC" in trust["remote"]


def test_stdio_console_matches_named_surface():
    from rocket_engine.adapters.stdio_console import (
        LOCAL_ONLY_TRUST,
        TRUST_NOTE,
    )

    assert LOCAL_ONLY_TRUST is True
    assert "no auth step" in TRUST_NOTE
    assert "REMOTE-EXEC" in auth.TRUST_MODEL
