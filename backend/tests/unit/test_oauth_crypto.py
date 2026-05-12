from __future__ import annotations

import os

import pytest

from vector.google_oauth.crypto import (
    CryptoError,
    decrypt_token,
    encrypt_token,
    generate_token_key,
)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    monkeypatch.delenv("VECTOR_OAUTH_TOKEN_KEY", raising=False)


def test_generate_token_key_decodes_to_32_bytes():
    import base64

    k = generate_token_key()
    raw = base64.urlsafe_b64decode(k)
    assert len(raw) == 32


def test_round_trip_with_key():
    k = generate_token_key()
    ct = encrypt_token("super-secret-refresh-token", key_b64=k)
    pt = decrypt_token(ct, key_b64=k)
    assert pt == "super-secret-refresh-token"
    # Ciphertext is base64 and longer than plaintext (nonce + tag/MAC).
    assert ct != "super-secret-refresh-token"


def test_round_trip_via_env(monkeypatch):
    k = generate_token_key()
    monkeypatch.setenv("VECTOR_OAUTH_TOKEN_KEY", k)
    ct = encrypt_token("hi")
    assert decrypt_token(ct) == "hi"


def test_missing_key_raises():
    with pytest.raises(CryptoError, match="not set"):
        encrypt_token("x", key_b64="")


def test_bad_key_length_raises():
    import base64

    short = base64.urlsafe_b64encode(b"x" * 10).decode()
    with pytest.raises(CryptoError, match="32 bytes"):
        encrypt_token("x", key_b64=short)


def test_wrong_key_fails_decrypt():
    k1 = generate_token_key()
    k2 = generate_token_key()
    ct = encrypt_token("hi", key_b64=k1)
    with pytest.raises(CryptoError):
        decrypt_token(ct, key_b64=k2)


def test_tampered_ciphertext_fails():
    k = generate_token_key()
    ct = encrypt_token("hello world", key_b64=k)
    tampered = ct[:-4] + ("AAAA" if not ct.endswith("AAAA") else "BBBB")
    with pytest.raises(CryptoError):
        decrypt_token(tampered, key_b64=k)


def test_bad_b64_decoding_raises():
    k = generate_token_key()
    with pytest.raises(CryptoError):
        decrypt_token("not!!base64!!", key_b64=k)


def test_unicode_round_trip():
    k = generate_token_key()
    msg = "naïve résumé — 漢字 🌊"
    assert decrypt_token(encrypt_token(msg, key_b64=k), key_b64=k) == msg
