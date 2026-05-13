"""Test-wide setup.

The dev workflow keeps a populated backend/.env with a generated bearer
token and real API keys. Pydantic-settings reads .env every time
Settings() is constructed (and several tests reset and reconstruct the
cached settings instance), which would cause auth-gated tests to 401.

Strategy: mutate the Settings class's model_config to disable .env
loading entirely under pytest. This applies to every future Settings()
instantiation — including the rebuild after a test resets the cache.

Also scrub VECTOR_* environment variables and re-seed the cached
Settings so the very first get_settings() call inside a test sees a
clean instance.
"""
from __future__ import annotations

import os

_TEST_SCRUB = (
    "VECTOR_BACKEND_BEARER",
    "VECTOR_ANTHROPIC_API_KEY",
    "VECTOR_ELEVENLABS_API_KEY",
    "VECTOR_LINEAR_API_KEY",
    "VECTOR_LINEAR_WEBHOOK_SECRET",
    "VECTOR_GOOGLE_OAUTH_CLIENT_ID",
    "VECTOR_GOOGLE_OAUTH_CLIENT_SECRET",
    "VECTOR_GOOGLE_MAPS_API_KEY",
    "VECTOR_OAUTH_TOKEN_KEY",
)

for _name in _TEST_SCRUB:
    os.environ.pop(_name, None)

from vector import config as _config  # noqa: E402 — must follow env scrub

# Disable .env file loading for every future Settings() instantiation.
# Several tests intentionally reset _config._settings to None and then
# call get_settings() again; without this patch, that rebuild would
# read backend/.env and reintroduce auth tokens.
_config.Settings.model_config = {
    **_config.Settings.model_config,
    "env_file": None,
}

# Seed the cache with a clean instance so the first get_settings() in
# any test (one that doesn't reset the cache) sees a known-empty state.
_config._settings = _config.Settings()
