# Vector

Local voice-first AI agent for Stratus Industries.

See `PRD.md` for the product spec and `TESTS.md` for the test plan.

## Layout

```
frontend/    SvelteKit + Three.js orb UI (Vitest)
backend/     FastAPI service on :7777 (pytest)
desktop/     Tauri shell (Rust)
```

## Dev

Backend:

```
cd backend
pip install -e .[dev]
python -m vector       # serves on http://127.0.0.1:7777
pytest                  # runs tests
```

Frontend (pnpm — `brew install pnpm` if you don't have it):

```
cd frontend
pnpm install
pnpm dev                # http://127.0.0.1:5173
pnpm test               # vitest
```

Desktop shell (after frontend builds):

```
cd desktop
cargo tauri dev
```

## Build status

Phase 1 — Voice Loop scaffolding in progress. See `PRD.md` §16 for the roadmap and §19 for the week-1 build steps.
