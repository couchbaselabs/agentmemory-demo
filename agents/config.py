"""
Central configuration for memory retrieval across all agents and UIs.

Single source of truth for `relevant_k` (the number of memory blocks to
retrieve per search call). Every agent, every UI surface, every helper
that touches Couchbase Agent Memory pulls its K from here so changing
retrieval depth is a one-line edit.

Adding a new agent? Add an entry here. Hardcoding K anywhere else is a
bug.
"""

from __future__ import annotations


# ──────────────────────────────────────────────────────────────────────────────
# Per-call-site K values
# ──────────────────────────────────────────────────────────────────────────────
#
# Values preserve the behaviour observed in the codebase before the
# Phase-1 toolkit refactor; tune in one place going forward.

MEMORY_K: dict[str, int] = {
    # Ops agents - synthesise across many memories per guest.
    # briefing: 9 queries × 20 = max 180 blocks retrieved.
    "briefing": 20,
    "digest": 10,
    "flag": 25,
    "group_event_brief": 10,
    "profile_overview": 50,
    "safety_scan": 20,
    "call_note_dedup": 5,
    # Concierge stack - per-refined-query retrieval for chat replies.
    "concierge": 10,
    # UI memory browsers - raw display, no LLM.
    "session_preview": 5,
    "session_history": 30,
    "role_memory": 25,
}


# ──────────────────────────────────────────────────────────────────────────────
# Retrieval defaults shared across the toolkit
# ──────────────────────────────────────────────────────────────────────────────

# Hard cap on parallel get_memory threads inside fan-out searches. Higher
# values risk overwhelming the Couchbase Agent Memory server; lower values
# slow down ops agents that fan out across 6-7 queries.
# Set to 20 to handle digest (3 users × 7 queries = 21 work items) without
# queuing; briefing and profile_overview (8-10 queries) fit comfortably too.
MAX_PARALLEL_QUERIES: int = 20

# Number of additional refined queries the concierge query-rewriter generates
# per guest message. Each refined query is one extra search_memory call, so
# total searches per turn = QUERY_REWRITER_N + 1 (the original query is always
# included). Raise to broaden recall; lower to reduce latency.
QUERY_REWRITER_N: int = 3


def k_for(call_site: str) -> int:
    """Look up the configured K value for a named call site.

    Raises KeyError on unknown names so a typo blows up loudly rather
    than silently retrieving the wrong amount of memory.

    Args:
        call_site: A key from MEMORY_K (e.g. "briefing", "concierge").

    Returns:
        The configured relevant_k for that call site.
    """
    if call_site not in MEMORY_K:
        raise KeyError(
            f"Unknown memory call site '{call_site}'. "
            f"Add it to MEMORY_K in agents/config.py. "
            f"Known sites: {sorted(MEMORY_K)}"
        )
    return MEMORY_K[call_site]
