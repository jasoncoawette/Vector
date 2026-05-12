# Vector — Brand Guidelines

> Design like Apple. Reason like an analyst.

---

## 01. Manifesto

Vector is the quietest tool in the room. It does not announce, it does not perform. It listens, anticipates, and shows you only the next move — phrased so plainly that you mistake it for your own thought.

If the interface is talking, it earned the airtime.

---

## 02. Principles

| # | Principle | What it means |
|---|---|---|
| 01 | **Quiet by default** | No emoji, no chatter, no celebration. The system never congratulates the user. |
| 02 | **Adapt to context** | Surfaces, density, and accent shift with the task. Focus mode hides everything but one thing. |
| 03 | **Phosphor for state** | The pale-blue accent (`--vec`) is reserved for *live state*, *focus*, and *the assistant's own voice.* Color is a privilege, not decoration. |
| 04 | **Mono for telemetry** | Mono signals "this came from a machine." Sans is for thought, narration, copy. |
| 05 | **No drama** | No gradient washes, no drop-shadow theatre, no glowing borders. Hairlines, weight, and space do the work. |
| 06 | **Show the source** | Every claim anchors to a source, timestamp, or sensor. Show your work like an analyst. |

---

## 03. Voice

Calm. Specific. Never cheerful. Tell the truth in one breath, then offer the next move.

### Say

> "Pricing v4 is with legal. Reply expected by 11."
> "Sleep was 5h 12m. I held your morning calls until 9:30."
> "Mira moved the 3:00 to Thursday."

### Don't say

> ~~"Great news! Your pricing draft is ready! ✨"~~
> ~~"You only slept 5 hours, you should rest more!"~~
> ~~"Hey Nia! Just a heads up, Mira had to reschedule…"~~

Rules of thumb:
- **One sentence per fact.** Sentences are statements, not warm-ups.
- **No hedges.** "I think," "perhaps," "maybe" — strip them.
- **No exclamations.** Ever.
- **Time and source first.** "21:48 · Mira:" beats "Mira just messaged you!"

---

## 04. Mark

The Vector mark is a single arrow inscribed in two thin rings — magnitude (length) and direction (arrowhead) on a closed orbit.

**Usage**
- Always reserve **clearspace = ½ mark height** on every side.
- Render in `currentColor` for the arrow and a single accent (`--vec`) for the apex dot.
- Minimum size: **16 px** on screen, **8 mm** in print.
- Never recolor the mark; never rotate it; never place it on a busy photographic background.

**Backgrounds (preferred order)**
1. `--bg-0` graphite void (primary)
2. `--bg-3` raised graphite
3. Solid `--ink-0` (rare, action contexts)
4. Solid `--vec` (calls-to-action only)

---

## 05. Type

| Role | Family | Weight | Tracking |
|---|---|---|---|
| Display | Inter Tight | 300 | -0.045em |
| Headline | Inter Tight | 400 | -0.025em |
| Title | Inter Tight | 500 | -0.015em |
| Body | Inter Tight | 400 | 0 |
| Caption | Inter Tight | 400 | 0 |
| Telemetry | JetBrains Mono | 500 | 0.02em |
| Label | JetBrains Mono | 500 | 0.24em (caps) |

---

## 06. Color

Five surfaces of warm graphite. Four inks. One reserved accent. Signal colors stay locked to function.

| Token | Hex | Use |
|---|---|---|
| `--vec` | `#b8d8ff` | **Reserved.** Live state, focus, assistant voice, primary CTA. |
| `--ok` | `#6fb38a` | System is nominal. |
| `--warn` | `#e2b170` | Attention required, not yet critical. |
| `--crit` | `#d97a7a` | Something is genuinely on fire. |
| `--gold` | `#c9bb88` | Scheduled / pending. |
| `--mag` | `#a78fc4` | Context / contextual reference. |

**Accent ratio rule:** ≤ 8% of accent area per screen, ≤ 3 simultaneous live indicators. If you're hitting the cap, the screen is shouting.

---

## 07. Motion

- Default ease: `cubic-bezier(0.2, 0.8, 0.2, 1)` ("Apple ease")
- Default duration: **180 ms** for state changes, **320 ms** for surface transitions.
- Backgrounds (particle field, drifting grid, radar sweep) move at <0.2 px/frame — should feel like ambient HVAC, not a screensaver.
- Pulse/breathing animations: 2-second cycle minimum, 60% → 100% opacity range.

---

## 08. Naming

- **Vector** is the assistant. Capital V.
- The user is "you," never "user."
- Agents are lowercase, named with one word each: `scribe`, `watcher`, `broker`.
- Skills are present-tense verbs: `triage`, `draft`, `schedule`, `recall`.

---

## 09. Don't

- ❌ Drop shadows used to imply elevation. Use a hairline border.
- ❌ Emoji. Anywhere.
- ❌ Gradient backgrounds that imply photography or weather.
- ❌ "Glassmorphism" except as a single OS layer (the top status bar).
- ❌ Personifying Vector ("I'm so excited to help!").
- ❌ Animating the wordmark.
- ❌ Inventing new colors. The palette is the palette.
