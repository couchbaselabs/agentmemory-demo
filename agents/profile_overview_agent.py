"""
Profile-overview synthesis agent (guest UI side).

Trigger: guest UI loading or refreshing the profile card. Non-chat -
produces a structured profile dict (visits, preferences, dislikes,
complaints).

Pipeline::

    START → memory-retrieval → profile-overview-agent → END

Reads: the guest's full memory across all sessions (cross-session fan-out).
Writes: nothing - this is a read-only synthesis surface.

Lifted out of ``agentmem_hotel.py`` so the UI is "just call the agent"
rather than inlining a bespoke retrieval + LLM pipeline. Same
``(prompt, K, queries)`` shape as every other agent in this package.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import time
import uuid
from typing import Any, Optional, TypedDict

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from prompts import PROFILE_OVERVIEW_TEMPLATE, renderer

from ._ops_utils import get_user_session
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


class ProfileOverviewState(TypedDict, total=False):
    agentmem_user: Any
    agentmem_session: (
        Any  # optional: pre-loaded session avoids an extra list_sessions() call
    )
    guest_id: str
    guest_name: str
    memory_context: str
    profile: dict
    retrieval_ms: float
    synthesis_ms: float
    span: Optional[object]


# ──────────────────────────────────────────────────────────────────────────────
# Profile parsing (kept agent-local; see _parse_profile in agentmem_hotel.py
# for the legacy implementation this replaces - the simplified version
# below relies on the prompt's strict JSON contract).
# ──────────────────────────────────────────────────────────────────────────────


_PLACEHOLDERS = {
    "",
    "none",
    "none mentioned",
    "n/a",
    "na",
    "unknown",
    "no preferences",
    "no dislikes",
    "no complaints",
}


def _is_placeholder(text: str) -> bool:
    return text.strip().lower() in _PLACEHOLDERS


def _normalise(item: Any) -> str:
    s = str(item or "").strip()
    s = s.strip("-•*\"'").strip()
    return s


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for it in items:
        key = it.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _parse_profile(text: str) -> dict:
    """Parse the LLM's JSON output into the profile dict expected by the UI.

    Strategy: strict JSON parse first; tolerant fallback that finds the
    first ``{...}`` block in the response.
    """
    visits = 0
    preferences: list[str] = []
    dislikes: list[str] = []
    complaints: list[str] = []

    raw = (text or "").strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, re.DOTALL | re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()

    parsed: dict | None = None
    if raw:
        try:
            parsed = json.loads(raw)
        except Exception:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except Exception as exc:
                    print(f"warning: profile JSON fallback parse failed — {exc}")
                    parsed = None

    if isinstance(parsed, dict):
        try:
            visits = int(parsed.get("visits", 0) or 0)
        except (TypeError, ValueError):
            visits = 0

        def _list(key: str) -> list[str]:
            raw_list = parsed.get(key, [])
            if isinstance(raw_list, str):
                raw_list = [p for p in raw_list.split(",")]
            if not isinstance(raw_list, (list, tuple)):
                return []
            cleaned = [_normalise(x) for x in raw_list]
            return [c for c in cleaned if c and not _is_placeholder(c)]

        preferences = _dedupe(_list("preferences"))
        dislikes = _dedupe(_list("dislikes"))
        complaints = _dedupe(_list("complaints"))

    def _join(items: list[str]) -> str:
        return ", ".join(items) if items else "None mentioned"

    return {
        "visits": visits,
        "preferences": _join(preferences),
        "dislikes": _join(dislikes),
        "complaints": _join(complaints),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Synthesis node
# ──────────────────────────────────────────────────────────────────────────────


class ProfileOverviewAgent:
    """LangGraph node: synthesise a guest profile from cross-session memory.

    Args:
        llm: Initialised LangChain LLM instance used for profile synthesis.
    """

    def __init__(self, llm: ChatOpenAI) -> None:
        self.llm = llm

    def node(self, state: dict) -> dict:
        """Synthesise a structured guest profile dict from retrieved memory.

        Returns a no-memory sentinel dict (``"empty": True``) if no
        memory context is available, avoiding an unnecessary LLM call.

        Args:
            state: LangGraph state dict. Expected keys: ``memory_context``
                and optionally ``span``.

        Returns:
            Partial state dict with ``profile`` (dict) and
            ``synthesis_ms`` (float). The ``profile`` dict has keys
            ``visits`` (int), ``preferences`` (str), ``dislikes`` (str),
            and ``complaints`` (str).
        """
        memory_context = state.get("memory_context", "")
        if not memory_context:
            return {
                "profile": {
                    "visits": 0,
                    "preferences": "No memories for user yet",
                    "dislikes": "No memories for user yet",
                    "complaints": "No memories for user yet",
                    "empty": True,
                },
                "synthesis_ms": 0.0,
            }

        prompt = renderer.render(PROFILE_OVERVIEW_TEMPLATE, history=memory_context)
        span = state.get("span")
        ctx = (
            span.new("profile-overview-agent")
            if span is not None
            else contextlib.nullcontext()
        )
        with ctx as s:
            if s is not None and _AGENTC:
                try:
                    s.log(SystemContent(value=prompt))
                except Exception as exc:
                    print(f"  [agentc] log failed: {exc}")

            t0 = time.time()
            response = self.llm.invoke([HumanMessage(content=prompt)])
            synthesis_ms = (time.time() - t0) * 1000

            if s is not None and _AGENTC:
                try:
                    s.log(ChatCompletionContent(output=response.content.strip()))
                except Exception as exc:
                    print(f"  [agentc] log failed: {exc}")

        profile = _parse_profile(response.content or "")
        return {"profile": profile, "synthesis_ms": synthesis_ms}


class ProfileOverviewGraph:
    """Compiled LangGraph for the profile-overview workflow.

    Fans out 10 short keyword queries (one per profile dimension - visits,
    preferences, dislikes, complaints, allergies, accessibility) so each
    angle's vector search is sharp; long natural-language questions
    retrieve worse than tight noun-phrases in dense vector search.

    Topology::

        START → memory-retrieval → profile-overview-agent → END
    """

    def __init__(self, model: str | None = None, temperature: float = 0.1) -> None:
        _model = model or os.getenv("MODEL", "gpt-4o-mini")
        llm = ChatOpenAI(model=_model, temperature=temperature)
        self.profile_agent = ProfileOverviewAgent(llm=llm)
        self._graph = self._build()

    def _memory_retrieval_node(self, state: dict) -> dict:
        """Multi-dimensional keyword retrieval for comprehensive profile.

        Fans out short keyword phrases (one per profile dimension) so
        each angle's vector search is sharp. Long natural-language
        questions retrieve worse than short noun-phrases in dense
        vector search - the embedding gets diluted across function
        words. Each dimension gets its own dedicated query so old
        guest-specific items don't get swamped by newer ones.

        Searches across all user sessions automatically.
        """
        import time as _time
        from .memory_toolkit import format_memories

        user = state.get("agentmem_user")
        if user is None:
            return {"memory_context": "", "retrieval_ms": 0.0}

        # Use a pre-loaded session if the caller provided one (saves two API
        # calls — list_sessions + get_session). Fall back to get_user_session
        # when called without a session (e.g. from tests or ops portal).
        client = state.get("client") or state.get("agentmem_client")
        user_id = state.get("guest_id") or state.get("user_id")
        session = state.get("agentmem_session") or get_user_session(
            user, client=client, user_id=user_id
        )
        if session is None:
            return {"memory_context": "", "retrieval_ms": 0.0}

        # Short keyword angles, one per profile dimension. Multiple
        # queries per dimension surface different memories and the
        # block_id dedup merges duplicates.
        #
        # Query design: use vocabulary that MATCHES how SDK-generated
        # summaries describe hotel conversations. Overly abstract terms
        # ("dislike", "complaint") may not match summaries that say
        # "concern", "issue", "was not happy with" etc.
        profile_queries = [
            # Visit/stay history
            "hotel visit stay booking reservation check-in",
            # Preferences (positive) — broad vocabulary
            "guest preference enjoy like favourite request",
            "room floor view type amenity service preferred",
            "dining food cuisine drink restaurant menu",
            # Dislikes — natural-language variants the SDK might use
            "guest avoids does not like dislike sensitivity exclude",
            "food preference dietary avoid restrict not eat",
            # Complaints — many ways hotel failures appear in summaries
            "guest concern complaint unhappy disappointed dissatisfied",
            "hotel service issue problem slow delay staff response",
            "room maintenance noise temperature broken facility issue",
            "event technical wifi connectivity AV failure problem",
            # Safety / medical — kept specific for precision
            "allergy allergic anaphylaxis intolerance severe reaction",
            "dietary restriction medical condition health disability",
            "mobility wheelchair accessibility assistance need",
        ]

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
                            tool_args={
                                "queries": profile_queries,
                                "k": MEMORY_K["profile_overview"],
                            },
                            tool_call_id=call_id,
                        )
                    )
                except Exception as exc:
                    print(f"  [agentc] log failed: {exc}")

            t0 = _time.time()
            records = search_memories(
                session,
                profile_queries,
                k=MEMORY_K["profile_overview"],
                cross_session=True,
            )

            # Newest first inside each section so the LLM sees recent items
            # at the top of each bucket; old items still appear below.
            records.sort(key=lambda r: r.timestamp or "", reverse=True)

            memory_context = format_memories(records, include_block_ids=False)

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

    def _build(self):
        """Compile the profile-overview LangGraph state graph."""
        builder = StateGraph(ProfileOverviewState)
        builder.add_node("memory-retrieval", self._memory_retrieval_node)
        builder.add_node("profile-overview-agent", self.profile_agent.node)
        builder.add_edge(START, "memory-retrieval")
        builder.add_edge("memory-retrieval", "profile-overview-agent")
        builder.add_edge("profile-overview-agent", END)
        return builder.compile()

    def run(
        self,
        agentmem_user,
        guest_id: str = "",
        guest_name: str = "",
        agentmem_session=None,
        client=None,
        span=None,
    ) -> dict:
        """Run the profile-overview pipeline for a single guest.

        Args:
            agentmem_user: Couchbase Agent Memory user object for the guest.
            guest_id: User identifier for the guest.
            guest_name: Display name of the guest.
            agentmem_session: Optional pre-loaded Couchbase Agent Memory session.
                Providing this avoids an extra ``list_sessions()`` API call;
                if ``None`` the node falls back to :func:`get_user_session`.
            span: Optional agentc tracing span.

        Returns:
            Final LangGraph state dict. Key fields: ``profile`` (dict),
            ``retrieval_ms`` (float), ``synthesis_ms`` (float).
        """
        state: dict = {
            "agentmem_user": agentmem_user,
            "agentmem_session": agentmem_session,  # None → falls back to get_user_session
            "client": client,
            "guest_id": guest_id,
            "guest_name": guest_name,
            "memory_context": "",
            "span": span,
        }
        return self._graph.invoke(state)
