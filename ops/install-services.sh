#!/bin/bash
# Install Vector launchd services on the Mac mini.
#
# What this does:
#   1. Builds the venv at .venv if missing (pip install -e backend[dev])
#   2. Builds the frontend static bundle (pnpm install + pnpm build,
#      falls back to npm if pnpm isn't on PATH)
#   3. Substitutes __HOME__ and __REPO__ into the plist templates
#   4. Copies them to ~/Library/LaunchAgents/
#   5. launchctl loads both (backend + snapshot)
#
# Safe to re-run: each step is idempotent.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/Vector"

mkdir -p "$LAUNCH_DIR" "$LOG_DIR"

# --- venv -----------------------------------------------------------
if [[ ! -d "$REPO_DIR/.venv" ]]; then
    echo "==> creating venv at $REPO_DIR/.venv"
    python3 -m venv "$REPO_DIR/.venv"
fi
# shellcheck disable=SC1091
source "$REPO_DIR/.venv/bin/activate"
pip install --upgrade pip wheel >/dev/null
pip install -e "$REPO_DIR/backend"
deactivate

# --- frontend build -------------------------------------------------
if command -v pnpm >/dev/null 2>&1; then
    echo "==> building frontend with pnpm"
    (cd "$REPO_DIR/frontend" && pnpm install --silent && pnpm build)
elif command -v npm >/dev/null 2>&1; then
    echo "warn: pnpm not found, falling back to npm" >&2
    (cd "$REPO_DIR/frontend" && npm install --silent && npm run build)
else
    echo "warn: neither pnpm nor npm found; skipping frontend build" >&2
fi

# --- plists ---------------------------------------------------------
for label in industries.stratus.vector.backend industries.stratus.vector.snapshot industries.stratus.vector.watchdog; do
    SRC="$REPO_DIR/ops/$label.plist"
    DST="$LAUNCH_DIR/$label.plist"
    sed -e "s|__HOME__|$HOME|g" -e "s|__REPO__|$REPO_DIR|g" "$SRC" > "$DST"
    # Unload first if already loaded (idempotent install).
    launchctl unload "$DST" 2>/dev/null || true
    launchctl load -w "$DST"
    echo "==> loaded $label"
done

echo
echo "Done. Tail logs with:"
echo "  tail -f $LOG_DIR/backend.err.log"
echo "Check status:"
echo "  launchctl list | grep stratus.vector"
