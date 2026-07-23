"""
Group-event facilities pre-brief agent (ops side).

Trigger: a new group booking is confirmed (form submission). Non-chat.

Pipeline::

    START → memory-search (organiser, past events) → group-event-brief-agent → END

Reads: the organiser's full memory across all past events.
Writes: facilities brief back into the ``role_events`` memory pool so
any future events coordinator inherits the institutional knowledge.

The organiser is NOT a guest in the room - they book on behalf of an
attendee group. This agent demonstrates indirect-relationship reasoning
(Charlie booking for 30+ attendees) and contradiction resolution
(positive feedback from one event vs. failures at another).
"""

from __future__ import annotations

import contextlib
import os
import time
from typing import Any, Optional, TypedDict

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from prompts import GROUP_EVENT_BRIEF_TEMPLATE, renderer

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


GROUP_EVENT_QUERIES = [
    "event past failure issue complaint AV breakout",
    "accessibility wheelchair mobility ramp",
    "privacy confidentiality executive retreat",
    "catering dietary group meal allergy",
    "schedule logistics setup teardown",
    "attendee feedback post-event",
    "room reservation block accessible",
]


class GroupEventBriefState(TypedDict, total=False):
    client: Any
    agentmem_user: Any
    organiser_id: str
    organiser_name: str
    event_date: str
    attendee_count: int
    memory_context: str
    brief: dict
    write_ok: bool
    retrieval_ms: float
    synthesis_ms: float
    span: Optional[object]


class GroupEventBriefAgent:
    """LangGraph node: synthesise a facilities brief for a new group event.

    Args:
        llm: Initialised LangChain LLM instance used for brief synthesis.
    """

    def __init__(self, llm: ChatOpenAI) -> None:
        self.llm = llm

    def node(self, state: dict) -> dict:
        """Synthesise a structured facilities brief JSON from retrieved memory.

        Args:
            state: LangGraph state dict. Expected keys: ``organiser_name``,
                ``event_date``, ``attendee_count``, ``memory_context``,
                ``client``, ``organiser_id``, and optionally ``span``.

        Returns:
            Partial state dict with ``brief`` (dict), ``write_ok``
            (bool), and ``synthesis_ms`` (float).
        """
        prompt = renderer.render(
            GROUP_EVENT_BRIEF_TEMPLATE,
            organiser_name=state.get("organiser_name", ""),
            event_date=state.get("event_date", ""),
            attendee_count=state.get("attendee_count", 0),
            memory_context=state.get("memory_context", ""),
        )
        span = state.get("span")
        ctx = (
            span.new("group-event-brief-agent")
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

        parsed = safe_parse_json(response.content) or {
            "organiser": state.get("organiser_name", ""),
            "event_date": state.get("event_date", ""),
            "attendee_count": state.get("attendee_count", 0),
            "past_failures": [],
            "accessibility_needs": [],
            "privacy_flags": [],
            "facilities_actions": [],
            "summary": "Insufficient memory to compose facilities brief.",
        }

        write_ok = False
        client = state.get("client")
        if client is not None:
            write_ok = write_artifact_to_role(
                client=client,
                role_id="role_events",
                role_name="Events Team",
                artifact=parsed,
                artifact_type="group_event_brief",
                ref_user=state.get("organiser_id"),
            )
        return {
            "brief": parsed,
            "write_ok": write_ok,
            "synthesis_ms": synthesis_ms,
        }


class GroupEventBriefGraph:
    """Compiled LangGraph for the group-event pre-brief workflow.

    Topology::

        START → memory-search → group-event-brief-agent → END
    """

    def __init__(self, model: str | None = None, temperature: float = 0.1) -> None:
        _model = model or os.getenv("MODEL", "gpt-4o-mini")
        llm = ChatOpenAI(model=_model, temperature=temperature)
        self.brief_agent = GroupEventBriefAgent(llm=llm)
        self.memory_node = make_retrieval_node(
            queries=GROUP_EVENT_QUERIES,
            k=MEMORY_K["group_event_brief"],
            include_block_ids=False,
        )
        self._graph = self._build()

    def _build(self):
        """Compile the group-event-brief LangGraph state graph."""
        builder = StateGraph(GroupEventBriefState)
        builder.add_node("memory-search", self.memory_node)
        builder.add_node("group-event-brief-agent", self.brief_agent.node)
        builder.add_edge(START, "memory-search")
        builder.add_edge("memory-search", "group-event-brief-agent")
        builder.add_edge("group-event-brief-agent", END)
        return builder.compile()

    def run(
        self,
        client,
        agentmem_user,
        organiser_id: str,
        organiser_name: str,
        event_date: str,
        attendee_count: int,
        span=None,
    ) -> dict:
        """Run the group-event-brief pipeline for a single booking.

        Args:
            client: Couchbase Agent Memory client instance.
            agentmem_user: Couchbase Agent Memory user object for the organiser.
            organiser_id: User identifier for the event organiser.
            organiser_name: Display name of the event organiser.
            event_date: Human-readable event date string.
            attendee_count: Number of attendees for the event.
            span: Optional agentc tracing span.

        Returns:
            Final LangGraph state dict. Key fields: ``brief`` (dict),
            ``write_ok`` (bool), ``retrieval_ms`` (float),
            ``synthesis_ms`` (float).
        """
        state: dict = {
            "client": client,
            "agentmem_user": agentmem_user,
            "organiser_id": organiser_id,
            "organiser_name": organiser_name,
            "event_date": event_date,
            "attendee_count": attendee_count,
            "memory_context": "",
            "span": span,
        }
        return self._graph.invoke(state)
