"""
Monthly operations digest agent (ops side).

Trigger: schedule (monthly) - or a manual "Run digest now" button on
the ops UI. Non-chat - produces a structured report aggregating
patterns across many guests.

Pipeline::

    START → multi-user-memory-fan-out → digest-agent → END

Reads: a representative session per guest, querying across all sessions
for each user in parallel.
Writes: digest report into the ``role_gm`` memory pool - so a new GM
joining inherits the historical pattern record (role-based memory).
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

from prompts import OPS_DIGEST_TEMPLATE, renderer

from ._ops_utils import get_user_session, safe_parse_json, write_artifact_to_role
from .config import MEMORY_K
from .memory_toolkit import format_memories, search_memories_multi_user

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


DIGEST_QUERIES = [
    "complaint issue problem",
    "wait delay slow",
    "request preference repeat",
    "spend booking loyalty",
    "allergy dietary safety",
    "event group facilities",
    "compliment positive feedback",
]


class DigestState(TypedDict, total=False):
    client: Any
    user_list: list
    period: str
    memory_context: str
    digest: dict
    write_ok: bool
    retrieval_ms: float
    synthesis_ms: float
    span: Optional[object]


class DigestAgent:
    """LangGraph node: synthesise a monthly ops digest from aggregated memory.

    Args:
        llm: Initialised LangChain LLM instance used for digest synthesis.
    """

    def __init__(self, llm: ChatOpenAI) -> None:
        self.llm = llm

    def node(self, state: dict) -> dict:
        """Synthesise a monthly ops digest JSON from aggregated multi-user memory.

        Args:
            state: LangGraph state dict. Expected keys: ``period``,
                ``user_list``, ``memory_context``, ``client``, and
                optionally ``span``.

        Returns:
            Partial state dict with ``digest`` (dict), ``write_ok``
            (bool), and ``synthesis_ms`` (float).
        """
        guest_count = len(state.get("user_list", []))
        prompt = renderer.render(
            OPS_DIGEST_TEMPLATE,
            period=state.get("period", ""),
            guest_count=guest_count,
            memory_context=state.get("memory_context", ""),
        )
        span = state.get("span")
        ctx = span.new("digest-agent") if span is not None else contextlib.nullcontext()
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

        parsed = safe_parse_json(response.content) or {
            "period": state.get("period", ""),
            "headline": "Insufficient memory to compose digest.",
            "recurring_complaints": [],
            "recurring_requests": [],
            "spend_or_loyalty_signals": [],
            "operational_action_items": [],
        }

        write_ok = False
        client = state.get("client")
        if client is not None:
            write_ok = write_artifact_to_role(
                client=client,
                role_id="role_gm",
                role_name="General Manager",
                artifact=parsed,
                artifact_type="monthly_ops_digest",
                ref_user=None,
            )
        return {
            "digest": parsed,
            "write_ok": write_ok,
            "synthesis_ms": synthesis_ms,
        }


class _MultiUserFanOutNode:
    """Multi-user fan-out node, the only multi-user search in the codebase.

    Pulls memories for every (user_id, session) pair across DIGEST_QUERIES,
    then renders a single grouped-by-guest dump for the synthesis prompt.
    Cap is doubled vs single-user agents because aggregation across many
    guests legitimately needs more excerpts.
    """

    def node(self, state: dict) -> dict:
        """Fan out memory searches across all users and aggregate results.

        Args:
            state: LangGraph state dict. Expected keys: ``user_list``
                (list of (user_id, user_object) pairs) and optionally
                ``span``.

        Returns:
            Partial state dict with ``memory_context`` (str) and
            ``retrieval_ms`` (float).
        """
        # Ops UI passes (user_id, user_object) pairs for consistency
        # with every other agent's "agentmem_user" contract; the toolkit
        # primitive needs (user_id, session) pairs because it calls
        # `session.get_memory(...)`. Resolve each user to a session here.
        user_list = state.get("user_list") or []
        if not user_list:
            return {"memory_context": "", "retrieval_ms": 0.0}

        client = state.get("client")
        user_sessions: list[tuple[str, Any]] = []
        for uid, user in user_list:
            if user is None:
                continue
            sess = get_user_session(user, client=client, user_id=uid)
            if sess is not None:
                user_sessions.append((uid, sess))
        if not user_sessions:
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
                            tool_name="search_memories_multi_user",
                            tool_args={"queries": DIGEST_QUERIES},
                            tool_call_id=call_id,
                        )
                    )
                except Exception as exc:
                    print(f"  [agentc] log failed: {exc}")

            t0 = time.time()
            records = search_memories_multi_user(
                user_sessions=user_sessions,
                queries=DIGEST_QUERIES,
                k=MEMORY_K["digest"],
            )
            memory_context = format_memories(records, group_by_user=True)
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

        return {"memory_context": memory_context, "retrieval_ms": retrieval_ms}


class DigestGraph:
    """Compiled LangGraph for the monthly ops digest workflow.

    Topology::

        START → multi-user-memory-fan-out → digest-agent → END
    """

    def __init__(self, model: str | None = None, temperature: float = 0.1) -> None:
        _model = model or os.getenv("MODEL", "gpt-4o-mini")
        llm = ChatOpenAI(model=_model, temperature=temperature)
        self.digest_agent = DigestAgent(llm=llm)
        self.fan_out = _MultiUserFanOutNode()
        self._graph = self._build()

    def _build(self):
        """Compile the digest LangGraph state graph."""
        builder = StateGraph(DigestState)
        builder.add_node("multi-user-memory-fan-out", self.fan_out.node)
        builder.add_node("digest-agent", self.digest_agent.node)
        builder.add_edge(START, "multi-user-memory-fan-out")
        builder.add_edge("multi-user-memory-fan-out", "digest-agent")
        builder.add_edge("digest-agent", END)
        return builder.compile()

    def run(
        self,
        client,
        user_list: list[tuple[str, Any]],
        period: str,
        span=None,
    ) -> dict:
        """Run the digest pipeline across a list of guest users.

        Args:
            client: Couchbase Agent Memory client instance.
            user_list: List of ``(user_id, user_object)`` pairs to aggregate.
            period: Human-readable period label for the digest (e.g. ``"May 2026"``).
            span: Optional agentc tracing span.

        Returns:
            Final LangGraph state dict. Key fields: ``digest`` (dict),
            ``write_ok`` (bool), ``retrieval_ms`` (float),
            ``synthesis_ms`` (float).
        """
        state: dict = {
            "client": client,
            "user_list": user_list,
            "period": period,
            "memory_context": "",
            "span": span,
        }
        return self._graph.invoke(state)
