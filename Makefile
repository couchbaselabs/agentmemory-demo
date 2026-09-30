# Couchbase Agent Memory Hotel demo.
#
#   make demo      # everything: configure, local Couchbase + Agent Memory server,
#                  # deps, seed data, start the UI  (needs Docker; see `make doctor`)
#
# Or step by step:
#   make configure # OpenAI key + path to the downloaded server image (interactive)
#   make doctor    # preflight; prints exact fixes for anything missing
#   make backend   # local Couchbase + Agent Memory server in Docker
#   make setup     # venv, deps, UI build
#   make seed      # load Alice/Bob/Charlie and wait until searchable
#   make up        # start the API + UI  (make down / status / logs)

SHELL := /bin/bash
.DEFAULT_GOAL := help

# First Python >= 3.12 on PATH (system python3 on macOS is often 3.9). Override: make PYTHON=python3.14
PYTHON      ?= $(shell for p in python3.14 python3.13 python3.12 python3; do command -v $$p >/dev/null 2>&1 && $$p -c 'import sys; sys.exit(sys.version_info < (3,12))' 2>/dev/null && { echo $$p; break; }; done)
VENV        := .venv
BIN         := $(VENV)/bin
RUN_DIR     := .run
API_PORT    ?= 8001
UI_PORT     ?= 8502
STREAMLIT_GUEST_PORT ?= 8501
STREAMLIT_OPS_PORT   ?= 8503
# Read from .env when present, otherwise the documented default.
AGENTMEM_BASE_URL ?= $(shell grep -s '^AGENTMEM_BASE_URL=' .env | cut -d= -f2- | tr -d '"' || true)
AGENTMEM_BASE_URL := $(or $(AGENTMEM_BASE_URL),http://localhost:8080)

.PHONY: help demo configure doctor backend backend-down backend-status backend-destroy \
        setup check venv install env ui-install ui-build seed wait-indexed smoke up down restart status logs \
        api ui streamlit clean distclean

help: ## Show this help
	@awk 'BEGIN{FS=":.*## "} /^[a-zA-Z_-]+:.*## /{printf "  \033[36m%-12s\033[0m %s\n",$$1,$$2}' $(MAKEFILE_LIST)

# ─── One command ──────────────────────────────────────────────────────────

demo: ## Do everything: configure, backend, setup, seed, start the UI
	@$(MAKE) --no-print-directory configure
	@$(MAKE) --no-print-directory doctor
	@$(MAKE) --no-print-directory backend
	@$(MAKE) --no-print-directory setup
	@$(MAKE) --no-print-directory seed
	@$(MAKE) --no-print-directory up
	@$(MAKE) --no-print-directory smoke

configure: ## Set OpenAI key and locate the Agent Memory server image (interactive)
	@./scripts/configure.sh

doctor: ## Preflight: Docker, Python, Node, OpenAI key, server image, ports
	@./scripts/doctor.sh

# ─── Backend (local Couchbase + Agent Memory server, in Docker) ───────────

backend: ## Start local Couchbase + Agent Memory server (idempotent)
	@./scripts/backend.sh up

backend-down: ## Stop the backend containers (data is kept)
	@./scripts/backend.sh down

backend-status: ## Show backend container state and server health
	@./scripts/backend.sh status

backend-destroy: ## Delete the backend containers and ALL local Couchbase data
	@./scripts/backend.sh destroy

# ─── Setup ────────────────────────────────────────────────────────────────

setup: check venv install env ui-build ## One-time setup: venv, deps, .env, UI build
	@echo; echo "✓ Setup done. (Standalone? Next: make configure, make backend, make seed, make up — or just make demo.)"

check: ## Verify toolchain and (non-fatally) the memory server
	@test -n "$(PYTHON)" || { echo "✗ Need Python >= 3.12 (try: brew install python@3.14, or make PYTHON=/path/to/python)"; exit 1; }
	@echo "✓ python: $$($(PYTHON) --version)"
	@command -v node >/dev/null && node -e 'process.exit(+(process.versions.node.split(".")[0] < 18))' \
		&& echo "✓ node: $$(node --version)" || { echo "✗ Need Node.js >= 18 and npm"; exit 1; }
	@curl -fsS -m 3 $(AGENTMEM_BASE_URL)/health >/dev/null 2>&1 \
		&& echo "✓ memory server: $(AGENTMEM_BASE_URL)" \
		|| echo "! memory server not reachable at $(AGENTMEM_BASE_URL) (needed for seed/up, not for setup)"

$(BIN)/python:
	$(PYTHON) -m venv $(VENV)

venv: $(BIN)/python

install: venv ## Install Python deps and confirm the agentmemory SDK imports
	$(BIN)/python -m pip install --quiet --upgrade pip
	$(BIN)/python -m pip install --quiet -r requirements.txt
	@$(BIN)/python -c "from agentmemory import AgentMemoryClient" 2>/dev/null \
		|| { echo "✗ agentmemory SDK missing from $(VENV). Install it here: $(BIN)/pip install couchbase-agent-memory"; exit 1; }
	@echo "✓ agentmemory SDK importable"

env: ## Create .env and hotel_ui/.env.local from templates if absent
	@test -f .env || { cp .env.example .env; echo "• created .env — set OPENAI_API_KEY"; }
	@test -f hotel_ui/.env.local || { echo "NEXT_PUBLIC_API_URL=http://localhost:$(API_PORT)" > hotel_ui/.env.local; echo "• created hotel_ui/.env.local"; }

ui-install:
	cd hotel_ui && npm install --no-audit --no-fund

ui-build: env ui-install ## Install and build the Next.js UI
	cd hotel_ui && npm run build

# ─── Data ─────────────────────────────────────────────────────────────────

seed: wait-server ## Seed demo guests (idempotent) and wait until searchable
	set -a; . ./.env; set +a; $(BIN)/python couchbase_setup.py --data data/hotel_demo.json
	@$(MAKE) --no-print-directory wait-indexed

.PHONY: wait-server
wait-server:
	@set -a; . ./.env; set +a; $(BIN)/python scripts/wait_ready.py server || { echo "  Is the backend running? Try: make backend"; exit 1; }

wait-indexed: ## Wait until seeded data is searchable
	@set -a; . ./.env; set +a; WAIT_TIMEOUT=300 $(BIN)/python scripts/wait_ready.py indexed

smoke: ## Quick end-to-end check through the UI proxy
	@curl -fsS localhost:$(UI_PORT)/api/users | $(BIN)/python -c 'import sys,json; d=json.load(sys.stdin); u=d if isinstance(d,list) else d.get("users",d); print("✓ smoke: /api/users ->", len(u), "guests")'

# ─── Run (Next.js + FastAPI, backgrounded; logs and pids in .run/) ────────

up: require-memory-server $(RUN_DIR)/api.pid $(RUN_DIR)/ui.pid ## Start the demo API (API_PORT) and UI (UI_PORT)
	@echo; echo "  Guest: http://localhost:$(UI_PORT)/guest   (alice/bob/charlie, password 123)"
	@echo "  Ops:   http://localhost:$(UI_PORT)/ops     (password: ops)"

$(RUN_DIR):
	@mkdir -p $(RUN_DIR)

.PHONY: require-memory-server
require-memory-server:
	@./scripts/backend.sh require

$(RUN_DIR)/api.pid: | $(RUN_DIR)
	@test -x $(BIN)/uvicorn || { echo "✗ run 'make setup' first"; exit 1; }
	@set -a; . ./.env; set +a; nohup $(BIN)/uvicorn hotel_server:app --host 127.0.0.1 --port $(API_PORT) \
		> $(RUN_DIR)/api.log 2>&1 & echo $$! > $@
	@for i in $$(seq 1 30); do curl -fsS -m 1 localhost:$(API_PORT)/health >/dev/null 2>&1 && { echo "✓ api  :$(API_PORT)"; exit 0; }; sleep 1; done; \
		echo "✗ api failed to start — see $(RUN_DIR)/api.log"; kill $$(cat $@) 2>/dev/null; rm -f $@; exit 1

$(RUN_DIR)/ui.pid: | $(RUN_DIR)
	@test -d hotel_ui/.next || { echo "✗ UI not built — run 'make ui-build'"; exit 1; }
	@NEXT_PUBLIC_API_URL=http://localhost:$(API_PORT) nohup npm --prefix hotel_ui start -- -H 127.0.0.1 -p $(UI_PORT) \
		> $(RUN_DIR)/ui.log 2>&1 & echo $$! > $@
	@for i in $$(seq 1 30); do curl -fsS -m 1 localhost:$(UI_PORT) >/dev/null 2>&1 && { echo "✓ ui   :$(UI_PORT)"; exit 0; }; sleep 1; done; \
		echo "✗ ui failed to start — see $(RUN_DIR)/ui.log"; kill $$(cat $@) 2>/dev/null; rm -f $@; exit 1

down: ## Stop the demo API and UI
	@for n in api ui; do \
		if [ -f $(RUN_DIR)/$$n.pid ]; then \
			pid=$$(cat $(RUN_DIR)/$$n.pid); \
			pkill -P $$pid 2>/dev/null; kill $$pid 2>/dev/null; \
			rm -f $(RUN_DIR)/$$n.pid; echo "• stopped $$n"; \
		fi; done

restart: down up ## Restart both (use after Python or env changes)

status: ## Show health of memory server, demo API and UI
	@curl -fsS -m 2 $(AGENTMEM_BASE_URL)/health >/dev/null 2>&1 && echo "✓ memory server  $(AGENTMEM_BASE_URL)" || echo "✗ memory server  $(AGENTMEM_BASE_URL)"
	@curl -fsS -m 2 localhost:$(API_PORT)/health >/dev/null 2>&1 && echo "✓ api            :$(API_PORT)" || echo "✗ api            :$(API_PORT)"
	@curl -fsS -m 2 localhost:$(UI_PORT) >/dev/null 2>&1 && echo "✓ ui             :$(UI_PORT)" || echo "✗ ui             :$(UI_PORT)"

logs: ## Tail backend and UI logs
	@tail -n 50 -f $(RUN_DIR)/api.log $(RUN_DIR)/ui.log

# ─── Foreground helpers ───────────────────────────────────────────────────

api: ## Run the demo API in the foreground with --reload
	set -a; . ./.env; set +a; $(BIN)/uvicorn hotel_server:app --host 127.0.0.1 --port $(API_PORT) --reload

ui: ## Run UI in the foreground with hot reload
	cd hotel_ui && NEXT_PUBLIC_API_URL=http://localhost:$(API_PORT) npm run dev -- -H 127.0.0.1 -p $(UI_PORT)

streamlit: ## Run both Streamlit apps (guest + ops) in the foreground
	set -a; . ./.env; set +a; \
	$(BIN)/streamlit run agentmem_hotel_ops.py --server.address 127.0.0.1 --server.port $(STREAMLIT_OPS_PORT) --server.headless true & \
	trap 'kill 0' EXIT; \
	$(BIN)/streamlit run agentmem_hotel.py --server.address 127.0.0.1 --server.port $(STREAMLIT_GUEST_PORT) --server.headless true

# ─── Cleanup ──────────────────────────────────────────────────────────────

clean: down ## Stop services and remove logs/build output
	rm -rf $(RUN_DIR) hotel_ui/.next

distclean: clean ## Also remove venv and node_modules (keeps .env)
	rm -rf $(VENV) hotel_ui/node_modules
