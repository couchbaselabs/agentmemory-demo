#!/usr/bin/env bash
# Local Couchbase + Agent Memory server, in Docker.
#   backend.sh up | down | status | destroy
set -euo pipefail
. "$(dirname "$0")/lib.sh"
load_env

need_docker() {
  command -v docker >/dev/null || { bad "Docker not installed. Run: brew install --cask docker"; exit 1; }
  docker_running || { bad "Docker isn't running. Start Docker Desktop (open -a Docker), wait for the whale icon to settle, then retry."; exit 1; }
}

check_key() {
  is_placeholder "${OPENAI_API_KEY:-}" && { bad "OPENAI_API_KEY isn't set in $ENV_FILE — run: make configure"; exit 1; }
  if [ "$(openai_key_status "$OPENAI_API_KEY")" = invalid ]; then
    bad "OpenAI rejected OPENAI_API_KEY (401) — run: make configure"; exit 1
  fi
}

# Up = answers HTTP at all (401 is fine: an initialised cluster requires auth on /pools).
cb_listening() {
  local code
  code="$(docker exec "$CB_CONTAINER" curl -s -o /dev/null -w '%{http_code}' http://localhost:8091/pools 2>/dev/null)" || return 1
  [ "$code" = 200 ] || [ "$code" = 401 ]
}

cbcli() { docker exec "$CB_CONTAINER" couchbase-cli "$@"; }
cb_curl() { docker exec "$CB_CONTAINER" curl -fsS -u "$CB_USER:$CB_PASS" "$@"; }

up_couchbase() {
  docker network inspect "$NET" >/dev/null 2>&1 || docker network create "$NET" >/dev/null
  if docker inspect "$CB_CONTAINER" >/dev/null 2>&1; then
    docker start "$CB_CONTAINER" >/dev/null
  else
    echo "• starting Couchbase Server ($CB_IMAGE) — first run pulls ~1.5 GB"
    docker pull -q "$CB_IMAGE" >/dev/null
    docker run -d --name "$CB_CONTAINER" --network "$NET" \
      -p 127.0.0.1:8091:8091 -v "$CB_VOLUME":/opt/couchbase/var "$CB_IMAGE" >/dev/null
  fi
  wait_for 120 "Couchbase to accept connections" cb_listening

  if ! cbcli server-list -c localhost:8091 -u "$CB_USER" -p "$CB_PASS" >/dev/null 2>&1; then
    echo "• initialising cluster (data, index, query, search)"
    cbcli cluster-init -c localhost:8091 --cluster-name agentmem-demo \
      --cluster-username "$CB_USER" --cluster-password "$CB_PASS" \
      --services data,index,query,fts \
      --cluster-ramsize 1024 --cluster-index-ramsize 512 --cluster-fts-ramsize 512 \
      --index-storage-setting default >/dev/null
  fi
  if ! cbcli bucket-list -c localhost:8091 -u "$CB_USER" -p "$CB_PASS" 2>/dev/null | grep -qx "$CB_BUCKET"; then
    echo "• creating bucket '$CB_BUCKET'"
    cbcli bucket-create -c localhost:8091 -u "$CB_USER" -p "$CB_PASS" \
      --bucket "$CB_BUCKET" --bucket-type couchbase --bucket-ramsize 512 --bucket-replica 0 >/dev/null
  fi
  wait_for 180 "Search (FTS) service" cb_curl http://localhost:8094/api/ping
  wait_for 120 "Query service" cb_curl http://localhost:8093/admin/ping
  ok "Couchbase ready — console http://localhost:8091 ($CB_USER / $CB_PASS)"
}

resolve_image() {
  local tarfile tag
  if tarfile="$(find_tar)"; then
    tag="$(tar_image_tag "$tarfile")"
    if docker image inspect "$tag" >/dev/null 2>&1; then echo "$tag"; return; fi
    echo "• loading $(basename "$tarfile")" >&2
    docker load -i "$tarfile" >/dev/null
    echo "$tag"; return
  fi
  # No tarball around: fall back to an already-loaded image.
  tag="$(docker images --format '{{.Repository}}:{{.Tag}}' | grep '^agentmemory-server:' | head -1 || true)"
  [ -n "$tag" ] && { echo "$tag"; return; }
  bad "Agent Memory server image not found."
  info "Download it via the form linked from"
  info "  https://docs.couchbase.com/ai/build/agent-memory/get-started-agent-mem.html"
  info "then either save it in ~/Downloads or set AGENTMEM_IMAGE_TAR=/path/to/agentmemory-server-$(docker_arch)-<version>.tar in .env (make configure does this)."
  exit 1
}

up_server() {
  is_placeholder "${OPENAI_API_KEY:-}" && { bad "OPENAI_API_KEY isn't set in $ENV_FILE — run: make configure"; exit 1; }
  local image; image="$(resolve_image)"
  mkdir -p "$RUN_DIR"
  local envfile="$RUN_DIR/agentmemory-server.env"
  ( umask 077; cat > "$envfile" <<EOT
AGENTMEMORY_CONN_STRING=couchbase://$CB_CONTAINER
AGENTMEMORY_USERNAME=$CB_USER
AGENTMEMORY_PASSWORD=$CB_PASS
AGENTMEMORY_BUCKET=$CB_BUCKET
OPENAI_API_KEY=$OPENAI_API_KEY
AGENTMEMORY_EMBEDDING_MODEL=${AGENTMEMORY_EMBEDDING_MODEL:-text-embedding-3-small}
AGENTMEMORY_LLM_MODEL=${AGENTMEMORY_LLM_MODEL:-gpt-4o-mini}
AGENTMEMORY_SERVER_HOST=0.0.0.0
AGENTMEMORY_SERVER_PORT=8080
OIDC_AUTH_ENABLED=false
LOG_LEVEL=INFO
EOT
  )
  # The server is stateless: always recreate so config changes take effect.
  docker rm -f "$AM_CONTAINER" >/dev/null 2>&1 || true
  echo "• starting Agent Memory server ($image)"
  docker run -d --name "$AM_CONTAINER" --network "$NET" --env-file "$envfile" \
    -p 127.0.0.1:8080:8080 -v "$AM_LOGS_VOLUME":/app/logs "$image" >/dev/null
  if ! wait_for 120 "Agent Memory server /health" curl -fsS http://127.0.0.1:8080/health; then
    docker logs --tail 40 "$AM_CONTAINER" 2>&1 | grep -E "ERROR|WARNING|Exception" | tail -8 || true
    docker logs "$AM_CONTAINER" 2>&1 | grep -q "health check failed: unauthorized" \
      && bad "OpenAI rejected the API key. Fix it with: make configure   (then: make backend)"
    info "full logs: docker logs $AM_CONTAINER"
    exit 1
  fi
  ok "Agent Memory server healthy — http://localhost:8080  (API docs: /docs)"
}

status() {
  for c in "$CB_CONTAINER" "$AM_CONTAINER"; do
    s="$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo absent)"
    if [ "$s" = running ]; then ok "$c: running"; else bad "$c: $s"; fi
  done
  curl -fsS -m 3 http://127.0.0.1:8080/health 2>/dev/null && echo || true
}

# require — used by `make up`: succeed only if the memory server answers; otherwise say why.
require() {
  local url="${AGENTMEM_BASE_URL:-http://localhost:8080}"
  curl -fsS -m 5 "$url/health" >/dev/null 2>&1 && return 0
  bad "Agent Memory server isn't reachable at $url — the demo would start but every page would fail."
  case "$url" in
    http://localhost:*|http://127.0.0.1:*) ;;
    *) info "That's a remote URL: check AGENTMEM_BASE_URL in $ENV_FILE and that the server is up."; exit 1 ;;
  esac
  if ! command -v docker >/dev/null || ! docker_running; then
    info "Cause: Docker isn't running."
    info "Fix:   open -a Docker   (wait until it says running), then: make backend"
  elif [ "$(docker inspect -f '{{.State.Running}}' "$AM_CONTAINER" 2>/dev/null)" != true ]; then
    info "Cause: the memory server container isn't running."
    info "Fix:   make backend"
  else
    info "Cause: the container is running but not healthy."
    info "Look:  docker logs --tail 40 $AM_CONTAINER"
  fi
  exit 1
}

case "${1:-}" in
  require) require ;;
  up)      need_docker; check_key; up_couchbase; up_server ;;
  down)    need_docker; docker stop "$AM_CONTAINER" "$CB_CONTAINER" >/dev/null 2>&1 || true; ok "backend stopped (data kept)" ;;
  status)  need_docker; status ;;
  destroy)
    need_docker
    if [ "${FORCE:-}" != 1 ]; then
      read -r -p "Delete the local Couchbase data and both containers? [y/N] " a
      [ "$a" = y ] || [ "$a" = Y ] || { echo aborted; exit 1; }
    fi
    docker rm -f "$AM_CONTAINER" "$CB_CONTAINER" >/dev/null 2>&1 || true
    docker volume rm "$CB_VOLUME" "$AM_LOGS_VOLUME" >/dev/null 2>&1 || true
    docker network rm "$NET" >/dev/null 2>&1 || true
    ok "backend removed" ;;
  *) echo "usage: $0 up|down|status|destroy" >&2; exit 2 ;;
esac
