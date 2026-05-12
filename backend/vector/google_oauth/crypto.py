"""Symmetric encryption for OAuth refresh tokens.

We never persist refresh tokens in plaintext. The key comes from
`VECTOR_OAUTH_TOKEN_KEY` (base64-encoded 32 random bytes). If unset we
refuse to write tokens — better to crash loud than store a plaintext
refresh token on disk.

We use AES-256-GCM via stdlib's `hashlib.sha256` + a fixed-IV scheme
would be wrong; instead we use a one-shot scheme with a per-call random
nonce and the cryptography library when available. To keep the stdlib
path viable for environments without cryptography installed, we fall
back to scrypt+xor — flagged as legacy and only used if `cryptography`
isn't importable.

In production: install `cryptography` and set VECTOR_OAUTH_TOKEN_KEY.
"""
from __future__ import annotations

import base64
import logging
import os
import secrets

logger = logging.getLogger("vector.google_oauth.crypto")


class CryptoError(RuntimeError):
    pass


def generate_token_key() -> str:
    """Return a base64-encoded 32-byte key suitable for VECTOR_OAUTH_TOKEN_KEY."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def _load_key(b64: str) -> bytes:
    if not b64:
        raise CryptoError("VECTOR_OAUTH_TOKEN_KEY not set")
    try:
        raw = base64.urlsafe_b64decode(b64)
    except (ValueError, TypeError) as e:
        raise CryptoError(f"bad VECTOR_OAUTH_TOKEN_KEY: {e}") from e
    if len(raw) != 32:
        raise CryptoError(f"VECTOR_OAUTH_TOKEN_KEY must be 32 bytes, got {len(raw)}")
    return raw


def _try_aes_gcm():
    """Return (encrypt_fn, decrypt_fn) using AES-GCM, or None if unavailable.

    We deliberately catch BaseException here. The `cryptography` package
    can be partially installed (e.g. missing the cffi backend), in which
    case its module import raises a non-Exception subclass like
    pyo3_runtime.PanicException. Falling through to the HMAC-XOR
    fallback is better than crashing module-import time."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except BaseException as e:  # noqa: BLE001
        logger.debug("cryptography unavailable: %s", e)
        return None
    # Smoke-test the binding once. If decrypting fails here we know the
    # Rust binding is alive; better to find out at import than mid-call.
    try:
        AESGCM(secrets.token_bytes(32)).encrypt(secrets.token_bytes(12), b"x", None)
    except BaseException as e:  # noqa: BLE001
        logger.debug("cryptography binding broken: %s", e)
        return None

    def _encrypt(plaintext: bytes, key_b64: str) -> str:
        key = _load_key(key_b64)
        nonce = secrets.token_bytes(12)
        ct = AESGCM(key).encrypt(nonce, plaintext, associated_data=None)
        return base64.urlsafe_b64encode(nonce + ct).decode("ascii")

    def _decrypt(blob_b64: str, key_b64: str) -> bytes:
        key = _load_key(key_b64)
        try:
            blob = base64.urlsafe_b64decode(blob_b64)
        except (ValueError, TypeError) as e:
            raise CryptoError(f"bad ciphertext encoding: {e}") from e
        if len(blob) < 28:
            raise CryptoError("ciphertext too short")
        nonce, ct = blob[:12], blob[12:]
        try:
            return AESGCM(key).decrypt(nonce, ct, associated_data=None)
        except Exception as e:  # noqa: BLE001
            raise CryptoError(f"decrypt failed: {e}") from e

    return _encrypt, _decrypt


def _fallback_xor():
    """HMAC-derived keystream XOR + HMAC-SHA256 authentication tag.

    Not as strong as AES-GCM but stdlib-only. Used only when the
    `cryptography` package isn't installed. Logs a warning."""
    import hashlib
    import hmac

    def _ks(key: bytes, nonce: bytes, n: int) -> bytes:
        out = bytearray()
        counter = 0
        while len(out) < n:
            block = hmac.new(
                key, nonce + counter.to_bytes(4, "big"), hashlib.sha256
            ).digest()
            out.extend(block)
            counter += 1
        return bytes(out[:n])

    def _encrypt(plaintext: bytes, key_b64: str) -> str:
        key = _load_key(key_b64)
        nonce = secrets.token_bytes(16)
        ks = _ks(key, nonce, len(plaintext))
        ct = bytes(a ^ b for a, b in zip(plaintext, ks))
        tag = hmac.new(key, nonce + ct, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(nonce + tag + ct).decode("ascii")

    def _decrypt(blob_b64: str, key_b64: str) -> bytes:
        key = _load_key(key_b64)
        try:
            blob = base64.urlsafe_b64decode(blob_b64)
        except (ValueError, TypeError) as e:
            raise CryptoError(f"bad ciphertext encoding: {e}") from e
        if len(blob) < 48:
            raise CryptoError("ciphertext too short")
        nonce, tag, ct = blob[:16], blob[16:48], blob[48:]
        expected = hmac.new(key, nonce + ct, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise CryptoError("auth tag mismatch")
        ks = _ks(key, nonce, len(ct))
        return bytes(a ^ b for a, b in zip(ct, ks))

    return _encrypt, _decrypt


_impl = _try_aes_gcm()
if _impl is None:
    logger.warning(
        "cryptography unavailable; using stdlib HMAC-XOR fallback for OAuth tokens"
    )
    _impl = _fallback_xor()

_encrypt, _decrypt = _impl


def encrypt_token(plaintext: str, *, key_b64: str | None = None) -> str:
    """Encrypt + authenticate a refresh-token string. Returns base64."""
    k = key_b64 if key_b64 is not None else os.environ.get("VECTOR_OAUTH_TOKEN_KEY", "")
    return _encrypt(plaintext.encode("utf-8"), k)


def decrypt_token(ciphertext_b64: str, *, key_b64: str | None = None) -> str:
    k = key_b64 if key_b64 is not None else os.environ.get("VECTOR_OAUTH_TOKEN_KEY", "")
    return _decrypt(ciphertext_b64, k).decode("utf-8")
