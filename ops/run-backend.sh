#!/bin/bash
# Backend launcher. Sourced by launchd via the plist's ProgramArguments.
#
# Steps:
#   1. cd into repo, source .env if present (export-as-env semantics)
#   2. activate the venv at .venv (Python 3.11+) — fail if missing
#   3. exec uvicorn so launchd sees our PID, not a shell parent
#
# Crash semantics:
#   - Any non-zero exit triggers launchd's KeepAlive (10s throttle).
#   - Catastrophic startup errors (missing .venv, bad config) exit
#     fast so the throttle starts immediately rather than burning loops.

set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$REPO_DIR"

# Load .env if present. Exported keys become environment for uvicorn.
if [[ -f backend/.env ]]; then
    set -a
    # shellcheck disable=SC1091
    source backend/.env
    set +a
fi

VENV="${VECTOR_VENV:-$REPO_DIR/.venv}"
if [[ ! -d "$VENV" ]]; then
    echo "fatal: venv not found at $VENV — run ops/install-services.sh first" >&2
    exit 78  # EX_CONFIG
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

# Exec the backend. -m vector runs vector/__main__.py which calls
# uvicorn with the configured host/port and installs JSON logging
# before uvicorn's own chatter starts.
exec python -m vector
