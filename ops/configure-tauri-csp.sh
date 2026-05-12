#!/bin/bash
# Rewrite desktop/tauri.conf.json's CSP to point at the configured
# backend host. Useful when you run the backend on a Mac mini and
# want the Tauri shell on a MacBook to connect over Tailscale.
#
# Usage:
#   ops/configure-tauri-csp.sh <backend-host>[:port]
# Examples:
#   ops/configure-tauri-csp.sh 127.0.0.1:7777          # local default
#   ops/configure-tauri-csp.sh mac-mini.tail-scale.ts.net:7777
#   ops/configure-tauri-csp.sh 100.64.1.42:7777        # Tailscale CGNAT IP

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONF="$REPO_DIR/desktop/tauri.conf.json"

target="${1:-127.0.0.1:7777}"
if ! [[ "$target" =~ : ]]; then
    target="${target}:7777"
fi

# Allow both http+ws so the WebSocket voice stream connects too.
# Keep 'self' so served bundle assets still load.
new_csp="default-src 'self'; connect-src 'self' http://${target} ws://${target}; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'"

# Find the existing csp line and replace it. Use python so we don't
# depend on a specific sed flavor (GNU vs BSD).
python3 - "$CONF" "$new_csp" <<'PY'
import json, sys, pathlib
conf_path = pathlib.Path(sys.argv[1])
new_csp = sys.argv[2]
data = json.loads(conf_path.read_text())
data.setdefault("app", {}).setdefault("security", {})["csp"] = new_csp
conf_path.write_text(json.dumps(data, indent=2) + "\n")
print(f"==> CSP rewritten in {conf_path}")
print(f"    connect-src now allows http://{new_csp.split('http://', 1)[1].split(' ')[0]}")
PY
