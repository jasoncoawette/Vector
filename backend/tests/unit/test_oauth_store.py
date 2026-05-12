from __future__ import annotations

from pathlib import Path

import pytest

from vector.google_oauth import TokenStore, generate_token_key
from vector.store import connect


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("VECTOR_OAUTH_TOKEN_KEY", generate_token_key())


@pytest.fixture()
def store(tmp_path: Path):
    conn = connect(tmp_path / "v.db", check_integrity=False)
    yield TokenStore(conn)
    conn.close()


def test_save_then_read_refresh_token(store):
    store.save(
        account="jason@stratus",
        scopes=["calendar"],
        refresh_token="RT-abc-123",
        access_token="AT",
        expires_in=3600,
    )
    tok = store.get("jason@stratus")
    assert tok is not None
    assert tok.scopes == "calendar"
    assert tok.access_token == "AT"
    # Refresh token is encrypted on disk — never appears in plaintext.
    assert "RT-abc-123" not in tok.refresh_token_ciphertext
    # But decryption round-trips.
    assert store.get_refresh_token("jason@stratus") == "RT-abc-123"


def test_save_upserts_on_conflict(store):
    store.save(account="a", scopes=["s1"], refresh_token="R1", expires_in=10)
    store.save(
        account="a",
        scopes=["s1", "s2"],
        refresh_token="R2",
        access_token="A2",
        expires_in=20,
    )
    tok = store.get("a")
    assert tok.scopes == "s1 s2"
    assert tok.access_token == "A2"
    assert store.get_refresh_token("a") == "R2"


def test_update_access_token_only(store):
    store.save(account="a", scopes=["s"], refresh_token="R", expires_in=0)
    store.update_access_token(account="a", access_token="A-new", expires_in=42)
    tok = store.get("a")
    assert tok.access_token == "A-new"
    # Refresh token unchanged.
    assert store.get_refresh_token("a") == "R"


def test_list_accounts_sorted(store):
    store.save(account="b", scopes=["s"], refresh_token="R")
    store.save(account="a", scopes=["s"], refresh_token="R")
    assert store.list_accounts() == ["a", "b"]


def test_delete_removes(store):
    store.save(account="a", scopes=["s"], refresh_token="R")
    assert store.delete("a") is True
    assert store.get("a") is None
    assert store.delete("a") is False  # second time -> false


def test_get_unknown_account_is_none(store):
    assert store.get("missing") is None
    assert store.get_refresh_token("missing") is None


def test_corrupt_refresh_token_raises_on_decrypt(store):
    store.save(account="a", scopes=["s"], refresh_token="R")
    # Tamper with the ciphertext directly.
    store._conn.execute(
        "UPDATE google_tokens SET refresh_token_ciphertext='garbled' WHERE account='a'"
    )
    with pytest.raises(Exception):
        store.get_refresh_token("a")
