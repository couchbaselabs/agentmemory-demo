# Setup Guide — Couchbase Agent Memory Hotel (from scratch)

This is a step-by-step, from-nothing guide to running the hotel demo locally. It
documents what the code **actually** requires (which differs from the top-level
`README.md` in a few places — see [Notes on the README](#notes-on-the-readme) at
the bottom).

If something goes wrong, see [`TROUBLESHOOTING.md`](./TROUBLESHOOTING.md) — every
issue listed there is one that can actually happen with these exact steps.

---

## 0. How the pieces fit together

```
                    ┌─────────────────────────────┐
   Guest / Ops  ──► │  UI layer                    │
   browser          │  • Streamlit apps  (8501/850x)│
                    │  • Next.js UI      (8502)     │──┐  proxies /api/* 
                    └─────────────────────────────┘  │  to FastAPI
                            │ imports                 ▼
                    ┌─────────────────────────────┐  ┌──────────────────┐
                    │  agents/ + LangGraph         │  │ FastAPI backend  │
                    │  (this repo)                 │◄─┤ hotel_server.py  │
                    │  • calls OpenAI (LLM)        │  │ (8001)           │
                    │  • calls agentmemory SDK     │  └──────────────────┘
                    └──────────────┬──────────────┘
                                   │ HTTP (AGENTMEM_BASE_URL)
                                   ▼
                    ┌─────────────────────────────┐
                    │  Couchbase Agent Memory      │
                    │  service   (localhost:8080)  │  ◄── this is a SEPARATE service
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────┐
                    │  Couchbase cluster           │  (Capella or self-hosted)
                    └─────────────────────────────┘
```

Key point that the README glosses over: **this demo is only a client.** It does
not talk to Couchbase directly and it does not embed the memory engine. It makes
HTTP calls to a running **Couchbase Agent Memory service** (default
`http://localhost:8080`). That service is what owns the Couchbase connection,
embeddings, and fact extraction.

So the demo needs exactly three things at runtime:

| Dependency | Why | How the demo reaches it |
|---|---|---|
| A running Agent Memory service | stores/retrieves memory | `AGENTMEM_BASE_URL` |
| An OpenAI API key | the 8 agents call an LLM | `OPENAI_API_KEY` (read by `langchain-openai`) |
| Python + (for the React UI) Node | to run the apps | local toolchain |

---

## 1. Prerequisites

These must already be in place — this guide does **not** cover installing the SDK
or standing up the memory server; they are assumed to exist.

- **A running Couchbase Agent Memory server**, reachable at `AGENTMEM_BASE_URL`
  (default `http://localhost:8080`).
- **A Couchbase backend** (Capella or self-hosted cluster) behind that server.
- **The `agentmemory` SDK installed in the same environment you run the demo from**
  (PyPI: `couchbase-agent-memory`). If you use a venv (step 2), the SDK must be
  installed *inside that venv* — a system-wide install won't be visible to it.
- **Python 3.12+** — 3.14 is known-good. (If your Homebrew `python@3.12` is
  broken with a `pyexpat` / `libexpat` error, see Troubleshooting; use 3.14.)
- **Node.js 18+ and npm** — only needed for the Next.js UI (Option B).
- **An OpenAI API key.**

Confirm the toolchain and the memory server (the SDK is verified in step 2, once
the venv exists):

```bash
python3 --version                     # >= 3.12
node --version                        # >= 18   (Option B only)
curl -s http://localhost:8080/health  # {"status":"healthy",...}
```

> Server-side configuration (Couchbase connection string, bucket, credentials,
> embedding/LLM models) belongs to the memory **server**, not to this demo. The
> demo never reads those variables — see the env table in step 3.

---

## 2. Python environment

Create a virtual environment and install the demo's dependencies, then confirm the
SDK prerequisite is importable **from this env**:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

# the agentmemory SDK is a prerequisite — verify it's available in this venv
python -c "from agentmemory import AgentMemoryClient; print('SDK ok')"
```

If that raises `ModuleNotFoundError`, the SDK isn't installed in this venv — install
it here before continuing (see Troubleshooting).

---

## 3. Environment variables (`.env`)

```bash
cp .env.example .env
```

The shipped `.env.example` lists more variables than the demo actually uses. Here
is what is **really** read by the code:

| Variable | Required? | Used by | Notes |
|---|---|---|---|
| `OPENAI_API_KEY` | **Yes** | `langchain-openai` (all agents) | LLM calls fail without it |
| `AGENTMEM_BASE_URL` | Recommended | the SDK client | defaults to `http://localhost:8080` |
| `MODEL` | Optional | all agents | defaults to `gpt-4o-mini` |
| `AGENT_CATALOG_CONN_STRING` etc. | Optional | `agents/agentc_catalog.py` | only for agentc tracing; leave unset to disable |
| `COUCHBASE_HOST` / `COUCHBASE_USER` / `COUCHBASE_PASSWORD` / `COUCHBASE_BUCKET` | **No** | — | present in `.env.example` but **not read** by the demo; they are server-side |
| `TAVILY_API_KEY` | **No** | — | present in `.env.example` but **not used** anywhere |

A minimal working `.env`:

```env
OPENAI_API_KEY=sk-...
AGENTMEM_BASE_URL=http://localhost:8080
MODEL=gpt-4o-mini
```

---

## 4. Seed the demo data

```bash
python couchbase_setup.py --data data/hotel_demo.json
```

This creates three guest users — `alice_chen`, `bob_morrison`, `charlie_wu` —
with ~53 sessions and ~300 memory blocks. Expected tail:

```
✓ 308 memories ingested in ~38 seconds
[DONE] Setup complete.
```

> **After seeding, wait ~30–60s before expecting rich results.** The service
> indexes memory into its FTS vector index asynchronously. Immediately after
> seeding, agents that rely on search (profile, safety scan, digest) may return
> "no memories" until the index catches up. This is normal — see Troubleshooting.

---

## 5. Option A — Streamlit UI (simplest)

Two single-file apps, no build step. Run each in its own terminal (venv active,
`.env` sourced automatically by the app via `python-dotenv`):

```bash
# Terminal 1 — guest concierge portal
streamlit run agentmem_hotel.py --server.port 8501

# Terminal 2 — operations portal
streamlit run agentmem_hotel_ops.py --server.port 8503
```

- Guest portal: <http://localhost:8501> — sign in as Alice / Bob / Charlie,
  password **`123`**
- Ops portal: <http://localhost:8503> — sign in by role, password **`ops`** for
  all roles

> The README uses port **8502** for the ops Streamlit app, but 8502 is also the
> Next.js port (step 6). If you ever run both at once, give them different ports.
> This guide uses **8503** for ops Streamlit to avoid the clash.

When you edit anything under `agents/`, restart Streamlit — its hot-reload does
not pick up sub-package changes.

---

## 6. Option B — Next.js + FastAPI UI

This is a React frontend that calls a FastAPI backend over SSE.

### 7.1 Start the FastAPI backend (port 8001)

```bash
source .venv/bin/activate
set -a; source .env; set +a          # export env into the process
uvicorn hotel_server:app --host 127.0.0.1 --port 8001 --reload
```

Check it: `curl -s http://localhost:8001/health` → `{"status":"ok"}`.

### 7.2 Configure and run the frontend (port 8502)

```bash
cd hotel_ui
cp .env.local.example .env.local
printf 'NEXT_PUBLIC_API_URL=http://localhost:8001\n' > .env.local

npm install
npm run build      # production build
npm start          # serves on 8502 (npm run dev also works, with hot reload)
```

- Guest portal: <http://localhost:8502/guest>
- Ops portal: <http://localhost:8502/ops>

**How routing works (important):** the frontend calls its own `/api/*` path,
and `next.config.mjs` rewrites `/api/*` to the backend. The rewrite reads
`NEXT_PUBLIC_API_URL` (default `http://localhost:8001`):

```js
// next.config.mjs
const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
// source: '/api/:path*'  ->  destination: `${apiUrl}/:path*`
```

So the backend URL is set **at server start**, not baked into the client bundle.
If you change `NEXT_PUBLIC_API_URL`, restart `npm start` (a rebuild is not
strictly required for the rewrite, but restart the Node process).

> ⚠️ The stock branch shipped this rewrite hardcoded to `http://localhost:8502`
> (the UI's own port), which makes every `/api/*` call loop back to Next.js and
> return 404 HTML — logins silently do nothing. If you see that, confirm your
> `next.config.mjs` uses `NEXT_PUBLIC_API_URL` as above. See Troubleshooting.

### 6.3 About `start_server.sh` / `hotel_ui/start_ui.sh`

These are the **PM2/EC2** launchers. They resolve paths relative to themselves, so
they run from any checkout. Ports default to **8502** (backend) and **8501** (UI);
override with `PORT` / `UI_PORT`. For everyday local development you can also just
use the `uvicorn` and `npm` commands above.

---

## 7. Verify everything works

Quick backend smoke test (with the FastAPI server up on 8001):

```bash
curl -s http://localhost:8001/users | python3 -m json.tool          # 3 seeded guests
curl -s "http://localhost:8001/ops/safety-scan?force=true"          # allergy items (after index warmup)
curl -s http://localhost:8001/users/alice_chen/profile              # populated profile
```

In the browser:

1. **Guest chat** — log in as Alice, ask *"What coffee do I like and any
   allergies on file?"* You should get a reply referencing Blue Bottle coffee
   and a shellfish allergy, drawn from cross-session memory.
2. **Ops → Food Allergen Check** — pick Alice, enter a shellfish order, run it.
   You should get a **HIGH safety flag** citing a `block:<uuid>` as evidence.
3. **Ops → Pre-Arrival Briefings** — generate Alice's briefing; it should write
   to `role_front_desk` and show retrieval/LLM timings.

The eight agents (Concierge, ProfileOverview, Briefing, SafetyScan, Flag, Digest,
GroupEventBrief, CallNote) all share `agents/memory_toolkit.py` and
`agents/config.py`, so both UIs exercise the same logic.

---

## Gotchas worth remembering

The top-level `README.md` has been corrected to match this guide. These are the
points that trip people up most often — keep them in mind:

1. **The `agentmemory` SDK is a prerequisite** (PyPI `couchbase-agent-memory`) —
   make sure it's installed in the same environment you run the demo in.
2. **Only three env vars matter to the demo:** `OPENAI_API_KEY` (required),
   `AGENTMEM_BASE_URL`, and `MODEL`. The `COUCHBASE_*` and `TAVILY_API_KEY` entries
   in `.env.example` are server-side or unused — the demo never reads them.
3. **Next.js proxy port.** The frontend reaches the backend via a `/api/*` rewrite
   driven by `NEXT_PUBLIC_API_URL`. If it points at the UI's own port, every API
   call 404s and logins silently fail. See Troubleshooting.
4. **Port clash.** Streamlit ops and the Next.js UI both default to 8502 — run the
   Streamlit ops app on a different port (e.g. 8503) if you run them together.
5. **`start_server.sh` / `start_ui.sh`** contain hardcoded EC2 paths; edit them for
   your host, or ignore them locally and use the `uvicorn` / `npm` commands above.
