"""
Call-note ingestion agent (ops side).

Trigger: a staff member uses the Log Guest Call view in the ops
portal after a phone call or in-person guest interaction.

Pipeline::

    START → classify → memory-search → enrich → write → END

* classify       LLM normalises the free-text note into a structured
                     fact (canonical phrasing, category, severity, tags).
                     Can override the staff-selected category when the
                     note text disagrees.
* memory-search  Couchbase Agent Memory retrieval against the guest's namespace,
                     looking for near-duplicate facts so we can mark the
                     write as a follow-up rather than a fresh datapoint.
* enrich         Build the final fact string (subject explicitly
                     bound to the guest) and the annotations payload.
* write          ``session.add_memory(facts=[...], annotations={...},
                     async_processing=False)`` into the guest namespace.

Reads:  the guest's prior memory (top-K near-duplicate check).
Writes: a single fact-style memory block into the guest's session.
"""

from __future__ import annotations

import contextlib
import os
import time
import uuid
from typing import Any, Optional, TypedDict

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from prompts import CALL_NOTE_TEMPLATE, renderer

from ._ops_utils import safe_parse_json
from .config import MEMORY_K
from .memory_toolkit import search_memories

try:
    from agentc_core.activity.models.content import (
        ChatCompletionContent,
        SystemContent,
        ToolCallContent,
        ToolResultContent,
    )

    _AGENTC = True
except ImportError:
    _AGENTC = False


CALL_NOTE_CATEGORIES: dict[str, str] = {
    "complaint": "Complaint",
    "allergy": "Allergy / dietary",
    "preference": "Preference",
    "request": "Request",
    "incident": "Incident / safety",
    "general": "General note",
}


class CallNoteState(TypedDict, total=False):
    # inputs
    client: Any
    agentmem_session: Any
    agentmem_user: Any
    guest_id: str
    guest_name: str
    raw_note: str
    staff_category: str
    logged_by_role: str
    logged_by_role_name: str
    timestamp: str

    # classify-node outputs
    classified_category: str
    classified_severity: str
    classified_tags: list[str]
    canonical_fact: str
    classify_ms: float

    # memory-search-node outputs
    near_duplicate_excerpt: str
    near_duplicate_block_ids: list[str]
    retrieval_ms: float

    # enrich-node outputs
    final_fact: str
    annotations: dict
    enrich_ms: float

    # write-node outputs
    block_id: str
    write_ok: bool
    write_ms: float

    span: Optional[object]


# ──────────────────────────────────────────────────────────────
# Nodes
# ──────────────────────────────────────────────────────────────


class _ClassifyNode:
    """LLM node: normalise the staff note into a structured fact.

    Args:
        llm: Initialised LangChain LLM instance used for classification.
    """

    def __init__(self, llm: ChatOpenAI) -> None:
        self.llm = llm

    def node(self, state: dict) -> dict:
        """Classify the staff note into a structured fact with category and severity.

        Args:
            state: LangGraph state dict. Expected keys: ``guest_id``,
                ``guest_name``, ``staff_category``, ``logged_by_role_name``,
                ``timestamp``, ``raw_note``, and optionally ``span``.

        Returns:
            Partial state dict with ``classified_category`` (str),
            ``classified_severity`` (str), ``classified_tags`` (list[str]),
            ``canonical_fact`` (str), and ``classify_ms`` (float).
        """
        prompt = renderer.render(
            CALL_NOTE_TEMPLATE,
            guest_id=state.get("guest_id", ""),
            guest_name=state.get("guest_name", ""),
            staff_category=CALL_NOTE_CATEGORIES.get(
                state.get("staff_category", "general"),
                state.get("staff_category", "general"),
            ),
            logged_by_role_name=state.get("logged_by_role_name", ""),
            timestamp=state.get("timestamp", ""),
            raw_note=state.get("raw_note", ""),
            existing_memory="",  # filled in retroactively below if memory-search runs first
        )
        span = state.get("span")
        ctx = span.new("classify") if span is not None else contextlib.nullcontext()
        with ctx as s:
            if s is not None and _AGENTC:
                try:
                    s.log(SystemContent(value=prompt))
                except Exception as exc:
                    print(f"  [agentc] log failed: {exc}")

            t0 = time.time()
            response = self.llm.invoke([HumanMessage(content=prompt)])
            classify_ms = (time.time() - t0) * 1000

            if s is not None and _AGENTC:
                try:
                    s.log(ChatCompletionContent(output=response.content.strip()))
                except Exception as exc:
                    print(f"  [agentc] log failed: {exc}")

        parsed = safe_parse_json(response.content) or {}
        category = parsed.get("category") or state.get("staff_category", "general")
        if category not in CALL_NOTE_CATEGORIES:
            category = state.get("staff_category", "general")
        severity = parsed.get("severity") or "none"
        tags = parsed.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        canonical_fact = (parsed.get("canonical_fact") or "").strip()
        if not canonical_fact:
            # Defensive fallback - the LLM may have failed to produce JSON.
            canonical_fact = (
                f"{state.get('guest_name', 'Guest')} - "
                f"{state.get('raw_note', '').strip()}"
            )

        return {
            "classified_category": category,
            "classified_severity": severity,
            "classified_tags": tags,
            "canonical_fact": canonical_fact,
            "classify_ms": classify_ms,
        }


class _MemorySearchNode:
    """Look for near-duplicate facts already in the guest's Couchbase Agent Memory session."""

    def node(self, state: dict) -> dict:
        """Search the guest's session for near-duplicate facts.

        Args:
            state: LangGraph state dict. Expected keys: ``agentmem_session``,
                ``raw_note``, and optionally ``span``.

        Returns:
            Partial state dict with ``near_duplicate_excerpt`` (str),
            ``near_duplicate_block_ids`` (list[str]), and
            ``retrieval_ms`` (float).
        """
        session = state.get("agentmem_session")
        raw_note = state.get("raw_note", "") or ""
        if session is None or not raw_note:
            return {
                "near_duplicate_excerpt": "",
                "near_duplicate_block_ids": [],
                "retrieval_ms": 0.0,
            }

        span = state.get("span")
        ctx = (
            span.new("memory-search") if span is not None else contextlib.nullcontext()
        )
        with ctx as s:
            call_id = uuid.uuid4().hex
            if s is not None and _AGENTC:
                try:
                    s.log(
                        ToolCallContent(
                            tool_name="search_memories",
                            tool_args={
                                "query": raw_note,
                                "k": MEMORY_K["call_note_dedup"],
                            },
                            tool_call_id=call_id,
                        )
                    )
                except Exception as exc:
                    print(f"  [agentc] log failed: {exc}")

            t0 = time.time()
            records = search_memories(
                session,
                raw_note,
                k=MEMORY_K["call_note_dedup"],
            )
            retrieval_ms = (time.time() - t0) * 1000

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

        # Dedup uses raw text (not sectioned) since the downstream check
        # is fuzzy duplicate matching, not LLM synthesis.
        excerpts: list[str] = []
        block_ids: list[str] = []
        for rec in records[:5]:
            if rec.kind == "chat":
                if rec.user_content:
                    excerpts.append(rec.user_content.strip())
                if rec.assistant_content:
                    excerpts.append(rec.assistant_content.strip())
            elif rec.text:
                excerpts.append(rec.text.strip())
            block_ids.append(rec.block_id)

        excerpt_blob = "\n---\n".join(excerpts[:5])
        return {
            "near_duplicate_excerpt": excerpt_blob,
            "near_duplicate_block_ids": block_ids,
            "retrieval_ms": retrieval_ms,
        }


class _EnrichNode:
    """Build the final fact string and annotations payload for Couchbase Agent Memory."""

    def node(self, state: dict) -> dict:
        """Build the bound fact string and annotations dict from classified state.

        Args:
            state: LangGraph state dict. Expected keys: ``guest_name``,
                ``guest_id``, ``timestamp``, ``logged_by_role_name``,
                ``logged_by_role``, ``classified_category``,
                ``classified_severity``, ``classified_tags``,
                ``canonical_fact``, ``raw_note``, and
                ``near_duplicate_block_ids``.

        Returns:
            Partial state dict with ``final_fact`` (str),
            ``annotations`` (dict), and ``enrich_ms`` (float).
        """
        t0 = time.time()
        guest_name = state.get("guest_name", "Guest")
        guest_id = state.get("guest_id", "")
        ts = state.get("timestamp", "")
        role_name = state.get("logged_by_role_name", "")
        role_id = state.get("logged_by_role", "")
        category = state.get(
            "classified_category", state.get("staff_category", "general")
        )
        category_label = CALL_NOTE_CATEGORIES.get(category, category)
        severity = state.get("classified_severity", "none")
        tags = state.get("classified_tags", []) or []
        canonical_fact = state.get("canonical_fact", "").strip()
        raw_note = state.get("raw_note", "").strip()
        near_duplicate_block_ids = state.get("near_duplicate_block_ids", []) or []

        # The fact written to Couchbase Agent Memory. Subject is bound to the guest TWICE
        # (header + canonical sentence) so downstream LLMs cannot misread
        # the note as a third-party observation.
        final_fact = (
            f"[Staff call note about {guest_name} ({guest_id}) - {ts} - "
            f"logged by {role_name}] "
            f"Category: {category_label}. "
            f"This note is about {guest_name} themselves. "
            f"{canonical_fact} "
            f"Original staff phrasing: {raw_note}"
        )

        annotations = {
            "source": "staff_call_note",
            "category": category,
            "severity": severity,
            "logged_by_role": role_id,
            "logged_at": ts,
            "ref_user": guest_id,
        }
        if tags:
            annotations["tags"] = ",".join(tags[:8])
        if near_duplicate_block_ids:
            annotations["related_block_ids"] = ",".join(near_duplicate_block_ids[:5])

        return {
            "final_fact": final_fact,
            "annotations": annotations,
            "enrich_ms": (time.time() - t0) * 1000,
        }


class _WriteNode:
    """Synchronously persist the fact into the guest's Couchbase Agent Memory session.

    Uses async_processing=False so the block is immediately indexed and
    visible to subsequent rescans within the same request.
    """

    def node(self, state: dict) -> dict:
        """Persist the enriched fact into the guest's Couchbase Agent Memory session.

        Args:
            state: LangGraph state dict. Expected keys: ``agentmem_session``,
                ``agentmem_user``, ``final_fact``, ``annotations``, and
                optionally ``span``.

        Returns:
            Partial state dict with ``write_ok`` (bool), ``block_id``
            (str), and ``write_ms`` (float).
        """
        session = state.get("agentmem_session")
        user = state.get("agentmem_user")
        fact = state.get("final_fact", "")
        annotations = state.get("annotations", {})

        if not fact:
            return {"write_ok": False, "block_id": "", "write_ms": 0.0}

        # If the guest has no session yet (e.g. brand-new user that never
        # chatted), spin up a dedicated 'staff_notes' session so the fact
        # has a place to live.
        if session is None and user is not None:
            # Try to get an existing session first, then create if none found.
            try:
                session_list = user.list_sessions()
                existing = getattr(session_list, "sessions", None) or []
                if existing:
                    session = user.get_session(session_id=existing[0].session_id)
            except Exception:
                pass
        if session is None and user is not None:
            try:
                session = user.create_session(
                    session_id="staff_notes",
                    annotations={"source": "staff_call_log"},
                )
            except Exception as exc:
                print(
                    f"  [call-note-agent] could not create staff_notes session: {exc}"
                )
                return {"write_ok": False, "block_id": "", "write_ms": 0.0}

        if session is None:
            return {"write_ok": False, "block_id": "", "write_ms": 0.0}

        span = state.get("span")
        ctx = span.new("write") if span is not None else contextlib.nullcontext()
        with ctx as s:
            call_id = uuid.uuid4().hex
            if s is not None and _AGENTC:
                try:
                    s.log(
                        ToolCallContent(
                            tool_name="add_memory",
                            tool_args={"fact": fact[:200], "annotations": annotations},
                            tool_call_id=call_id,
                        )
                    )
                except Exception as exc:
                    print(f"  [agentc] log failed: {exc}")

            t0 = time.time()
            block_id = ""
            try:
                result = session.add_memory(
                    facts=[fact],
                    annotations=annotations,
                    async_processing=False,  # block until indexed so rescans see it
                    context_required=True,
                )
                # add_memory may return either a list[MemoryBlock] or None.
                if result:
                    first = (
                        result[0]
                        if isinstance(result, (list, tuple)) and result
                        else None
                    )
                    if first is not None:
                        block_id = getattr(first, "block_id", "") or ""
                write_ok = True
            except Exception as exc:  # pragma: no cover - defensive
                print(f"  [call-note-agent] write failed: {exc}")
                write_ok = False
            write_ms = (time.time() - t0) * 1000

            if s is not None and _AGENTC:
                try:
                    s.log(
                        ToolResultContent(
                            tool_call_id=call_id,
                            tool_result=f"write_ok={write_ok} block_id={block_id}",
                        )
                    )
                except Exception as exc:
                    print(f"  [agentc] log failed: {exc}")

        return {"write_ok": write_ok, "block_id": block_id, "write_ms": write_ms}


# ──────────────────────────────────────────────────────────────
# Compiled graph
# ──────────────────────────────────────────────────────────────


class CallNoteAgent:
    """Convenience handle that exposes the classify node externally.

    Most callers should use :class:`CallNoteGraph`; this class exists so
    the agent has a name parallel to the other ops agents
    (BriefingAgent, FlagAgent, DigestAgent, GroupEventBriefAgent).
    """

    def __init__(self, llm: ChatOpenAI) -> None:
        self.llm = llm
        self._classify = _ClassifyNode(llm=llm)

    def classify(self, state: dict) -> dict:
        """Classify the staff note into a structured fact.

        Delegates to the internal :class:`_ClassifyNode`. See
        :meth:`_ClassifyNode.node` for Args and Returns details.
        """
        return self._classify.node(state)


class CallNoteGraph:
    """Compiled LangGraph for the call-note ingestion workflow.

    Topology::

        START → classify → memory-search → enrich → write → END
    """

    def __init__(self, model: str | None = None, temperature: float = 0.0) -> None:
        _model = model or os.getenv("MODEL", "gpt-4o-mini")
        llm = ChatOpenAI(model=_model, temperature=temperature)
        self.call_note_agent = CallNoteAgent(llm=llm)
        self.memory_node = _MemorySearchNode()
        self.enrich_node = _EnrichNode()
        self.write_node = _WriteNode()
        self._graph = self._build()

    def _build(self):
        """Compile the call-note LangGraph state graph."""
        builder = StateGraph(CallNoteState)
        builder.add_node("classify", self.call_note_agent.classify)
        builder.add_node("memory-search", self.memory_node.node)
        builder.add_node("enrich", self.enrich_node.node)
        builder.add_node("write", self.write_node.node)
        builder.add_edge(START, "classify")
        builder.add_edge("classify", "memory-search")
        builder.add_edge("memory-search", "enrich")
        builder.add_edge("enrich", "write")
        builder.add_edge("write", END)
        return builder.compile()

    def run(
        self,
        *,
        client,
        agentmem_session,
        agentmem_user,
        guest_id: str,
        guest_name: str,
        raw_note: str,
        staff_category: str,
        logged_by_role: str,
        logged_by_role_name: str,
        timestamp: str,
        span=None,
    ) -> dict:
        """Run the call-note ingestion pipeline for a single staff note.

        Args:
            client: Couchbase Agent Memory client instance.
            agentmem_session: Active Couchbase Agent Memory session for the guest,
                or ``None`` if no session exists yet.
            agentmem_user: Couchbase Agent Memory user object for the guest.
            guest_id: User identifier for the guest.
            guest_name: Display name of the guest.
            raw_note: Free-text note entered by the staff member.
            staff_category: Category selected by the staff member
                (e.g. ``"complaint"``, ``"allergy"``).
            logged_by_role: Role identifier of the staff member logging the note.
            logged_by_role_name: Human-readable role name of the staff member.
            timestamp: ISO-8601 or human-readable timestamp of the interaction.
            span: Optional agentc tracing span.

        Returns:
            Final LangGraph state dict. Key fields: ``write_ok`` (bool),
            ``block_id`` (str), ``classified_category`` (str),
            ``canonical_fact`` (str), ``classify_ms`` (float),
            ``retrieval_ms`` (float), ``write_ms`` (float).
        """
        state: dict = {
            "client": client,
            "agentmem_session": agentmem_session,
            "agentmem_user": agentmem_user,
            "guest_id": guest_id,
            "guest_name": guest_name,
            "raw_note": raw_note,
            "staff_category": staff_category,
            "logged_by_role": logged_by_role,
            "logged_by_role_name": logged_by_role_name,
            "timestamp": timestamp,
            "span": span,
        }
        return self._graph.invoke(state)
