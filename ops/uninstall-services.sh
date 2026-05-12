#!/bin/bash
# Stop and remove Vector launchd services. The venv, repo, and the
# SQLite database are left in place.

set -euo pipefail

LAUNCH_DIR="$HOME/Library/LaunchAgents"

for label in industries.stratus.vector.backend industries.stratus.vector.snapshot industries.stratus.vector.watchdog; do
    DST="$LAUNCH_DIR/$label.plist"
    if [[ -f "$DST" ]]; then
        launchctl unload "$DST" 2>/dev/null || true
        rm -f "$DST"
        echo "==> removed $label"
    fi
done
