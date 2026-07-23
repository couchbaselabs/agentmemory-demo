"""
Guest-facing concierge LangGraph workflow.

Topology::

    START → memory-retrieval → response-agent → END

The memory-retrieval node fires the user's raw query as a single
Couchbase Agent Memory search via :func:`search_memories` and renders
the result with :func:`format_memories`. Single-query (no rewriter
fan-out) keeps chat latency consistently sub-second.

Reads and writes the shared Couchbase-backed Couchbase Agent Memory
store. All other agents in this package read from the same store.
"""

from __future__ import annotations

import contextlib
import os
import time
import uuid
from typing import Annotated, Optional

from agentmemory import ChatMessage
from langchain_core.messages import AnyMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from prompts import NO_MEMORY_TEMPLATE, WITH_MEMORY_TEMPLATE, renderer

from dataclasses import asdict

from .config import MEMORY_K, QUERY_REWRITER_N
from .memory_toolkit import QueryRewriter, format_memories, search_memories

try:
    from agentc_core.activity.models.content import (
        AssistantContent,
        ChatCompletionContent,
        EdgeContent,
        KeyValueContent,
        SystemContent,
        ToolCallContent,
        ToolResultContent,
    )

    _AGENTC = True
except ImportError:
    _AGENTC = False


class ConciergeState(TypedDict):
    """LangGraph state for the concierge workflow."""

    agentmem_session: object
    messages: Annotated[list[AnyMessage], add_messages]
    user_query: str
    refined_queries: list[str]  # set by query-rewriter; used by memory-retrieval
    speaker_name: Optional[str]
    use_memory: bool
    memory_context: str
    assistant_response: str
    conversation_history: list[dict]
    memory_write_ms: float
    retrieval_ms: float
    memory_records: list[dict]
    span: Optional[object]


class MemoryRetrievalNode:
    """Deterministic retrieval node for the concierge pipeline.

    Fires the user's raw query as a single Couchbase Agent Memory
    search and renders the result with :func:`format_memories`.
    Single-query (no rewriter fan-out) keeps chat latency consistently
    sub-second; ops agents that fan out across multiple queries tolerate
    the tail because they're synchronous batch triggers, not chat.

    Args:
        k: ``relevant_k`` per query. Pull from MEMORY_K["concierge"].
    """

    def __init__(self, k: int = MEMORY_K["concierge"]) -> None:
        self.k = k

    def node(self, state: dict) -> dict:
        """Retrieve relevant memories for the current user query.

        Args:
            state: LangGraph state dict with keys ``agentmem_session``,
                ``user_query``, ``refined_queries``, ``use_memory``,
                and optionally ``span``.

        Returns:
            Partial state dict with ``memory_context`` (str),
            ``retrieval_ms`` (float), and ``memory_records`` (list[dict]).
        """
        if not state.get("use_memory", True):
            return {
                "memory_context": "",
                "retrieval_ms": 0.0,
                "memory_records": [],
            }

        session = state.get("agentmem_session")
        user_query = state.get("user_query", "")
        # Prefer the rewriter's expanded queries; fall back to raw query.
        queries = state.get("refined_queries") or ([user_query] if user_query else [])
        if session is None or not queries:
            return {
                "memory_context": "",
                "retrieval_ms": 0.0,
                "memory_records": [],
            }

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
                            tool_name="search_memory",
                            tool_args={"queries": queries},
                            tool_call_id=call_id,
                        )
                    )
                except Exception as exc:
                    print(f"  [agentc] log failed: {exc}")

            t0 = time.time()
            records = search_memories(session, queries, k=self.k)
            memory_context = format_memories(records) or "No relevant memories found."
            retrieval_ms = (time.time() - t0) * 1000

            if s is not None and _AGENTC:
                try:
                    s.log(
                        ToolResultContent(
                            tool_call_id=call_id,
                            tool_result=f"{len(records)} records retrieved",
                        )
                    )
                    s.log(KeyValueContent(key="memory_context", value=memory_context))
                    s.log(
                        EdgeContent(
                            source=["hotel-concierge", "memory-retrieval"],
                            dest=["hotel-concierge", "response-agent"],
                        )
                    )
                except Exception as exc:
                    print(f"  [agentc] log failed: {exc}")

        # Serialise records to dicts so they survive LangGraph state
        # passing and Streamlit session_state pickling untouched.
        memory_records = [asdict(r) for r in records]

        return {
            "memory_context": memory_context,
            "retrieval_ms": retrieval_ms,
            "memory_records": memory_records,
        }


class ConciergeResponseAgent:
    """LangGraph node that generates the concierge reply and persists the
    new turn back into Couchbase Agent Memory.

    Accepts hotel-flavoured prompt templates and tracks write latency
    for the Streamlit pipeline view.
    """

    def __init__(
        self,
        llm: ChatOpenAI,
        with_memory_template: str | None = None,
        no_memory_template: str | None = None,
    ) -> None:
        self.llm = llm
        self.with_memory_template = with_memory_template or WITH_MEMORY_TEMPLATE
        self.no_memory_template = no_memory_template or NO_MEMORY_TEMPLATE

    def node(self, state: dict) -> dict:
        """Generate the concierge reply and persist the turn to memory.

        Args:
            state: LangGraph state dict. Must contain ``user_query``,
                ``agentmem_session``, ``use_memory``, ``memory_context``,
                ``conversation_history``, and optionally ``span``.

        Returns:
            Partial state dict with ``assistant_response`` (str),
            ``conversation_history`` (list[dict]), and
            ``memory_write_ms`` (float).
        """
        use_memory = state.get("use_memory", True)
        query = state["user_query"]
        memory_ctx = state.get("memory_context", "")
        history = state.get("conversation_history", [])
        span = state.get("span")

        template = self.with_memory_template if use_memory else self.no_memory_template
        prompt = renderer.render(
            template,
            query=query,
            memory_context=memory_ctx,
            conversation_history=history or None,
        )

        ctx = (
            span.new("concierge-response")
            if span is not None
            else contextlib.nullcontext()
        )
        with ctx as s:
            if s is not None and _AGENTC:
                try:
                    s.log(SystemContent(value=prompt))
                except Exception as exc:
                    print(f"  [agentc] log failed: {exc}")

            response = self.llm.invoke([HumanMessage(content=prompt)])
            reply = response.content.strip()

            if s is not None and _AGENTC:
                try:
                    s.log(ChatCompletionContent(output=reply))
                except Exception as exc:
                    print(f"  [agentc] log failed: {exc}")

            memory_write_ms = 0.0
            if use_memory:
                session = state["agentmem_session"]
                write_call_id = uuid.uuid4().hex
                if s is not None and _AGENTC:
                    try:
                        s.log(
                            ToolCallContent(
                                tool_name="add_memory",
                                tool_args={
                                    "user_query": query,
                                    "assistant_response": reply[:200],
                                },
                                tool_call_id=write_call_id,
                            )
                        )
                    except Exception as exc:
                        print(f"  [agentc] log failed: {exc}")
                try:
                    t0 = time.time()
                    session.add_memory(
                        messages=[
                            ChatMessage(user_content=query, assistant_content=reply)
                        ],
                        annotations={"source": "concierge_agent"},
                        async_processing=True,
                    )
                    memory_write_ms = (time.time() - t0) * 1000
                    if s is not None and _AGENTC:
                        try:
                            s.log(
                                ToolResultContent(
                                    tool_call_id=write_call_id,
                                    tool_result=f"stored in {memory_write_ms:.0f}ms",
                                )
                            )
                        except Exception as exc:
                            print(f"  [agentc] log failed: {exc}")
                except Exception as exc:
                    print(f"  [concierge-response] warning: write failed - {exc}")

            if s is not None and _AGENTC:
                try:
                    s.log(AssistantContent(value=reply))
                except Exception as exc:
                    print(f"  [agentc] log failed: {exc}")

        updated_history = list(history)
        updated_history.append({"user_content": query, "assistant_content": reply})

        return {
            "assistant_response": reply,
            "conversation_history": updated_history,
            "memory_write_ms": memory_write_ms,
        }


class ConciergeGraph:
    """Compiled LangGraph for the guest-facing concierge.

    Topology::

        START → query-rewriter → memory-retrieval → response-agent → END

    The query-rewriter expands the guest's raw message into 2–4 focused
    retrieval queries (including a safety/allergy angle on every turn) so
    the memory search surfaces relevant history even when the guest's words
    don't directly match stored fact terminology.

    Args:
        session: Active guest Couchbase Agent Memory session (e.g. Alice's session_5).
        model: OpenAI model name. Falls back to MODEL env var, then gpt-4o-mini.
        temperature: LLM sampling temperature for the response agent.
        top_k: Memory blocks retrieved per search call.
        with_memory_template: Optional hotel-flavoured prompt override for
            queries with memory context.
        no_memory_template: Optional hotel-flavoured prompt override for
            queries without memory context.
    """

    def __init__(
        self,
        session,
        model: str | None = None,
        temperature: float = 0.3,
        top_k: int = MEMORY_K["concierge"],
        with_memory_template: str | None = None,
        no_memory_template: str | None = None,
    ) -> None:
        self.session = session
        _model = model or os.getenv("MODEL", "gpt-4o-mini")
        llm = ChatOpenAI(model=_model, temperature=temperature)

        # Query rewriter uses temperature=0 — deterministic expansion, not creative.
        rewriter_llm = ChatOpenAI(model=_model, temperature=0.0)
        self.query_rewriter = QueryRewriter(llm=rewriter_llm, n=QUERY_REWRITER_N)
        self.memory_node = MemoryRetrievalNode(k=top_k)
        self.response_agent = ConciergeResponseAgent(
            llm=llm,
            with_memory_template=with_memory_template,
            no_memory_template=no_memory_template,
        )
        self._graph = self._build()
        self.conversation_history: list[dict] = []

    def _build(self):
        """Compile the concierge LangGraph state graph."""
        builder = StateGraph(ConciergeState)
        builder.add_node("query-rewriter", self.query_rewriter.node)
        builder.add_node("memory-retrieval", self.memory_node.node)
        builder.add_node("response-agent", self.response_agent.node)

        builder.add_edge(START, "query-rewriter")
        builder.add_edge("query-rewriter", "memory-retrieval")
        builder.add_edge("memory-retrieval", "response-agent")
        builder.add_edge("response-agent", END)
        return builder.compile()

    def run(
        self,
        query: str,
        use_memory: bool = True,
        speaker_name: str | None = None,
        span=None,
    ) -> dict:
        """Run the concierge pipeline for a single guest turn.

        Args:
            query: The guest's raw message.
            use_memory: Whether to retrieve and write memories.
            speaker_name: Optional display name override for the guest.
            span: Optional agentc tracing span.

        Returns:
            Final LangGraph state dict. Key fields: ``assistant_response``
            (str), ``retrieval_ms`` (float), ``memory_write_ms`` (float),
            ``memory_records`` (list[dict]), ``memory_context`` (str).
        """
        # Cap conversation history at the last 10 turns (5 user+assistant pairs)
        # so the prompt size stays bounded as the conversation grows. Memory
        # retrieval provides cross-session context for older turns anyway.
        _MAX_HISTORY_TURNS = 10
        state: dict = {
            "agentmem_session": self.session,
            "messages": [HumanMessage(content=query)],
            "user_query": query,
            "refined_queries": [],  # populated by the query-rewriter node
            "speaker_name": speaker_name,
            "use_memory": use_memory,
            "memory_context": "",
            "assistant_response": "",
            "conversation_history": list(
                self.conversation_history[-_MAX_HISTORY_TURNS:]
            ),
            "memory_write_ms": 0.0,
            "span": span,
        }
        result = self._graph.invoke(state)
        self.conversation_history = list(result.get("conversation_history", []))
        return result

    def reset_history(self) -> None:
        """Clear the in-memory conversation history for this graph instance."""
        self.conversation_history = []
