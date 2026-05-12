"""SQLite token store for Google OAuth credentials.

One row per (provider, account) tuple. Refresh tokens are encrypted at
rest with the key from `VECTOR_OAUTH_TOKEN_KEY`. Access tokens live in
memory only (they expire fast and are cheap to refresh).
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

from .crypto import decrypt_token, encrypt_token

# Common Google scope strings.
SCOPES_CALENDAR = (
    "https://www.googleapis.com/auth/calendar.events",
)
SCOPES_GMAIL_SEND = (
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
)


@dataclass
class GoogleToken:
    provider: str  # "google"
    account: str   # email or "default"
    scopes: str    # space-separated
    refresh_token_ciphertext: str
    access_token: str | None = None
    access_token_expires_at: float = 0.0
    created_at: float = 0.0
    updated_at: float = 0.0


SCHEMA = """
CREATE TABLE IF NOT EXISTS google_tokens (
    provider TEXT NOT NULL,
    account TEXT NOT NULL,
    scopes TEXT NOT NULL,
    refresh_token_ciphertext TEXT NOT NULL,
    access_token TEXT,
    access_token_expires_at REAL NOT NULL DEFAULT 0.0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (provider, account)
);
"""


class TokenStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        conn.executescript(SCHEMA)

    def save(
        self,
        *,
        account: str,
        scopes: list[str] | tuple[str, ...],
        refresh_token: str,
        access_token: str | None = None,
        expires_in: int = 0,
    ) -> None:
        now = time.time()
        expires_at = now + expires_in if expires_in else 0.0
        ciphertext = encrypt_token(refresh_token)
        self._conn.execute(
            """
            INSERT INTO google_tokens(
                provider, account, scopes, refresh_token_ciphertext,
                access_token, access_token_expires_at,
                created_at, updated_at
            ) VALUES('google', ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, account) DO UPDATE SET
                scopes = excluded.scopes,
                refresh_token_ciphertext = excluded.refresh_token_ciphertext,
                access_token = COALESCE(excluded.access_token, google_tokens.access_token),
                access_token_expires_at = excluded.access_token_expires_at,
                updated_at = excluded.updated_at
            """,
            (
                account,
                " ".join(scopes),
                ciphertext,
                access_token,
                expires_at,
                now,
                now,
            ),
        )

    def update_access_token(
        self, *, account: str, access_token: str, expires_in: int
    ) -> None:
        now = time.time()
        self._conn.execute(
            """
            UPDATE google_tokens
            SET access_token = ?, access_token_expires_at = ?, updated_at = ?
            WHERE provider = 'google' AND account = ?
            """,
            (access_token, now + expires_in, now, account),
        )

    def get(self, account: str) -> GoogleToken | None:
        row = self._conn.execute(
            "SELECT * FROM google_tokens WHERE provider='google' AND account=?",
            (account,),
        ).fetchone()
        if row is None:
            return None
        return GoogleToken(
            provider=row["provider"],
            account=row["account"],
            scopes=row["scopes"],
            refresh_token_ciphertext=row["refresh_token_ciphertext"],
            access_token=row["access_token"],
            access_token_expires_at=row["access_token_expires_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_accounts(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT account FROM google_tokens WHERE provider='google' ORDER BY account"
        ).fetchall()
        return [r["account"] for r in rows]

    def delete(self, account: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM google_tokens WHERE provider='google' AND account=?",
            (account,),
        )
        return cur.rowcount > 0

    def get_refresh_token(self, account: str) -> str | None:
        """Decrypt and return the plaintext refresh token. Throws on
        decryption failure — bad key or tampered ciphertext."""
        tok = self.get(account)
        if tok is None:
            return None
        return decrypt_token(tok.refresh_token_ciphertext)
