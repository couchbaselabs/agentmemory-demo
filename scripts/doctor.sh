#!/usr/bin/env bash
# Preflight: checks everything the demo needs and prints exact fixes. Installs nothing.
set -uo pipefail
. "$(dirname "$0")/lib.sh"
load_env
fails=0
fail() { bad "$1"; shift; for l in "$@"; do info "$l"; done; fails=$((fails + 1)); }

# OS / CPU
ok "platform: $(uname -s) $(uname -m)"

# Docker
if ! command -v docker >/dev/null; then
  fail "Docker not installed" "brew install --cask docker   (then open Docker Desktop once)"
elif ! docker_running; then
  fail "Docker is installed but not running" "open -a Docker   (wait until it says 'running', then retry)"
else
  ok "docker: $(docker version -f '{{.Server.Version}}' 2>/dev/null)"
  mem_gb=$(( $(docker info -f '{{.MemTotal}}' 2>/dev/null || echo 0) / 1073741824 ))
  if [ "$mem_gb" -lt 6 ]; then
    warn "Docker has ${mem_gb} GB RAM; Couchbase + Agent Memory want ≥ 6 GB"
    info "Docker Desktop → Settings → Resources → Memory"
  else
    ok "docker memory: ${mem_gb} GB"
  fi
fi

# Python >= 3.12
py=""; for p in ${PYTHON:-} python3.14 python3.13 python3.12 python3; do
  command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(sys.version_info < (3,12))' 2>/dev/null && { py="$p"; break; }
done
if [ -n "$py" ]; then ok "python: $($py --version)"; else
  fail "Python ≥ 3.12 not found" "brew install python@3.14"; fi

# Node >= 18
if command -v node >/dev/null && node -e 'process.exit(+(+process.versions.node.split(".")[0] < 18))'; then
  ok "node: $(node --version)"
else
  fail "Node.js ≥ 18 not found" "brew install node"
fi

# make (for the Makefile itself)
command -v make >/dev/null || fail "make not found" "xcode-select --install"

# OpenAI key
if is_placeholder "${OPENAI_API_KEY:-}"; then
  fail "OPENAI_API_KEY not set" "run: make configure"
else
  case "$(openai_key_status "$OPENAI_API_KEY")" in
    ok)          ok "OPENAI_API_KEY accepted by OpenAI" ;;
    invalid)     fail "OPENAI_API_KEY was rejected by OpenAI (401)" "run: make configure   (paste a valid key)" ;;
    unreachable) warn "OPENAI_API_KEY set, but api.openai.com is unreachable — can't validate" ;;
    *)           warn "OPENAI_API_KEY set; OpenAI returned an unexpected status while validating" ;;
  esac
fi

# Server image
if tarfile="$(find_tar)"; then
  ok "server image tarball: $tarfile"
elif docker images --format '{{.Repository}}' 2>/dev/null | grep -qx agentmemory-server; then
  ok "server image already loaded in Docker"
else
  fail "Agent Memory server image not found" \
    "Download via the form at https://docs.couchbase.com/ai/build/agent-memory/get-started-agent-mem.html" \
    "Save it to ~/Downloads (agentmemory-server-$(docker_arch)-*.tar) or run: make configure"
fi

# Ports (ours are fine if our own containers hold them)
for spec in 8080:$AM_CONTAINER 8091:$CB_CONTAINER 8001: 8502:; do
  port="${spec%%:*}"; owner="${spec#*:}"
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    if [ -n "$owner" ] && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$owner"; then
      ok "port $port in use by $owner (ok)"
    elif [ -f "$RUN_DIR/api.pid" ] || [ -f "$RUN_DIR/ui.pid" ]; then
      ok "port $port in use (demo already running?)"
    else
      warn "port $port is already in use by something else: $(lsof -nP -iTCP:"$port" -sTCP:LISTEN | awk 'NR==2{print $1}')"
    fi
  fi
done

echo
if [ "$fails" -gt 0 ]; then bad "$fails problem(s) — fix the above and re-run: make doctor"; exit 1; fi
ok "all good"
