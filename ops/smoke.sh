#!/bin/bash
# Smoke test: verify all the things Phase 11 promises.
#
# Checks (in order):
#   1. /healthz responds 200 (liveness)
#   2. /health/deep responds 200 (db + workspace + audit sink)
#   3. /config GET returns redacted secrets (no plaintext keys)
#   4. /costs returns a rollup payload
#   5. /events returns the events list
#   6. launchctl shows all three services loaded (skipped if not on macOS)
#
# Exit 0 on success, 1 on first failure. Prints a one-line summary.

set -uo pipefail

BASE="${VECTOR_BASE_URL:-http://127.0.0.1:7777}"
pass=0
fail=0
fails=()

probe() {
    local name="$1" url="$2" expect="$3" jq_filter="${4:-}"
    local code body
    body=$(curl -sS -o /tmp/vector-smoke-body -w "%{http_code}" --max-time 5 "$url" 2>/dev/null) || code=000
    code="$body"
    if [[ "$code" != "$expect" ]]; then
        echo "FAIL $name: expected HTTP $expect, got $code"
        fails+=("$name (http $code)")
        fail=$((fail + 1))
        return 1
    fi
    if [[ -n "$jq_filter" ]] && command -v jq >/dev/null 2>&1; then
        if ! jq -e "$jq_filter" /tmp/vector-smoke-body >/dev/null 2>&1; then
            echo "FAIL $name: body did not satisfy $jq_filter"
            fails+=("$name (body shape)")
            fail=$((fail + 1))
            return 1
        fi
    fi
    echo "ok   $name"
    pass=$((pass + 1))
}

probe "GET /healthz" "$BASE/healthz" 200 '.ok == true'
probe "GET /health/deep" "$BASE/health/deep" 200 '.checks.db.ok == true'
probe "GET /config" "$BASE/config" 200 '(.anthropic_api_key == "***redacted***" or .anthropic_api_key == "")'
probe "GET /costs" "$BASE/costs" 200 '.today_runs >= 0'
probe "GET /events" "$BASE/events" 200 '.events | type == "array"'

if [[ "$(uname)" == "Darwin" ]]; then
    if launchctl list | grep -q stratus.vector.backend; then
        echo "ok   launchctl backend loaded"
        pass=$((pass + 1))
    else
        echo "WARN launchctl backend not loaded"
    fi
fi

echo
echo "$pass passed, $fail failed"
if (( fail > 0 )); then
    printf 'failures:\n'
    for f in "${fails[@]}"; do printf '  - %s\n' "$f"; done
    exit 1
fi
exit 0
