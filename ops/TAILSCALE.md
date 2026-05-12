# Tailscale — Mac mini host + MacBook access

Vector is built to live on one Mac mini (running launchd-supervised
services from `ops/`) with the MacBook reaching it over Tailscale.
This file walks through the wiring.

## Threat model in one paragraph

The backend exposes `/voice/stream` (WebSocket — burns LLM tokens),
`/tools/call` (writes files), `/agents/spawn` (orchestrates Claude),
`/plans` (spawns plans of agents), and the Gmail / Calendar /
Notebook write endpoints. Off loopback, **every mutation must
require a bearer token** or someone on your tailnet (or worse, the
local network if you mis-configure) can drive the backend. Bearer +
Tailscale ACL = two layers; we want both.

## One-time setup on both machines

```bash
brew install tailscale
tailscale up                       # interactive — sign in
tailscale status                   # confirm both machines visible
```

Pick stable hostnames in the Tailscale admin console — say
`mac-mini` and `laptop`. Tailscale gives them DNS names
`mac-mini.<tailnet>.ts.net`.

## Configure the Mac mini backend

In `backend/.env`:

```bash
# Bind to all interfaces so the Tailscale interface accepts connections.
VECTOR_HOST=0.0.0.0

# REQUIRED off loopback. Generate one:
#   openssl rand -hex 32
VECTOR_BACKEND_BEARER=<32+ random hex chars>

# Tell CORS which other Tailscale machines may hit the API directly.
VECTOR_CORS_ORIGINS=http://laptop.<tailnet>.ts.net:5173,http://mac-mini.<tailnet>.ts.net:5173
```

Restart the backend service:

```bash
launchctl kickstart -k gui/$(id -u)/industries.stratus.vector.backend
```

If `VECTOR_HOST` isn't loopback and `VECTOR_BACKEND_BEARER` is
empty, the backend logs an `error` line at startup:

```
ERROR vector.startup vector is bound to a non-loopback host but
VECTOR_BACKEND_BEARER is unset; mutation endpoints will be open
to anyone who can reach the port
```

Treat that line as a stop-the-world bug.

## Confirm from the MacBook

```bash
# Should return 200 with build hash.
curl http://mac-mini.<tailnet>.ts.net:7777/healthz

# Mutations need the bearer.
curl -X POST \
  http://mac-mini.<tailnet>.ts.net:7777/tasks \
  -H "Authorization: Bearer <your-secret>" \
  -H "Content-Type: application/json" \
  -d '{"title":"hello from laptop"}'
```

## Build the Tauri shell for the MacBook

The desktop bundle's CSP is locked down to one backend host. Rewrite
it to your Mac mini's Tailscale name before building:

```bash
cd ~/Vector
ops/configure-tauri-csp.sh mac-mini.<tailnet>.ts.net:7777

# Also tell Vite where the backend lives so api.ts resolves correctly.
export VITE_BACKEND=http://mac-mini.<tailnet>.ts.net:7777

cd desktop
cargo tauri build
```

The browser bundle in `frontend/build/` ships inside the .app —
because we baked `VITE_BACKEND` at build time, every fetch goes to
the Mac mini.

## Mobile (`/m` route)

The `isLocalBackend()` gate in the mobile page already accepts
Tailscale CGNAT addresses (`100.x.y.z`) and `.ts.net` hostnames
once you open the page from the laptop. Paste the bearer token
into the field on the voice/mobile screens — it's saved to
localStorage so you only do it once.

## Tailscale ACL recommendation

In your Tailscale admin console, restrict who can reach the Mac
mini on port 7777:

```hujson
"acls": [
  {
    "action": "accept",
    "src":    ["autogroup:owner"],
    "dst":    ["mac-mini:7777"]
  }
]
```

If you're the only user, `autogroup:owner` is enough. With a
partner or contractor, tag those devices and add them explicitly.

## What's NOT exposed

- The SQLite DB is at `~/VectorWorkspace/vector.db` on the Mac
  mini. No tool gives a remote caller read access to the raw file.
- The Obsidian vault lives inside the `FileGuard` scope. Notes are
  reachable through `/tools/call` with `obsidian.read` — which is
  bearer-gated.
- ITAR-tagged content stays where it is: rules in PRD §14.9 still
  apply. Tailscale only changes who can reach the HTTP API, not
  what content the API will return.

## Rollback

```bash
# Bring Vector back to loopback-only.
sed -i '' 's/^VECTOR_HOST=.*/VECTOR_HOST=127.0.0.1/' backend/.env
launchctl kickstart -k gui/$(id -u)/industries.stratus.vector.backend
ops/configure-tauri-csp.sh 127.0.0.1:7777
```
