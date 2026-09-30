"""Readiness checks against the Agent Memory server.

  python scripts/wait_ready.py server    # server + Couchbase + models healthy
  python scripts/wait_ready.py indexed   # seeded data is searchable (replaces "wait 30-60s")

Exits 0 when ready, 1 on timeout. Reads AGENTMEM_BASE_URL from the environment.
"""
from __future__ import annotations

import os
import sys
import time

from agentmemory import AgentMemoryClient

BASE_URL = os.getenv("AGENTMEM_BASE_URL", "http://localhost:8080")
TIMEOUT = float(os.getenv("WAIT_TIMEOUT", "180"))
PROBE_USER, PROBE_QUERY = "alice_chen", "shellfish allergy"


def client() -> AgentMemoryClient:
    return AgentMemoryClient(base_url=BASE_URL, timeout=30.0, verify=False)


def server_ready(c: AgentMemoryClient) -> tuple[bool, str]:
    r = c.health_ping()
    parts = {
        "server": r.server,
        "couchbase": r.couchbase,
        "models": r.models,
    }
    bad = []
    for name, v in parts.items():
        status = v.get("status") if isinstance(v, dict) else getattr(v, "status", None)
        if str(getattr(status, "value", status)) != "healthy":
            bad.append(f"{name}={status}")
    return (not bad), ", ".join(bad) or "healthy"


def indexed_ready(c: AgentMemoryClient) -> tuple[bool, str]:
    user = c.get_user(user_id=PROBE_USER)
    sessions = getattr(user.list_sessions(), "sessions", None) or []
    if not sessions:
        return False, f"no sessions for {PROBE_USER} (did `make seed` run?)"
    first = sessions[-1]
    sid = first if isinstance(first, str) else first.session_id
    res = user.get_session(session_id=sid).search_memory(
        query=PROBE_QUERY, filters={"session_ids": "all"}
    )
    n = len(res.memory_blocks)
    return n > 0, f"{n} search hit(s) for {PROBE_QUERY!r}"


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "server"
    check = {"server": server_ready, "indexed": indexed_ready}.get(mode)
    if check is None:
        print(f"usage: {sys.argv[0]} server|indexed", file=sys.stderr)
        return 2
    c = client()
    deadline = time.time() + TIMEOUT
    last = ""
    while time.time() < deadline:
        try:
            ok, last = check(c)
            if ok:
                print(f"✓ {mode}: {last}")
                return 0
        except Exception as exc:  # server not up yet, index not built yet, ...
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(3)
    print(f"✗ {mode}: not ready after {TIMEOUT:.0f}s — {last}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
