# Troubleshooting

Concrete problems you can hit running this demo, each with the symptom, the
cause, and the fix. Most of these were observed during a real from-scratch setup.

Jump to:

- [Install & environment](#install--environment)
- [Connecting to the memory service](#connecting-to-the-memory-service)
- [Empty / missing memory results](#empty--missing-memory-results)
- [Next.js + FastAPI](#nextjs--fastapi)
- [Streamlit](#streamlit)
- [Quick diagnostic commands](#quick-diagnostic-commands)

---

## Install & environment

### `ModuleNotFoundError: No module named 'agentmemory'`

**Cause.** The `agentmemory` SDK (a prerequisite) isn't installed in the
environment you're running the demo from.

**Fix.**

```bash
pip install couchbase-agent-memory     # provides the `agentmemory` module
python -c "from agentmemory import AgentMemoryClient; print('ok')"
```

### `venv` creation fails with a `pyexpat` / `libexpat.1.dylib` error (macOS)

**Symptom.**

```
Symbol not found ... pyexpat ... Expected in: /usr/lib/libexpat.1.dylib
Command '[...ensurepip...]' returned non-zero exit status 1.
```

**Cause.** A broken Homebrew `python@3.12` build (mismatched system `libexpat`).
`ensurepip` can't run, so the venv has no pip.

**Fix.** Use a working interpreter. Python **3.14** was verified end-to-end here:

```bash
python3 --version               # if this is 3.14.x, just use it
python3 -c "import pyexpat, ssl; print('stdlib ok')"
python3 -m venv .venv
```

If you must stay on 3.12, reinstall it: `brew reinstall python@3.12` (and
`brew reinstall expat`).

### Binary wheels won't build / install on a very new Python

**Cause.** `pydantic-core`, `pandas`, etc. may not yet publish wheels for a
brand-new Python release.

**Fix.** Prefer a Python with published wheels (3.12–3.14 were fine here). Ensure
`pip` is current first: `python -m pip install --upgrade pip`.

### OpenAI auth errors (`401`, `invalid_api_key`) when an agent runs

**Cause.** `OPENAI_API_KEY` missing or not exported into the process. The agents
read it via `langchain-openai`, which looks at the environment.

**Fix.** Put it in `.env`, and make sure it's actually exported for the process
you run:

```bash
set -a; source .env; set +a
python -c "import os; print(bool(os.getenv('OPENAI_API_KEY')))"   # True
```

Streamlit apps load `.env` themselves via `python-dotenv`; `uvicorn` started from
a plain shell does **not** — export the env first (as above) or use `--env-file`.

---

## Connecting to the memory service

### `Connection refused` / timeouts to `localhost:8080`

**Cause.** The Couchbase Agent Memory **service** isn't running. This demo is only
a client; it can't work without the service.

**Fix.**

```bash
curl -s http://localhost:8080/health
```

- Healthy response → good; make sure `AGENTMEM_BASE_URL` matches.
- No response → start the Agent Memory service (see `SETUP.md` §2). It is a
  separate project from this demo.

### `NotFoundError: ... USER_NOT_FOUND ... alice_chen`

**Symptom.** The service is up, but users are missing.

**Cause.** Data hasn't been seeded (or was seeded into a different bucket than the
service is currently pointed at).

**Fix.**

```bash
python couchbase_setup.py --data data/hotel_demo.json
curl -s http://localhost:8080  # service reachable
```

Then confirm the three users exist via the backend: `curl -s http://localhost:8001/users`.

### SSL / certificate warnings

The clients are constructed with `verify=False` (see `AgentMemoryClient(..., verify=False)`),
which is intentional for local/self-signed setups. You may see an
`InsecureRequestWarning`; it's harmless locally. Do **not** rely on `verify=False`
in production.

---

## Empty / missing memory results

### Profile shows "No memories for user yet"; safety-scan / digest come back empty — right after seeding

**Symptom.** Immediately after `couchbase_setup.py`, `/users/<id>/profile`,
`/ops/safety-scan`, and `/ops/digest` return empty or "no memories", even though
seeding reported hundreds of blocks.

**Cause.** The service indexes memory into its FTS vector index **asynchronously**.
Search-based retrieval can't see blocks that aren't indexed yet. (A direct
`get_memory()` fetch works immediately, which is why raw session views populate
before search-driven agents do.)

**Fix.** Wait ~30–60 seconds after seeding, then retry. To confirm the data is
actually present (bypassing search):

```bash
python - <<'PY'
from agentmemory import AgentMemoryClient
c = AgentMemoryClient(base_url="http://localhost:8080", verify=False)
s = c.get_user(user_id="alice_chen").get_session(session_id="session_1")
print("blocks:", len(s.get_memory().memory_blocks))   # > 0 means data is there
PY
```

If direct fetch shows blocks but search stays empty for minutes, check the
service logs for FTS index build errors.

### Retrieval "works in one UI but not the other"

Both UIs call the same `agents/` code and the same service, so this is almost
always timing (index warmup) or a stale process. Restart the app that's behind
and retry after warmup.

---

## Next.js + FastAPI

### Login does nothing / Network tab shows `/api/...` returning 404 HTML

**Symptom.** Clicking Sign In on the Next.js portal does nothing; requests to
`/api/auth/login` (or any `/api/*`) return a Next.js 404 HTML page instead of
JSON.

**Cause.** The `/api/*` rewrite in `next.config.mjs` points at the wrong port.
The stock branch hardcoded `http://localhost:8502` — the Next.js server's **own**
port — so `/api/*` loops back into Next.js and 404s.

**Fix.** Make the rewrite target the FastAPI backend via `NEXT_PUBLIC_API_URL`:

```js
// hotel_ui/next.config.mjs
async rewrites() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
  return [{ source: '/api/:path*', destination: `${apiUrl}/:path*` }];
}
```

Set `hotel_ui/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8001
```

Restart `npm start`. Verify the proxy:

```bash
curl -s http://localhost:8502/api/health      # -> {"status":"ok"} (from FastAPI, not 404 HTML)
```

### `EADDRINUSE` / port already in use on 8502

**Cause.** Another process (a prior Next.js, or the Streamlit ops app if you put
it on 8502) holds the port.

**Fix.**

```bash
lsof -i :8502            # find the PID
kill <pid>
# or run Next.js elsewhere: npm start -- -p 3000  (and update NEXT_PUBLIC_API_URL consumers)
```

### `uvicorn: command not found` / the app imports but the server won't serve

Run uvicorn through the venv's Python so you use the right interpreter:

```bash
.venv/bin/python -m uvicorn hotel_server:app --host 127.0.0.1 --port 8001 --reload
```

### `start_server.sh` / `hotel_ui/start_ui.sh` — ports or environment

**Behaviour.** Both scripts resolve paths relative to themselves, so they run from
any checkout. `start_server.sh` loads `.env` and activates `.venv` if present, then
runs the backend on `PORT` (default **8502**). `start_ui.sh` runs the UI on
`UI_PORT` (default **8501**).

**Fixes.**

- Wrong port / collision → override: `PORT=8001 ./start_server.sh`,
  `UI_PORT=3000 ./start_ui.sh`.
- Backend can't find deps → make sure a `.venv` exists with requirements + the SDK
  installed (the script activates `.venv` automatically if present).
- For quick local dev you can skip the scripts and use the `uvicorn` / `npm`
  commands from `SETUP.md` §6.

### SSE agent responses never arrive in the UI

The ops agent endpoints stream Server-Sent Events encoded as
`data: {"type": "...", "data": ...}` (no `event:` line). If you're testing with a
custom client, parse the `type` field **inside** the JSON payload, not an SSE
`event:` header. In the browser this is handled for you.

---

## Streamlit

### Blank page or "Please wait..." forever

Check the terminal running `streamlit` for a Python traceback. Common causes:
missing `OPENAI_API_KEY`, service unreachable on `:8080`, or SDK not installed.

### Chat input is greyed out: "Viewing a previous session — start a New Chat"

Not a bug. You're viewing historical session in read-only mode. Click **New
Chat** in the sidebar to start a live conversation.

### Edits to `agents/` don't take effect

Streamlit's hot-reload doesn't pick up sub-package modules. Stop and restart the
`streamlit run ...` process after editing anything under `agents/`.

### Port collision between Streamlit ops and Next.js

Both default to 8502 in different places. Run the Streamlit ops app on a distinct
port, e.g. `--server.port 8503`.

---

## Quick diagnostic commands

```bash
# 1. Is the memory service up?
curl -s http://localhost:8080/health

# 2. Is the SDK importable in the venv?
.venv/bin/python -c "import agentmemory, sys; print(agentmemory.__file__)"

# 3. Are the demo users seeded?
.venv/bin/python -c "from agentmemory import AgentMemoryClient as C; \
  print([C(base_url='http://localhost:8080',verify=False).get_user(user_id=u).user_id \
  for u in ('alice_chen','bob_morrison','charlie_wu')])"

# 4. Is the FastAPI backend up and seeing users?
curl -s http://localhost:8001/health
curl -s http://localhost:8001/users | python3 -m json.tool

# 5. Is the Next.js proxy pointing at the backend (not itself)?
curl -s http://localhost:8502/api/health     # expect {"status":"ok"}, not HTML

# 6. What env does a process actually see?
.venv/bin/python -c "import os; [print(k, bool(os.getenv(k))) for k in \
  ('OPENAI_API_KEY','AGENTMEM_BASE_URL','MODEL')]"
```
