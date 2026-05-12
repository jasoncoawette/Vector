# Vector ops

Service-level self-healing for the Mac mini host. Three launchd jobs
(backend, snapshot, watchdog) plus an integrity check on every boot.

## What runs

| Service | Plist | Purpose |
|---|---|---|
| `industries.stratus.vector.backend` | `industries.stratus.vector.backend.plist` | The FastAPI app + bundled SvelteKit frontend on `:7777`. KeepAlive restarts on non-zero exit; ThrottleInterval=10s prevents fast crash loops. |
| `industries.stratus.vector.snapshot` | `industries.stratus.vector.snapshot.plist` | Hourly atomic SQLite `.backup` to `~/VectorBackups/`. Rotates to keep the newest 48 (2 days). |
| `industries.stratus.vector.watchdog` | `industries.stratus.vector.watchdog.plist` | Polls `/health/deep` every 30s. After 3 consecutive failures, SIGTERMs the backend so launchd restarts it. Watchdog is itself KeepAlive'd. |

On every backend boot:
- `PRAGMA integrity_check` runs. On failure, the corrupt file is moved aside (`vector.db.corrupt-YYYYMMDD-HHMMSS`) and the newest snapshot from `~/VectorBackups/` is copied into place. If that's also corrupt, we exit loud so launchd's throttle kicks in.
- Any agent runs left in `queued` / `running` state from a previous process are flipped to `interrupted` (PRD §14.10 crash recovery).

## Install on the Mac mini

```bash
git clone <repo> ~/Vector
cd ~/Vector

# Fill in keys before installing. At minimum:
#   VECTOR_ANTHROPIC_API_KEY
#   VECTOR_ELEVENLABS_API_KEY
#   VECTOR_BACKEND_BEARER  (generate: openssl rand -hex 32)
cp backend/.env.example backend/.env
$EDITOR backend/.env

bash ops/install-services.sh
```

The install script is idempotent:
1. Creates `.venv/` if missing and `pip install -e backend`
2. `cd frontend && pnpm install && pnpm build` so the backend can serve the bundle at `/`
3. Substitutes `__HOME__` / `__REPO__` into the plist templates
4. Copies them to `~/Library/LaunchAgents/` and `launchctl load -w`s each one

## Verify

```bash
# Should list all three with PIDs.
launchctl list | grep stratus.vector

# Liveness (cheap; just checks the event loop is responding):
curl -s http://127.0.0.1:7777/healthz | jq

# Readiness (db + workspace + audit sink — what the watchdog probes):
curl -s http://127.0.0.1:7777/health/deep | jq

# The full UI:
open http://127.0.0.1:7777/
```

## Logs

Everything tees to `~/Library/Logs/Vector/`:

```bash
tail -f ~/Library/Logs/Vector/backend.err.log     # JSON log stream (default)
tail -f ~/Library/Logs/Vector/watchdog.err.log    # "probe failed (n/3)" lines
tail -f ~/Library/Logs/Vector/snapshot.err.log    # any sqlite3 .backup failures
```

Each backend log line carries a `trace_id` you can plug into:
```
curl http://127.0.0.1:7777/trace/<trace_id> | jq
```
to reconstruct the full chain (events + audit + routing rows).

## Tuning knobs

In `backend/.env`:

| Var | Default | What it does |
|---|---|---|
| `VECTOR_HOST` | `127.0.0.1` | Bind address. Change to `0.0.0.0` if you'll reach this from the MacBook (see Tailscale notes below). |
| `VECTOR_PORT` | `7777` | HTTP port. |
| `VECTOR_DAILY_BUDGET_USD` | `0` | Spend ceiling. `/costs` flags `over_budget_today` when exceeded; backend never auto-pauses. |
| `VECTOR_BACKUP_DIR` | `~/VectorBackups` | Where hourly snapshots land. Point at a USB mount for off-laptop backup. |
| `VECTOR_BACKUP_KEEP` | `48` | Number of snapshots to retain (oldest pruned). |
| `VECTOR_WATCHDOG_INTERVAL_S` | `30` | How often the watchdog probes `/health/deep`. |
| `VECTOR_WATCHDOG_FAIL_THRESHOLD` | `3` | Consecutive probe failures before SIGTERM. |
| `VECTOR_WATCHDOG_TIMEOUT_S` | `5` | Per-probe timeout (curl `--max-time`). |
| `VECTOR_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `VECTOR_LOG_FORMAT` | `json` | `plain` for local debugging. |

## Self-healing layers

| Failure | Recovery |
|---|---|
| Backend process crashes | launchd KeepAlive restarts (≥10s throttle) |
| Backend hangs (event loop frozen, deadlock) | Watchdog SIGTERMs after 3 failed probes; launchd restarts |
| SQLite file corrupt | `connect()` runs `integrity_check`; restores newest snapshot; exits loud if snapshot also bad |
| Backend OS-killed mid-run | Startup sweep flips queued/running rows to `interrupted` |
| Watchdog crashes | Its own plist has `KeepAlive=true`; launchd restarts it |
| Snapshot script crashes | launchd reschedules at the next hour boundary |
| Disk full | `audit.record`, `runs_store.upsert_from_summary`, snapshot write log warnings and skip — backend keeps serving |

## Smoke test

```bash
bash ops/smoke.sh
```

Runs against `http://127.0.0.1:7777` by default; checks every health endpoint and prints a summary. Override `VECTOR_BASE_URL` to test a remote (e.g. Tailscale) deploy.

## Uninstall

```bash
bash ops/uninstall-services.sh
```

Stops + removes all three plists. The venv, repo, database, and backups are left in place.

## Accessing from your MacBook

Two ways once the Mac mini is running these services:

**Loopback only (current default):** open `http://mac-mini.local:7777/` on the same Wi-Fi using mDNS. Plain HTTP, no encryption. Works at home.

**Tailscale (recommended for anywhere-access):**
1. `brew install tailscale` on both Macs and `tailscale up` (free for personal use)
2. Bump `VECTOR_HOST=0.0.0.0` in `backend/.env` and restart: `launchctl kickstart -k gui/$(id -u)/industries.stratus.vector.backend`
3. Set `VECTOR_BACKEND_BEARER` to a real secret (`openssl rand -hex 32`) — required when the backend listens outside loopback
4. From the MacBook, hit `http://<mac-mini-tailscale-name>:7777/`. The `isLocalBackend()` gate in the mobile UI already accepts `100.x.y.z` Tailscale addresses.

That's the full hosting story Phase 11 wires up; the Tailscale code-side changes still owe a separate commit (CORS list, Tauri CSP) which will be the next phase.
