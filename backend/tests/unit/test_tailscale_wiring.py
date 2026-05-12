from __future__ import annotations

import pytest

from vector.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    import vector.config as cfg

    cfg._settings = None
    yield
    cfg._settings = None


def test_cors_extra_parses_csv():
    s = Settings(cors_origins="http://a:1, http://b:2")
    assert s.cors_extra() == ["http://a:1", "http://b:2"]


def test_cors_extra_empty_is_empty():
    assert Settings(cors_origins="").cors_extra() == []
    assert Settings(cors_origins="   ").cors_extra() == []


def test_cors_extra_ignores_blank_tokens():
    s = Settings(cors_origins="http://a:1,,http://b:2,")
    assert s.cors_extra() == ["http://a:1", "http://b:2"]


def test_loopback_helper_recognizes_local_addresses():
    from vector.app import _loopback_host

    for host in ("127.0.0.1", "::1", "localhost", ""):
        assert _loopback_host(host)
    for host in ("0.0.0.0", "100.64.1.42", "mac-mini.tail.ts.net"):
        assert not _loopback_host(host)


def test_cors_origins_baseline_always_present():
    """The dev-server origins are always in the allowlist even if
    VECTOR_CORS_ORIGINS is unset, so `pnpm dev` keeps working."""
    from vector.app import _cors_origins

    origins = _cors_origins()
    assert "http://127.0.0.1:5173" in origins
    assert "http://localhost:5173" in origins


def test_cors_origins_appends_extra(monkeypatch):
    import vector.config as cfg

    cfg._settings = None
    monkeypatch.setenv("VECTOR_CORS_ORIGINS", "http://mac-mini.ts.net:5173")
    from vector.app import _cors_origins

    origins = _cors_origins()
    assert "http://mac-mini.ts.net:5173" in origins


def test_startup_warns_on_non_loopback_without_bearer(caplog, monkeypatch):
    import logging

    import vector.config as cfg

    cfg._settings = None
    monkeypatch.setenv("VECTOR_HOST", "0.0.0.0")
    monkeypatch.setenv("VECTOR_BACKEND_BEARER", "")

    caplog.set_level(logging.ERROR, logger="vector.startup")
    from vector.app import _on_start

    _on_start()
    messages = " ".join(rec.message for rec in caplog.records)
    assert "non-loopback" in messages
    assert "VECTOR_BACKEND_BEARER" in messages


def test_startup_quiet_when_loopback(caplog, monkeypatch):
    import logging

    import vector.config as cfg

    cfg._settings = None
    monkeypatch.setenv("VECTOR_HOST", "127.0.0.1")
    monkeypatch.setenv("VECTOR_BACKEND_BEARER", "")

    caplog.set_level(logging.ERROR, logger="vector.startup")
    from vector.app import _on_start

    _on_start()
    messages = " ".join(rec.message for rec in caplog.records)
    assert "non-loopback" not in messages


def test_startup_quiet_when_bearer_set(caplog, monkeypatch):
    import logging

    import vector.config as cfg

    cfg._settings = None
    monkeypatch.setenv("VECTOR_HOST", "0.0.0.0")
    monkeypatch.setenv("VECTOR_BACKEND_BEARER", "x" * 32)

    caplog.set_level(logging.ERROR, logger="vector.startup")
    from vector.app import _on_start

    _on_start()
    messages = " ".join(rec.message for rec in caplog.records)
    assert "non-loopback" not in messages
