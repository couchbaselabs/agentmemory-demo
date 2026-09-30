# Quickstart — from nothing to a running demo (macOS)

For when you need the demo running quickly, for example before a customer call, and
don't want to assemble the pieces by hand. It runs everything locally in Docker.
[`SETUP.md`](./SETUP.md) remains the reference for how the parts fit together and for
the manual and Streamlit options; [`TROUBLESHOOTING.md`](./TROUBLESHOOTING.md) covers
problems once it's running.

## What you need first

| Need | Get it |
|---|---|
| Docker Desktop (give it ≥ 6 GB RAM) | `brew install --cask docker`, then open it once |
| Python 3.12+ | `brew install python@3.14` (the macOS system `python3` is 3.9) |
| Node.js 18+ | `brew install node` |
| An OpenAI API key | your OpenAI account |
| The Agent Memory **server image** | download via the form linked from the [Agent Memory docs](https://docs.couchbase.com/ai/build/agent-memory/get-started-agent-mem.html); save `agentmemory-server-arm64-<version>.tar` (Apple Silicon) or `…-amd64-…` (Intel) in `~/Downloads` |

Not sure what's missing? Run `make doctor`. It checks everything and prints the exact
fix for each gap. It installs nothing.

## Run it

```bash
make demo
```

It asks for your OpenAI key once (input hidden, validated with OpenAI, stored in the
git-ignored `.env`) and locates the server image. Then it starts Couchbase and the
Agent Memory server, installs dependencies, seeds Alice, Bob and Charlie, and starts
the UI. Re-running is safe.

- Guest portal: <http://localhost:8502/guest> — Alice / Bob / Charlie, password `123`
- Ops portal: <http://localhost:8502/ops> — sign in by role, password `ops`

## The same thing, step by step

| Command | Does |
|---|---|
| `make configure` | creates `.env`, asks for the OpenAI key, finds the server image |
| `make doctor` | preflight for the list above, plus ports |
| `make backend` | starts Couchbase (initialises cluster and bucket) and the Agent Memory server, waits for `/health` |
| `make setup` | `.venv`, Python dependencies, UI build |
| `make seed` | loads the demo guests, then waits until they're searchable (no guessing at "30–60 seconds") |
| `make up` | starts the demo API (:8001) and UI (:8502) in the background |
| `make smoke` | calls the API through the UI proxy |

`make help` lists everything else (`status`, `logs`, `down`, `streamlit`, …).

## Stop, restart, start over

```bash
make down              # stop the demo API and UI
make backend-down      # stop Couchbase and the memory server (data kept)
make backend           # bring them back
make backend-destroy   # DELETE all local Couchbase data (asks first)
```

Ports used: memory server 8080, Couchbase console 8091 (`Administrator` /
`demo-password`, local only), demo API 8001, UI 8502. Everything listens on
`127.0.0.1` only, so nothing is exposed to your network. Logs for the demo
processes are in `.run/`.

## If it doesn't work

| Symptom | Fix |
|---|---|
| `make up` says the Agent Memory server isn't reachable (or the UI says "Cannot reach the backend server") | the memory server or Docker is down, often after quitting Docker Desktop. The message names the cause; usually `open -a Docker`, then `make backend` |
| `Docker isn't running` | `open -a Docker`, wait until it says running, retry |
| Memory server exits: `Embedding model health check failed: unauthorized` | OpenAI rejected the key. `make configure`, then `make backend` |
| `Agent Memory server image not found` | download it (see above) into `~/Downloads`, or run `make configure` and give it the path. It must match your CPU |
| Port 8080 or 8091 already in use | another container or app holds it (an older Agent Memory or Couchbase, say). `lsof -nP -iTCP:8080 -sTCP:LISTEN` shows which; stop it and re-run |
| Empty results right after seeding | `make wait-indexed` |
| Anything else | `make backend-status`, `docker logs agentmem-server`, `make logs` |

## Notes

- The Agent Memory server is started with authentication off (`OIDC_AUTH_ENABLED=false`)
  because the demo's client doesn't send a token. This is for local use only.
- The image tag inside the downloaded tarball is `agentmemory-server:v1.0.0`; the
  scripts read it from the file, so a different version works without edits.
