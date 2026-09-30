#!/usr/bin/env bash
# shellcheck shell=bash disable=SC2034  # variables are used by the scripts that source this
# Shared helpers for the demo scripts. Source this; don't run it.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT/.run"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"

NET=agentmem-demo
CB_CONTAINER=agentmem-couchbase
AM_CONTAINER=agentmem-server
CB_VOLUME=agentmem-couchbase-data
AM_LOGS_VOLUME=agentmem-demo-logs   # deliberately not "agentmemory-logs", the name used in the upstream docs
CB_IMAGE="${CB_IMAGE:-couchbase:enterprise-8.0.2}"   # Agent Memory needs Server >= 8.0.2 (Enterprise)
CB_USER=Administrator
CB_PASS="${CB_PASS:-demo-password}"                  # local-only; ports bind to 127.0.0.1
CB_BUCKET="${CB_BUCKET:-agentmem}"

ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*"; }
bad()  { printf '\033[31m✗\033[0m %s\n' "$*"; }
info() { printf '  %s\n' "$*"; }

load_env() {
  # shellcheck disable=SC1090
  if [ -f "$ENV_FILE" ]; then set -a; . "$ENV_FILE"; set +a; fi
}

# set_env KEY VALUE — add or replace KEY in the env file (value written verbatim).
set_env() {
  [ -f "$ENV_FILE" ] || cp "$ROOT/.env.example" "$ENV_FILE"
  KEY="$1" VAL="$2" F="$ENV_FILE" python3 - <<'PY'
import os, re
k, v, f = os.environ["KEY"], os.environ["VAL"], os.environ["F"]
pat = re.compile(rf"^\s*#?\s*{re.escape(k)}=")
out, done = [], False
for line in open(f).read().splitlines():
    if pat.match(line):
        if not done:               # replace the first occurrence (commented or not)
            out.append(f"{k}={v}")
            done = True
        elif line.lstrip().startswith("#"):
            out.append(line)       # keep other commented examples
        # drop later duplicate assignments
    else:
        out.append(line)
if not done:
    out.append(f"{k}={v}")
open(f, "w").write("\n".join(out) + "\n")
PY
  chmod 600 "$ENV_FILE"
}

is_placeholder() { case "${1:-}" in ""|"sk-..."|"sk-your-key"*) return 0;; *) return 1;; esac; }

# openai_key_status KEY — prints ok | invalid | unreachable | http-NNN (asks api.openai.com only).
openai_key_status() {
  local code
  code="$(curl -s -o /dev/null -m 10 -w '%{http_code}' https://api.openai.com/v1/models \
          -H @<(printf 'Authorization: Bearer %s' "$1") 2>/dev/null)" || code=000
  case "$code" in 200) echo ok;; 401) echo invalid;; 000) echo unreachable;; *) echo "http-$code";; esac
}

docker_arch() { case "$(uname -m)" in arm64|aarch64) echo arm64;; *) echo amd64;; esac; }

docker_running() { docker info >/dev/null 2>&1; }

# find_tar — print the path of an Agent Memory server tarball for this CPU, if we can find one.
find_tar() {
  local arch; arch="$(docker_arch)"
  if [ -n "${AGENTMEM_IMAGE_TAR:-}" ] && [ -f "$AGENTMEM_IMAGE_TAR" ]; then echo "$AGENTMEM_IMAGE_TAR"; return 0; fi
  local d f
  for d in "$ROOT" "$HOME/Downloads" "$HOME/Desktop"; do
    f="$(ls -t "$d"/agentmemory-server-"$arch"-*.tar 2>/dev/null | head -1 || true)"
    [ -n "$f" ] && { echo "$f"; return 0; }
  done
  return 1
}

# tar_image_tag TARFILE — the image name:tag stored inside the tarball.
tar_image_tag() {
  tar -xOf "$1" manifest.json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)[0]["RepoTags"][0])'
}

wait_for() { # wait_for SECONDS DESCRIPTION CMD...
  local secs="$1" what="$2"; shift 2
  local i
  for ((i = 0; i < secs; i += 2)); do
    if "$@" >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  bad "timed out after ${secs}s waiting for $what"
  return 1
}
