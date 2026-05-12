# Vector — Product Requirements Doc

**Owner:** Jason
**Version:** 0.1 (draft)
**Date:** May 2026

---

## 1. Name

**Vector.**

Tagline: *Your path to the win.*

Why the name works:

- Two clean syllables. Safe for voice wake.
- Vector means direction and speed. Fits the mission.
- Math and AI vibe. Fits Stratus.
- Military vibe (vector in on target). Fits the Kill Chain ethos.

Backup names: Praetor. Aegis. Helm. Atlas.

---

## 2. Mission

Help Jason ship Stratus Industries to a multibillion dollar outcome.

The end goal: help the US beat China in the AI race by raising US military compute.

Vector keeps Jason on the highest leverage path each day.

---

## 3. Product Vision

Vector is a local voice-first AI agent. It lives on Jason's laptop.

It speaks. It listens. A 3D avatar sits on the screen. It reads files. It runs tasks. It manages sub-agents. It tracks the metrics that matter.

Each morning Vector tells Jason the top three tasks for the day. It pulls from Linear and calendar and goals. It pushes back when Jason drifts.

---

## 4. User

Single user: Jason.

- Age 21
- Solo founder of Stratus Industries
- Day job at Boeing in cloud and AI
- Stratus block: 5:00–7:15am
- Wants leverage not busywork
- Reads The Kill Chain. Thinks in chains.

---

## 5. Goals

- Cut decision load to near zero in the morning block.
- Surface the three top tasks each day.
- Track Stratus metrics in one place.
- Run sub-agents for code and research and writing.
- Replace half of Jason's tab switching.
- Keep ITAR data on the laptop.

---

## 6. Non-Goals

- Not a chat buddy. No small talk loop.
- Not a calendar app. It writes to calendar but does not own it.
- Not a code editor. It calls Cursor or Claude Code for edits.
- Not a CRM. It pulls from CRM but does not own it.
- Not a Boeing tool. Vector serves Stratus.
- Not a public product. Single user build for now.

---

## 7. Core Features

### 7.1 Voice Interface

- Wake word: "Vector"
- Speech in: local Whisper or Deepgram
- Speech out: ElevenLabs
- Push to talk fallback
- Mute toggle
- Barge-in support (Jason can cut Vector off mid sentence)

### 7.2 3D Avatar UI

Stack: SvelteKit + Three.js.

- Orb or low-poly face in the center of the screen
- Mouth shape syncs to voice output
- Color states: idle (blue), listen (green), think (yellow), speak (white), error (red)
- Drag to move on screen
- Pin on top toggle
- Click to mute

### 7.3 Daily Priority Engine

- Pulls open Linear issues at 4:55am
- Reads Stratus roadmap doc
- Checks calendar for the day
- Picks 3 tasks with a reason for each
- Reads them out at 5:00am wake
- Re-ranks at the mid-day check

### 7.4 Task Management

- Read and write to Linear
- Read and write to Apple Reminders
- Sprint check on two week scope
- Outcome vs process tags
- Daily review at end of block
- Weekly review on Sunday

### 7.5 Metrics System

See section 13.

### 7.6 File System Access

- Read any file in /Users/jason
- Write to a scoped workspace folder
- Confirm step for any write outside scope
- No delete without a two step ok
- Audit log for every read and write

### 7.7 Browser Control

- Open URLs in a side window
- Read page text via headless mode
- Fill forms with confirm step
- Pull data from a safe list of sites (GitHub. Linear. Gmail. SAM.gov. AFWERX. DSIP.)

### 7.8 Sub-Agent Management

- Spawn Claude or local model agents for sub-tasks
- Three agent types: code, research, writer
- Vector owns the queue
- Vector reports results back by voice
- Cap on parallel agents (default 3)

### 7.9 Mobile Web Companion

A phone-first read-and-act view for testing Vector away from the laptop.

- Same SvelteKit app, served at `/m`
- Phone-first layout. Breakpoint at 768px. Touch targets ≥ 44px.
- Read: today's picks, morning brief, agent status, top-line metrics, audit log tail
- Act: push-to-talk, spawn a sub-agent, mark a pick shipped, log a metric value
- Push-to-talk only (no wake word on mobile)
- Connects to the laptop backend over local network (Tailscale or LAN). No public exposure.
- Same bearer-token gate as `POST /config` for any mutation.
- Read-only fallback if the backend is unreachable: last cached payloads from localStorage.

Why: lets Jason check Vector during commutes and meetings. Lets the build be tested on a phone without a Tauri shell on iOS.

---

## 8. Architecture

### 8.1 High Level Diagram

```
[Mic] -> [STT] -> [Orchestrator] -> [LLM Brain] -> [Tools] -> [TTS] -> [Speaker]
                       |                              |
                       v                              v
                   [3D UI]                       [Sub-Agents]
                       |                              |
                       v                              v
                   [State Store]                 [External APIs]
```

### 8.2 Parts

- **Frontend:** SvelteKit + Three.js avatar (port 5173 in dev)
- **Desktop shell:** Tauri (smaller than Electron)
- **Backend:** Python FastAPI service on port 7777
- **STT:** Whisper local (whisper.cpp) or Deepgram cloud
- **TTS:** ElevenLabs streaming
- **Brain:** Claude Sonnet 4.6 for hot path. Claude Opus 4.7 for hard plans.
- **Tools:** Custom MCP servers for Linear and Gmail and files and browser
- **State:** SQLite (encrypted at rest)
- **Memory:** Chroma or LanceDB for long-term recall
- **Browser:** Playwright

---

## 9. Voice Pipeline

1. Mic stream feeds STT.
2. Wake word fires. Open turn.
3. Speech chunks stream to brain.
4. Brain plans. Calls tools as needed.
5. Brain streams tokens to TTS.
6. TTS streams audio to speaker.
7. Avatar mouth syncs to audio.
8. End of turn. Back to listen.

Target latency from end of speech to first audio out: under 800ms.

---

## 10. Agent Loop

```
plan -> act -> observe -> reflect -> next
```

- **Plan:** Pick the top action for the goal.
- **Act:** Call a tool or a sub-agent.
- **Observe:** Read the result.
- **Reflect:** Did this move us forward?
- **Next:** Queue the follow-up or close the loop.

A turn ends when the reflect step says the goal is met or blocked.

---

## 11. Daily Workflow

| Time        | Action                                                             |
| ----------- | ------------------------------------------------------------------ |
| 4:55am      | Vector wakes. Pulls Linear and calendar. Picks top 3.              |
| 5:00am      | Voice brief to Jason. Three tasks. Why each one. Time blocks.      |
| 5:00–7:15am | Stratus block. Vector runs sub-agents on side tasks. Reports back. |
| 7:15am      | Hand off. Vector logs the block. Sets Boeing day reminders.        |
| 12:30pm     | Mid-day check. Adjust if blocked.                                  |
| 8:30pm     | Daily review. Shipped vs slipped. Notes for tomorrow.              |
| Sun 4pm     | Weekly review. Sprint health. Metric trend lines. Next two weeks.  |

---

## 12. Memory Model

Three layers:

1. **Hot context** — current turn, last 10 minutes. In LLM context window.
2. **Working memory** — current day. SQLite rows.
3. **Long-term memory** — vector store. Pulled on demand.

What Vector remembers:

- Every task picked and shipped
- Every metric value over time
- Every voice command and outcome
- Jason's overrides (when he picks a different top 3)
- Sub-agent runs and cost

Vector learns from overrides. When Jason swaps the top 3, Vector logs the swap and shifts the picker weights.

---

## 13. Metrics System

### 13.1 Stratus Top Line

- Revenue this month
- Pilot count
- LOIs signed
- AFWERX SBIR phase
- Burn rate
- Runway in months

### 13.2 Build Metrics

- CLI tool ship date
- Dashboard ship date
- ITAR audit status
- Anduril Lattice link status
- Test coverage %

### 13.3 Network Metrics

- DOD contacts added this week
- Calls booked
- Calls held
- Follow-ups open

### 13.4 Personal Metrics

- Morning block hit rate (target 6/7)
- Sleep hours
- Workout count
- Savings rate
- Linear sprint velocity

### 13.5 Mission Metrics (US vs China)

- US AI compute share trend
- China AI compute output trend
- Stratus share of US mil compute
- Top three US choke points this week

All metrics live in SQLite. Dashboard in SvelteKit at /metrics. Vector reads them on voice request.

---

## 14. Edge Cases

### 14.1 Voice

- Background noise: fall back to push to talk.
- Two voices at once: pause. Ask who is speaking.
- Mic blocked: switch to text input.
- ElevenLabs down: switch to local TTS (Piper).
- Wake word false trigger: silence for 2 seconds returns Vector to idle.

### 14.2 LLM Brain

- API timeout: retry with backoff. Cap at 3.
- Rate limit: queue and warn Jason.
- Bad tool call: validate schema. Reject.
- Loop detection: cap at 5 same calls in a row.
- Token cost spike: pause and ask Jason.
- Bad plan: Jason says "stop" to abort.

### 14.3 File System

- Path outside scope: deny with a reason.
- Large file (over 50MB): summary mode.
- Binary file: skip with a note.
- Permission error: ask Jason to grant.
- Symlink out of scope: refuse.

### 14.4 Browser

- Login wall: stop. Ask Jason.
- Captcha: stop. Hand off.
- Form with money or send action: hard confirm step.
- 2FA prompt: hand off to Jason.
- Site not on safe list: ask before fetch.

### 14.5 Sub-Agents

- Sub-agent fails: log and try one fallback path.
- Sub-agent runs long (over 10 min): check-in prompt.
- Two sub-agents touch same file: queue not parallel.
- Sub-agent cost over $1 per run: pause and ask.
- Sub-agent goes off topic: kill and restart with tighter scope.

### 14.6 Data Sync

- Linear API down: cache last state. Mark stale.
- Conflict between cache and remote: remote wins.
- Lost network: queue actions. Run on reconnect.
- Calendar event moved by phone: poll every 5 min.

### 14.7 Safety

- Send email: ask first.
- Push to public Linear project: ask first.
- Spend money: hard stop. Ask Jason.
- Delete file: two step confirm.
- Run shell: dry run first. Then ask.
- Touch ~/.ssh or keychain: full block.

### 14.8 Mission Drift

- Boeing task in queue: tag and defer to lunch.
- Low leverage task on top: Vector pushes back with reason.
- Vector picks wrong top 3: Jason says swap. Vector learns.
- Jason in a rabbit hole: Vector nudges at 90 min mark.

### 14.9 Privacy

- ITAR content: never leaves the laptop.
- Personal docs: never leave the laptop.
- Public docs: cloud LLM ok.
- Stratus IP: never leaves the laptop.
- Boeing data: never touched.

### 14.10 Crash Recovery

- Backend crash: restart from SQLite state.
- Frontend crash: reconnect to backend.
- Mid-action crash: replay log up to last commit.
- ElevenLabs mid-stream cut: speak last clean sentence and stop.

### 14.11 Wellbeing

- Jason awake past 11pm: Vector flags sleep risk.
- Three days in a row missed block: Vector asks why.
- Negative self-talk in voice input: Vector reads the 4 principles back.

### 14.12 Mobile

- Backend unreachable: show cached last-good payload with a stale banner.
- Stale cache over 24h: read-only mode, hide action buttons.
- PTT release without speech: silent no-op, no turn opened.
- Phone locks mid-stream: drop the turn; let the next tap start a new one.
- Mobile on public Wi-Fi: refuse mutation if backend host is not loopback or Tailscale CGNAT range.

---

## 15. Security and Privacy

- All ITAR data stays local. No cloud LLM for ITAR.
- API keys in macOS Keychain.
- SQLite encrypted at rest with FileVault plus per-row crypto for secrets.
- Audit log for every tool call. Jason can read it from a UI tab.
- Kill switch: voice phrase ("Vector stop") plus a hot key combo.
- All cloud calls go through a single proxy module. Easy to swap or block.
- Weekly export of state to an encrypted backup on a USB drive.

---

## 16. Roadmap

### Phase 1: Voice Loop (Weeks 1–2)

- SvelteKit shell with Three.js orb
- Mic in. Whisper STT.
- Claude brain wired up
- ElevenLabs TTS streaming
- Wake word "Vector" via Picovoice

### Phase 2: Tools (Weeks 3–4)

- File read and write MCP
- Linear MCP
- Gmail MCP
- Calendar MCP
- Apple Reminders MCP

### Phase 3: Daily Engine (Weeks 5–6)

- Priority pick logic
- Morning brief
- Daily review
- Metrics dashboard v1

### Phase 4: Sub-Agents (Weeks 7–8)

- Code agent (Claude Code wrap)
- Research agent (web + read)
- Writer agent (drafts)
- Queue and report back

### Phase 5: Polish (Weeks 9–10)

- Browser control via Playwright
- Long-term memory (Chroma)
- Crash recovery
- Audit log UI

### Phase 6: Mission Layer (Weeks 11–12)

- US vs China compute metrics
- Stratus share dashboard
- Weekly mission brief

---

## 17. Success Metrics

Vector wins when:

- Jason hits the 5:00–7:15am block 6 of 7 days a week.
- Top 3 tasks ship 5 of 7 days.
- Sprint velocity in Linear goes up 30% in 90 days.
- Tab switches per day drop by half.
- Stratus revenue grows month over month.
- Jason says he trusts Vector to pick the next task.

Vector fails when:

- Jason turns it off for more than 2 days.
- Vector picks busywork over leverage.
- A safety rule breaks once.
- ITAR data leaves the laptop.

---

## 18. Open Questions

- Local LLM vs Claude API for the brain? Cost vs privacy trade.
- Tauri vs Electron for shell? Tauri is smaller. Electron has more libs.
- Custom MCP servers or off the shelf? Build core ones. Use rest from registry.
- How much should Vector talk vs show? Set a ratio in user prefs.
- Wake word lib: Picovoice vs open source (openWakeWord)?
- Should the avatar be a face or an orb? Orb ships faster. Face is more fun.
- One brain or split (planner + executor)? Split is safer. One is simpler.

---

## 19. First Build Steps (Week 1)

1. Spin up SvelteKit app. Add Three.js orb.
2. Wire Tauri shell.
3. Add a FastAPI backend on 7777.
4. Test ElevenLabs streaming with a hard coded prompt.
5. Add Whisper local STT.
6. Add Claude API call as the brain.
7. Make Vector say "Good morning Jason" on voice trigger.

Ship that loop. Then add tools.

---

*End of PRD v0.1.*
