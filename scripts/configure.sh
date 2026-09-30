#!/usr/bin/env bash
# Interactive first-run configuration: writes .env (OpenAI key, server image path).
# Safe to re-run; only asks for what's missing. Never echoes the API key.
set -euo pipefail
. "$(dirname "$0")/lib.sh"

[ -f "$ENV_FILE" ] || { cp "$ROOT/.env.example" "$ENV_FILE"; chmod 600 "$ENV_FILE"; echo "• created $ENV_FILE"; }
load_env
interactive=0; [ -t 0 ] && interactive=1

# 1. OpenAI key
if is_placeholder "${OPENAI_API_KEY:-}"; then
  if [ $interactive = 1 ]; then
    echo "OpenAI API key (input hidden; stored only in .env, which is git-ignored)."
    read -r -s -p "OPENAI_API_KEY: " key; echo
    if is_placeholder "$key"; then bad "no key entered"; exit 1; fi
    case "$(openai_key_status "$key")" in
      invalid) bad "OpenAI rejected that key (401). Nothing saved."; exit 1 ;;
      unreachable) warn "couldn't reach api.openai.com to validate the key; saving anyway" ;;
    esac
    set_env OPENAI_API_KEY "$key"
    ok "OPENAI_API_KEY saved"
  else
    bad "OPENAI_API_KEY is not set in $ENV_FILE"; exit 1
  fi
else
  ok "OPENAI_API_KEY already set"
fi

# 2. Agent Memory server image tarball
if tarfile="$(find_tar)"; then
  ok "Agent Memory server image: $tarfile"
  [ "${AGENTMEM_IMAGE_TAR:-}" = "$tarfile" ] || set_env AGENTMEM_IMAGE_TAR "$tarfile"
elif docker images --format '{{.Repository}}' 2>/dev/null | grep -qx agentmemory-server; then
  ok "Agent Memory server image already loaded in Docker"
elif [ $interactive = 1 ]; then
  echo
  echo "The Agent Memory server image isn't downloaded yet. Get it from the form linked at"
  echo "  https://docs.couchbase.com/ai/build/agent-memory/get-started-agent-mem.html"
  echo "(file name: agentmemory-server-$(docker_arch)-<version>.tar)"
  read -r -p "Path to the .tar (drag the file here): " p
  p="${p//\\ / }"; p="${p%\"}"; p="${p#\"}"; p="${p/#\~/$HOME}"
  [ -f "$p" ] || { bad "not found: $p"; exit 1; }
  set_env AGENTMEM_IMAGE_TAR "$p"
  ok "saved AGENTMEM_IMAGE_TAR"
else
  bad "Agent Memory server image not found (set AGENTMEM_IMAGE_TAR in $ENV_FILE)"; exit 1
fi
