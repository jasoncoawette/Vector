# Vector — Test Plan

**Version:** 0.1
**Scope:** All features in PRD.md
**Strategy:** Build the test list first, then walk through it phase by phase. Each phase ends with a cleanup pass and a security pass.

---

## 0. Test Layers

| Layer       | Tool                     | Lives in                      |
| ----------- | ------------------------ | ----------------------------- |
| Unit (py)   | pytest                   | `backend/tests/unit/`         |
| Unit (ts)   | vitest                   | `frontend/src/**/*.test.ts`   |
| Integration | pytest + httpx           | `backend/tests/integration/`  |
| E2E         | Playwright               | `e2e/`                        |
| Manual      | checklist                | `docs/manual-checks.md`       |

Naming: `test_<unit>_<behavior>` for py, `<unit>.test.ts` for ts.

Coverage target: 70% lines on backend core, 60% on frontend stores. Voice pipeline is integration-tested, not unit-tested.

---

## 1. Frontend Tests (SvelteKit + Three.js)

### 1.1 Orb Component

- renders a canvas
- mounts a Three.js scene on first paint
- disposes scene on unmount (no leak)
- changes color on state prop (idle/listen/think/speak/error)
- mouth-shape map updates on viseme input
- drag to reposition persists to localStorage
- "pin on top" toggle calls Tauri window API
- click triggers mute action

### 1.2 State Store

- voice state machine transitions: idle -> listen -> think -> speak -> idle
- error state is reachable from any other state
- barge-in: speak -> listen on mic activity
- mute blocks transitions to listen

### 1.3 Metrics Dashboard

- /metrics route renders five sections
- empty metrics show "no data yet"
- a metric write updates the chart within 1s
- mission metrics flag stale data over 7 days old

### 1.4 Mobile (`/m` route)

- renders single-column under 768px
- all touch targets at least 44x44px (computed style assert)
- shows picks, brief, agents tail, top metrics, audit tail
- PTT button toggles listen state on touchstart/touchend
- backend unreachable: shows last-cached payload with stale banner
- stale cache over 24h: action buttons hidden
- network guard refuses POST when host is public IP (mock)

---

## 2. Backend Tests (FastAPI)

### 2.1 Health + Config

- GET /healthz returns 200 with build hash
- GET /config returns redacted config (no secrets)
- POST /config with missing auth returns 401

### 2.2 Voice Endpoints

- POST /voice/turn accepts audio chunk, returns turn-id
- WS /voice/stream pushes TTS audio frames
- WS /voice/stream closes cleanly on client disconnect
- a turn that exceeds 30s aborts and logs

### 2.3 Brain

- plan() returns a tool-call or a final message
- tool-call schema is validated; invalid tool name rejected
- loop detection: 5 identical tool calls aborts the turn
- token cost over threshold pauses and emits ask-user event

### 2.4 Tools (MCP)

- file.read inside scope succeeds
- file.read outside scope returns 403
- file.write outside scope requires confirm token
- file.delete requires two-step confirm
- linear.list returns cached state when API is down
- gmail.send requires explicit user-confirm event
- browser.fetch on safe-list site succeeds
- browser.fetch off safe-list returns ask-user

### 2.5 Daily Engine

- pick_top_three() returns exactly 3 items
- pick_top_three() biases toward outcome tags
- override learning: swapping top-3 shifts weight on the swapped class
- morning brief renders all three with reasons under 60s of audio
- mid-day re-rank flips order when a task was completed

### 2.6 Sub-Agents

- spawn creates a queue entry
- max 3 concurrent agents enforced
- a failed agent runs the fallback path once
- cost over $1 pauses and asks
- two agents on same file are serialized

### 2.7 Memory

- working-memory rows written within current day
- vector-store recall pulls top-k relevant entries
- override events update picker weights table
- weekly export produces an encrypted file

---

## 3. Integration Tests

- mic chunk in -> STT -> brain -> TTS audio out, total latency under 800ms (mocked LLM)
- wake-word "Vector" opens a turn; "Vector stop" kills it
- Linear API down -> brief still ships from cache
- ElevenLabs down -> Piper fallback engages
- Crash mid-action: replay log restores last state on restart

---

## 4. Security Tests

- ITAR-tagged file never sent to cloud (proxy unit-test)
- ~/.ssh and macOS keychain reads are hard-blocked
- shell-run requires dry-run preview
- SQLite at rest is encrypted (read raw file, assert no plaintext key strings)
- audit log records every tool call with caller, args, result hash
- API keys are read from Keychain, never logged
- a symlink that points outside scope is refused
- send-money intents always hit hard-stop ask path

---

## 5. E2E Smoke (Playwright)

- launch app -> orb visible
- click orb -> mute icon shown
- /metrics loads
- mock voice turn -> orb cycles colors idle -> listen -> think -> speak -> idle
- "Good morning Jason" trigger plays audio (mocked TTS asserts call)

---

## 6. Manual Checks

- real mic test on macOS
- real ElevenLabs voice in quiet + noisy room
- wake word with TV playing in background
- two voices in the room
- 7-day uptime: no leak, no crash, audit log size under 50MB

---

## 7. Test Order (matches roadmap)

1. Phase 1: 1.1, 1.2, 2.1, 2.2, integration latency
2. Phase 2: 2.4 (tools)
3. Phase 3: 2.5 (daily engine), 1.3 (metrics)
4. Phase 4: 2.6 (sub-agents)
5. Phase 5: 2.4 browser, 2.7 memory, integration crash recovery
6. Phase 6: mission metrics in 1.3, manual checks

Each phase ends with: redundant-code sweep + section 4 security pass.

---

*End of test plan v0.1.*
