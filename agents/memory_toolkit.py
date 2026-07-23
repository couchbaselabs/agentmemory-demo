"""
Shared retrieval + formatting primitives for every agent and UI surface.

Three primitives, one job each:

* :class:`MemoryRecord` - structured view of a single Couchbase Agent
  Memory block. Decouples downstream code from the raw SDK shape.
* :func:`search_memories` - run one or many search queries against a
  session in parallel, return a deduped list of MemoryRecords. The ONLY
  place that touches ``session.get_memory`` from agent code.
* :func:`format_memories` - turn a list of MemoryRecords into a
  prompt-ready string sectioned by record kind. The ONLY place that
  decides what an LLM sees from a memory dump.

Design intent:
Every agent in this package is now ``(prompt, config-key) -> call
search_memories -> call format_memories -> stuff into prompt``. If you
need to change what gets retrieved or how it's presented to the LLM,
this file is the only place you should edit.
"""

from __future__ import annotations

import contextlib
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Iterable, Literal

from .config import MAX_PARALLEL_QUERIES

try:
    from agentc_core.activity.models.content import (
        ToolCallContent,
        ToolResultContent,
    )

    _AGENTC = True
except ImportError:
    _AGENTC = False


# ──────────────────────────────────────────────────────────────────────────────
# Structured view of a memory block
# ──────────────────────────────────────────────────────────────────────────────


RecordKind = Literal["chat", "fact", "summary", "context"]


@dataclass
class MemoryRecord:
    """Normalised, kind-tagged view of one Couchbase Agent Memory block.

    Couchbase Agent Memory blocks come in several shapes (chat-style with
    user/assistant content, fact-style for staff notes, summary-style
    rolled up by the SDK, plus separate context_blocks for windowed
    summaries). Downstream code only needs to know "what kind is this and
    what's the text" - this dataclass is that contract.

    Attributes:
        block_id: Stable identifier. Used for dedup and citation.
        kind: One of "chat", "fact", "summary", "context".
        user_content: Guest/user message body. Only set for kind="chat".
        assistant_content: Concierge/assistant reply body. Only set for
            kind="chat".
        text: Body for non-chat kinds (fact text, summary text, context
            window). Empty for kind="chat".
        timestamp: ISO-ish timestamp string when available, else "".
        query: The originating search query that surfaced this record.
            Useful for debugging "why did this memory appear?".
        ref_user: Optional guest user_id when fanning out across users
            (set by :func:`search_memories_multi_user`).
    """

    block_id: str
    kind: RecordKind
    user_content: str = ""
    assistant_content: str = ""
    text: str = ""
    timestamp: str = ""
    query: str = ""
    ref_user: str = ""


# ──────────────────────────────────────────────────────────────────────────────
# Block extraction (the ONE place we read raw SDK shape)
# ──────────────────────────────────────────────────────────────────────────────


def _record_from_memory_block(block: Any, query: str = "") -> MemoryRecord | None:
    """Convert one raw MemoryBlock into a MemoryRecord, or None to skip.

    Reads only documented fields from the Couchbase Agent Memory SDK:

        block_id      - canonical identifier (always present)
        ingested_at   - server-side timestamp (always present)
        message       - ChatMessage(user_content, assistant_content) for
                        chat-style blocks; None for fact-style.
        fact          - string for fact-style blocks; None otherwise.
        summary       - server-generated abstract (always set; rolled-up).
        contexts      - list[str] of windowed semantic bits.
        annotations   - dict; we read 'timestamp' if the writer set one.

    Resolution order: fact → summary → contexts. Raw chat is excluded;
    summaries and context windows capture the same information more
    compactly. Blocks with no summary or contexts yet are skipped until
    async processing completes.

    Timestamp: prefers annotations.timestamp when the writer set one
    (e.g. call-note agent's logged_at), else falls back to ingested_at.
    """
    block_id = str(block.block_id)
    ingested_at = getattr(block, "ingested_at", "") or ""

    # annotations is a dict per the SDK docs. The double-getattr chain
    # tolerates both dict and object shapes safely.
    annotations = getattr(block, "annotations", None) or {}
    if isinstance(annotations, dict):
        timestamp = annotations.get("timestamp") or ingested_at
    else:
        timestamp = getattr(annotations, "timestamp", "") or ingested_at

    # Resolution order: summary → contexts → fact → message (fallback).
    # summary/contexts are the most compact signal; fact is a staff note;
    # message is the raw chat content used when the SDK has not yet
    # finished async processing (new blocks, no summary/contexts yet).

    summary = getattr(block, "summary", None) or ""
    if summary:
        return MemoryRecord(
            block_id=block_id,
            kind="summary",
            text=summary,
            timestamp=timestamp,
            query=query,
        )

    contexts = getattr(block, "contexts", None) or []
    if contexts:
        joined = "\n".join(c for c in contexts if c)
        if joined:
            return MemoryRecord(
                block_id=block_id,
                kind="context",
                text=joined,
                timestamp=timestamp,
                query=query,
            )

    fact = getattr(block, "fact", None) or ""
    if fact:
        return MemoryRecord(
            block_id=block_id,
            kind="fact",
            text=fact,
            timestamp=timestamp,
            query=query,
        )

    # Fallback: raw message content for blocks the SDK has not yet
    # processed into summary/contexts (brand-new or in-flight blocks).
    message = getattr(block, "message", None)
    if message:
        user_content = getattr(message, "user_content", "") or ""
        assistant_content = getattr(message, "assistant_content", "") or ""
        if user_content or assistant_content:
            return MemoryRecord(
                block_id=block_id,
                kind="chat",
                user_content=user_content,
                assistant_content=assistant_content,
                timestamp=timestamp,
                query=query,
            )

    return None


# ──────────────────────────────────────────────────────────────────────────────
# search_memories - the One Search Function
# ──────────────────────────────────────────────────────────────────────────────


def search_memories(
    session: Any,
    queries: str | Iterable[str],
    k: int,
    *,
    cross_session: bool = True,
    max_workers: int = MAX_PARALLEL_QUERIES,
) -> list[MemoryRecord]:
    """Retrieve memories from a Couchbase Agent Memory session.

    Pass ONE query for a single search, or a list to fan out in
    parallel. Results from all queries are merged and deduped on
    block_id so the same memory never appears twice.

    This is the only function in the agents package that should call
    ``session.search_memory`` directly. Every agent and every UI memory
    read goes through here.

    The SDK returns a ``MemoryResponse`` with a ``memory_blocks`` field;
    we walk those and map each to a :class:`MemoryRecord`.

    Args:
        session: Active Couchbase Agent Memory session.
        queries: One query string or an iterable of them.
        k: ``relevant_k`` to pass to Couchbase Agent Memory per query.
            Pull this from :data:`agents.config.MEMORY_K` rather than
            hardcoding a literal.
        cross_session: When True (default), search across all sessions
            for the user (``session_ids="all"``).
        max_workers: Cap on parallel threads.

    Returns:
        Deduped list of MemoryRecords ordered by completion. Empty list
        on session=None or total retrieval failure.
    """
    if session is None:
        return []

    if isinstance(queries, str):
        query_list: list[str] = [queries]
    else:
        query_list = [q for q in queries if q]
    if not query_list:
        return []

    # Deduplicate queries (preserving order) so identical strings don't
    # generate redundant backend calls and inflate backend load.
    query_list = list(dict.fromkeys(query_list))

    # Build filter dict for the search.
    # When cross_session=True, search all sessions for the user.
    filter_dict = {"relevant_k": k}
    if cross_session:
        filter_dict["session_ids"] = "all"

    def _one(q: str) -> tuple[str, Any]:
        try:
            return q, session.search_memory(query=q, filters=filter_dict)
        except Exception as exc:
            print(f"warning: memory search failed for query {q!r:.60} — {exc}")
            return q, None

    seen: set[str] = set()
    records: list[MemoryRecord] = []

    workers = min(max_workers, max(1, len(query_list)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_one, q) for q in query_list]
        for fut in as_completed(futures):
            try:
                q, result = fut.result()
            except Exception as exc:
                print(
                    f"warning: future result retrieval failed in search_memories — {exc}"
                )
                continue
            if result is None:
                continue

            for mb in getattr(result, "memory_blocks", None) or []:
                rec = _record_from_memory_block(mb, query=q)
                if rec and rec.block_id not in seen:
                    seen.add(rec.block_id)
                    records.append(rec)

    return records


def search_memories_multi_user(
    user_sessions: list[tuple[str, Any]],
    queries: str | Iterable[str],
    k: int,
    *,
    max_workers: int = MAX_PARALLEL_QUERIES,
) -> list[MemoryRecord]:
    """Same as :func:`search_memories`, but across many users at once.

    Used by the digest agent. Each returned record has ``ref_user`` set
    to the originating user_id so the formatter can group by guest.
    """
    if isinstance(queries, str):
        query_list: list[str] = [queries]
    else:
        query_list = [q for q in queries if q]
    if not user_sessions or not query_list:
        return []

    # Deduplicate queries before building the work list.
    query_list = list(dict.fromkeys(query_list))

    # Multi-user searches always cross sessions to find matching memories across all guests.
    filter_dict = {"relevant_k": k, "session_ids": "all"}

    def _one(user_id: str, sess: Any, q: str) -> tuple[str, str, Any]:
        try:
            return user_id, q, sess.search_memory(query=q, filters=filter_dict)
        except Exception as exc:
            print(
                f"warning: memory search failed for user {user_id!r} query {q!r:.60} — {exc}"
            )
            return user_id, q, None

    work = [(uid, sess, q) for (uid, sess) in user_sessions for q in query_list]
    seen: set[tuple[str, str]] = set()  # (user_id, block_id)
    records: list[MemoryRecord] = []

    workers = min(max_workers, max(1, len(work)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_one, uid, sess, q) for (uid, sess, q) in work]
        for fut in as_completed(futures):
            try:
                user_id, q, result = fut.result()
            except Exception as exc:
                print(
                    f"warning: future result retrieval failed in search_memories_multi_user — {exc}"
                )
                continue
            if result is None:
                continue
            for mb in getattr(result, "memory_blocks", None) or []:
                rec = _record_from_memory_block(mb, query=q)
                if rec is None:
                    continue
                key = (user_id, rec.block_id)
                if key in seen:
                    continue
                seen.add(key)
                rec.ref_user = user_id
                records.append(rec)

    return records


# ──────────────────────────────────────────────────────────────────────────────
# format_memories - the One Formatter
# ──────────────────────────────────────────────────────────────────────────────


def _short_ts(ts: str) -> str:
    """Trim noisy second-precision timestamps to YYYY-MM-DD when sensible."""
    if not ts:
        return ""
    # Conservative slice: keep up to the 'T' or first space, fall through
    # otherwise so unfamiliar shapes are preserved verbatim.
    for sep in ("T", " "):
        if sep in ts:
            return ts.split(sep, 1)[0]
    return ts[:10] if len(ts) > 10 else ts


def format_memories(
    records: list[MemoryRecord],
    *,
    include_block_ids: bool = False,
    group_by_user: bool = False,
) -> str:
    """Render MemoryRecords into a prompt-ready, sectioned string.

    Layout::

        [Known facts]
        - 2026-04-10  Allergic to shellfish  [block:abc123]
        ...

        [Past conversations]
        - 2026-04-12  Guest: ...
                      Concierge: ...
        ...

        [Summaries]
        - 2026-04-15  3-night stay, 2 spa visits, 1 complaint resolved
        ...

        [Context windows]
        - <rolled-up window text>
        ...

    Sections appear in this order: facts, chat, summaries, context.
    Empty sections are omitted. Block IDs and timestamps are included
    when present so the LLM can cite them; turn off ``include_block_ids``
    if the prompt is purely synthesis-only.

    Args:
        records: Records as returned by :func:`search_memories`. All
            records are included with no truncation.
        include_block_ids: Prefix each excerpt with [block:<id>] for
            citation-grade prompts.
        group_by_user: When True (multi-user digests), insert a
            ``[guest:<user_id>]`` subheading before each guest's
            entries within every section.

    Returns:
        A single formatted string, or "" when ``records`` is empty.
    """
    if not records:
        return ""

    capped = records

    # Section bucketing - keep insertion order within each section.
    buckets: dict[str, list[MemoryRecord]] = {
        "fact": [],
        "chat": [],
        "summary": [],
        "context": [],
    }
    for r in capped:
        buckets.setdefault(r.kind, []).append(r)

    section_titles = {
        "fact": "Known facts",
        "chat": "Past conversations",
        "summary": "Summaries",
        "context": "Context windows",
    }

    def _line_for(rec: MemoryRecord) -> str:
        ts = _short_ts(rec.timestamp)
        bid = f" [block:{rec.block_id}]" if include_block_ids else ""
        head = f"- {ts}  " if ts else "- "
        if rec.kind == "chat":
            return (
                f"{head}Guest: {rec.user_content}\n"
                f"  Concierge: {rec.assistant_content}{bid}"
            )
        # fact / summary / context all carry their body in rec.text
        return f"{head}{rec.text}{bid}"

    out_sections: list[str] = []
    for kind in ("fact", "chat", "summary", "context"):
        items = buckets.get(kind) or []
        if not items:
            continue

        title = f"[{section_titles[kind]}]"
        if group_by_user:
            by_user: dict[str, list[MemoryRecord]] = {}
            for r in items:
                by_user.setdefault(r.ref_user or "(unknown)", []).append(r)
            block_lines: list[str] = [title]
            for uid, recs in by_user.items():
                block_lines.append(f"  [guest:{uid}]")
                for r in recs:
                    block_lines.append("  " + _line_for(r))
            out_sections.append("\n".join(block_lines))
        else:
            block_lines = [title] + [_line_for(r) for r in items]
            out_sections.append("\n".join(block_lines))

    return "\n\n".join(out_sections)


# ──────────────────────────────────────────────────────────────────────────────
# make_retrieval_node - factory for LangGraph memory-search nodes
# ──────────────────────────────────────────────────────────────────────────────


def make_retrieval_node(
    queries: list[str],
    k: int,
    *,
    include_block_ids: bool = False,
):
    """Build a LangGraph node that fans out, dedupes, and formats memories.

    Used by every ops agent (briefing, flag, group_event_brief, etc.).
    Reads ``state["agentmem_user"]`` and writes ``memory_context``
    (str) and ``retrieval_ms`` (float). Automatically searches across
    all user sessions. The ONLY thing that varies between agents is the
    query list and the K - everything else lives in this factory.

    Args:
        queries: Fan-out search queries the agent cares about.
        k: Pull from :data:`agents.config.MEMORY_K`. Hardcoded literals
            here are a smell.
        include_block_ids: Tag each excerpt with [block:<id>] for
            citation-grade prompts.

    Returns:
        A callable ``(state) -> dict`` suitable for ``StateGraph.add_node``.
    """
    import time as _time  # local import to keep top-level imports tight
    from ._ops_utils import get_user_session

    def _node(state: dict) -> dict:
        user = state.get("agentmem_user")
        if user is None:
            return {"memory_context": "", "retrieval_ms": 0.0}

        client = state.get("client") or state.get("agentmem_client")
        user_id = state.get("guest_id") or state.get("user_id")
        session = get_user_session(user, client=client, user_id=user_id)
        if session is None:
            return {"memory_context": "", "retrieval_ms": 0.0}

        span = state.get("span")
        ctx = (
            span.new("memory-retrieval")
            if span is not None
            else contextlib.nullcontext()
        )
        with ctx as s:
            call_id = uuid.uuid4().hex
            if s is not None and _AGENTC:
                try:
                    s.log(
                        ToolCallContent(
                            tool_name="search_memories",
                            tool_args={"queries": queries, "k": k},
                            tool_call_id=call_id,
                        )
                    )
                except Exception as exc:
                    print(f"  [agentc] log failed: {exc}")

            import threading as _threading

            # Run get_memory() in parallel with vector search so it adds
            # zero net latency (both complete concurrently).
            _direct: list = []

            def _fetch_direct():
                try:
                    resp = session.get_memory()
                    _direct.extend(getattr(resp, "memory_blocks", None) or [])
                except Exception as _exc:
                    print(f"  [retrieval] direct get_memory failed — {_exc}")

            _t = _threading.Thread(target=_fetch_direct, daemon=True)
            _t.start()

            t0 = _time.time()
            records = search_memories(session, queries, k=k, cross_session=True)
            _t.join()

            # Merge blocks not found by FTS (e.g. not yet indexed).
            _seen = {r.block_id for r in records}
            for mb in _direct:
                rec = _record_from_memory_block(mb, query="[direct]")
                if rec and rec.block_id not in _seen:
                    _seen.add(rec.block_id)
                    records.append(rec)

            memory_context = format_memories(
                records,
                include_block_ids=include_block_ids,
            )
            retrieval_ms = (_time.time() - t0) * 1000

            if s is not None and _AGENTC:
                try:
                    s.log(
                        ToolResultContent(
                            tool_call_id=call_id,
                            tool_result=f"{len(records)} records retrieved",
                        )
                    )
                except Exception as exc:
                    print(f"  [agentc] log failed: {exc}")

        return {"memory_context": memory_context, "retrieval_ms": retrieval_ms}

    return _node


# ──────────────────────────────────────────────────────────────────────────────
# QueryRewriter - the One Query Refinement Node
# ──────────────────────────────────────────────────────────────────────────────


def _parse_bulleted(text: str) -> list[str]:
    """Extract bullet-prefixed lines from LLM output into a clean list.

    Handles "- query", "* query", and plain lines. Strips whitespace and
    empty strings. Used by :class:`QueryRewriter` to parse its output.
    """
    lines = []
    for line in (text or "").splitlines():
        stripped = line.strip().lstrip("-*•").strip()
        if stripped:
            lines.append(stripped)
    return lines


class QueryRewriter:
    """Expand a single raw query into focused retrieval queries.

    Uses :data:`prompts.SEARCH_REFINEMENT_TEMPLATE` so the prompt is
    centralised and versioned alongside every other prompt. Always
    includes the original raw query as a safety net so exact-match
    recall is never lost to an over-paraphrased rewrite.

    Args:
        llm: Initialised LangChain LLM. Low temperature recommended —
            the rewriter is not meant to be creative.
        n: Target number of refined queries (default 3). The LLM may
            produce fewer if the question is narrow.

    Usage::

        rewriter = QueryRewriter(llm)
        queries = rewriter.rewrite("do you have any dietary restrictions?")
        records = search_memories(session, queries, k=MEMORY_K["concierge"])
    """

    def __init__(self, llm, n: int = 3) -> None:
        self.llm = llm
        self.n = n

    def rewrite(self, query: str) -> list[str]:
        """Return up to n+1 refined queries (raw + n rewrites); always non-empty.

        Falls back to ``[query]`` on any LLM failure so callers never
        need to null-check the result.
        """
        from langchain_core.messages import HumanMessage
        from prompts import SEARCH_REFINEMENT_TEMPLATE, renderer

        if not query or not query.strip():
            return []

        prompt = renderer.render(SEARCH_REFINEMENT_TEMPLATE, query=query, n=self.n)
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
        except Exception:
            return [query]

        refined = _parse_bulleted(getattr(response, "content", "") or "")

        # Always include the raw query so exact-match recall is never lost.
        if query not in refined:
            refined = [query] + refined

        # Deduplicate while preserving order, cap at n+1.
        seen: set[str] = set()
        deduped: list[str] = []
        for q in refined:
            qn = q.strip()
            if qn and qn not in seen:
                seen.add(qn)
                deduped.append(qn)

        return deduped[: self.n + 1] if deduped else [query]

    def node(self, state: dict) -> dict:
        """LangGraph-compatible node: reads ``user_query``, writes ``refined_queries``."""
        query = state.get("user_query", "")
        return {"refined_queries": self.rewrite(query) or [query]}


__all__ = [
    "MemoryRecord",
    "RecordKind",
    "search_memories",
    "search_memories_multi_user",
    "format_memories",
    "make_retrieval_node",
    "QueryRewriter",
]
