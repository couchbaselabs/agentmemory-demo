"""
Pre-arrival guest briefing agent (ops side).

Trigger: timer (countdown to arrival) or manual "Generate now" button
on the ops UI. Non-chat - produces a structured briefing card.

Pipeline::

    START → memory-search (guest_id, all sessions) → briefing-agent → END

Reads: the guest's full memory across every prior session.
Writes: structured briefing JSON back to the ``role_front_desk`` memory
pool, so any front-desk staff (current or future) sees the same brief.
"""

from __future__ import annotations

import contextlib
import os
import time
from typing import Any, Optional, TypedDict

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from prompts import BRIEFING_TEMPLATE, renderer

from ._ops_utils import safe_parse_json, write_artifact_to_role
from .config import MEMORY_K
from .memory_toolkit import make_retrieval_node

try:
    from agentc_core.activity.models.content import (
        ChatCompletionContent,
        SystemContent,
    )

    _AGENTC = True
except ImportError:
    _AGENTC = False


BRIEFING_QUERIES = [
    # Stay preferences & service history
    "room preference pillow bedding floor view temperature",
    "complaint issue problem service dissatisfied",
    "recovery apology compensation upgrade",
    "occasion anniversary birthday celebration honeymoon",
    "loyalty booking frequent guest",
    # Allergy & dietary
    "allergy intolerance cannot eat dietary restriction",
    "strong aversion medical alert EpiPen anaphylaxis",
    # One query naming all major allergen categories so documented allergies rank in top-k
    "seafood shellfish peanut nut gluten dairy milk soy egg allergy",
    # Family / companion safety flags
    "family companion guest allergic cannot have",
    "husband wife spouse child son daughter allergy",
]


class BriefingState(TypedDict, total=False):
    client: Any
    agentmem_user: Any
    guest_id: str
    guest_name: str
    arrival_time: str
    memory_context: str
    briefing: dict
    write_ok: bool
    retrieval_ms: float
    synthesis_ms: float
    span: Optional[object]


class BriefingAgent:
    """LangGraph node: synthesise a pre-arrival briefing JSON.

    Args:
        llm: Initialised LangChain LLM instance used for briefing synthesis.
    """

    def __init__(self, llm: ChatOpenAI) -> None:
        self.llm = llm

    def node(self, state: dict) -> dict:
        """Synthesise a structured pre-arrival briefing JSON from retrieved memory.

        Args:
            state: LangGraph state dict. Expected keys: ``guest_name``,
                ``arrival_time``, ``memory_context``, ``client``,
                ``guest_id``, and optionally ``span``.

        Returns:
            Partial state dict with ``briefing`` (dict), ``write_ok``
            (bool), and ``synthesis_ms`` (float).
        """
        prompt = renderer.render(
            BRIEFING_TEMPLATE,
            guest_name=state.get("guest_name", ""),
            arrival_time=state.get("arrival_time", ""),
            memory_context=state.get("memory_context", ""),
        )
        span = state.get("span")
        ctx = (
            span.new("briefing-agent") if span is not None else contextlib.nullcontext()
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

        parsed = safe_parse_json(response.content) or {
            "guest": state.get("guest_name", ""),
            "arrival": state.get("arrival_time", ""),
            "preferences": [],
            "prior_complaints": [],
            "safety_flags": [],
            "occasion_context": "",
            "recovery_actions": [],
            "summary": "Insufficient memory to brief.",
        }

        write_ok = False
        client = state.get("client")
        if client is not None:
            write_ok = write_artifact_to_role(
                client=client,
                role_id="role_front_desk",
                role_name="Front Desk",
                artifact=parsed,
                artifact_type="pre_arrival_briefing",
                ref_user=state.get("guest_id"),
            )
        return {
            "briefing": parsed,
            "write_ok": write_ok,
            "synthesis_ms": synthesis_ms,
        }


class BriefingGraph:
    """Compiled LangGraph for the pre-arrival briefing workflow.

    Topology::

        START → memory-search → briefing-agent → END
    """

    def __init__(self, model: str | None = None, temperature: float = 0.1) -> None:
        _model = model or os.getenv("MODEL", "gpt-4o-mini")
        llm = ChatOpenAI(model=_model, temperature=temperature)
        self.briefing_agent = BriefingAgent(llm=llm)
        self.memory_node = make_retrieval_node(
            queries=BRIEFING_QUERIES,
            k=MEMORY_K["briefing"],
            include_block_ids=True,
        )
        self._graph = self._build()

    def _build(self):
        """Compile the briefing LangGraph state graph."""
        builder = StateGraph(BriefingState)
        builder.add_node("memory-search", self.memory_node)
        builder.add_node("briefing-agent", self.briefing_agent.node)
        builder.add_edge(START, "memory-search")
        builder.add_edge("memory-search", "briefing-agent")
        builder.add_edge("briefing-agent", END)
        return builder.compile()

    def run(
        self,
        client,
        agentmem_user,
        guest_id: str,
        guest_name: str,
        arrival_time: str,
        span=None,
    ) -> dict:
        """Run the briefing pipeline for a single guest.

        Args:
            client: Couchbase Agent Memory client instance.
            agentmem_user: Couchbase Agent Memory user object for the guest.
            guest_id: User identifier for the guest.
            guest_name: Display name of the guest.
            arrival_time: Human-readable arrival date/time string.
            span: Optional agentc tracing span.

        Returns:
            Final LangGraph state dict. Key fields: ``briefing`` (dict),
            ``write_ok`` (bool), ``retrieval_ms`` (float),
            ``synthesis_ms`` (float).
        """
        state: dict = {
            "client": client,
            "agentmem_user": agentmem_user,
            "guest_id": guest_id,
            "guest_name": guest_name,
            "arrival_time": arrival_time,
            "memory_context": "",
            "span": span,
        }
        return self._graph.invoke(state)
