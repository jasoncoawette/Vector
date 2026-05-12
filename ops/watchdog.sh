#!/bin/bash
# Watchdog: poll /health/deep on a loop. If the endpoint fails N times
# in a row, kill the backend process so launchd's KeepAlive restarts it.
#
# Why this exists:
#   launchd restarts on process death. A backend that's *alive but
#   hung* (deadlock, frozen event loop, lost DB connection) won't trip
#   KeepAlive on its own. This loop closes that gap.
#
# Tunables (env or backend/.env):
#   VECTOR_WATCHDOG_INTERVAL_S   poll period, default 30
#   VECTOR_WATCHDOG_FAIL_THRESHOLD  consecutive failures before SIGTERM, default 3
#   VECTOR_WATCHDOG_TIMEOUT_S    curl timeout per probe, default 5
#   VECTOR_HEALTH_URL            URL to probe, default http://127.0.0.1:7777/health/deep

set -uo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$REPO_DIR"

if [[ -f backend/.env ]]; then
    set -a
    # shellcheck disable=SC1091
    source backend/.env
    set +a
fi

INTERVAL="${VECTOR_WATCHDOG_INTERVAL_S:-30}"
THRESHOLD="${VECTOR_WATCHDOG_FAIL_THRESHOLD:-3}"
TIMEOUT="${VECTOR_WATCHDOG_TIMEOUT_S:-5}"
URL="${VECTOR_HEALTH_URL:-http://127.0.0.1:${VECTOR_PORT:-7777}/health/deep}"

fails=0
while true; do
    if curl -fsS --max-time "$TIMEOUT" "$URL" >/dev/null 2>&1; then
        if (( fails > 0 )); then
            echo "watchdog: recovered after $fails fails"
        fi
        fails=0
    else
        fails=$((fails + 1))
        echo "watchdog: probe failed ($fails/$THRESHOLD)" >&2
        if (( fails >= THRESHOLD )); then
            echo "watchdog: $fails consecutive failures -> killing backend" >&2
            # Find the python -m vector PID (launchd's KeepAlive will
            # restart it). Use pkill -f to match by command line; -TERM
            # so the backend has a chance to flush logs.
            pkill -TERM -f 'python -m vector' || true
            fails=0
        fi
    fi
    sleep "$INTERVAL"
done
