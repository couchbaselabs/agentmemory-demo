"""
Per-guest safety scan agent (ops side dashboard).

Trigger: ops-UI dashboard load. Non-chat - produces a structured list
of safety items (allergy / dietary / medical / mobility) with severity
ratings and verbatim evidence quotes.

Pipeline::

    START → memory-retrieval → safety-scan-agent → END

Reads: the guest's full memory across all sessions (cross-session
fan-out over a small set of safety-focused queries).
Writes: nothing - this is a read-only synthesis surface that powers the
"Allergy & Safety" dashboard panel.

Replaces the deterministic keyword-match scan that lived inline in
``agentmem_hotel_ops.py``. The keyword-match version surfaced raw
excerpts and made staff infer severity; this version does the inference
in one LLM call so the dashboard can show structured "shellfish allergy
- HIGH" badges with citations.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import time
from typing import Any, Optional, TypedDict

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from prompts import SAFETY_SCAN_TEMPLATE, renderer

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


SAFETY_SCAN_QUERIES = [
    # Allergy & dietary — broad query catches all allergen types; LLM categorises.
    "allergy intolerance cannot eat dietary restriction",
    "strong aversion medical alert EpiPen anaphylaxis avoid",
    # Family / companion safety flags
    "family companion guest allergic cannot have dietary",
    "husband wife spouse child son daughter allergy",
    # Mobility & medical
    "mobility wheelchair accessibility elevator",
    "medical condition health diabetes medication",
]


class SafetyScanState(TypedDict, total=False):
    agentmem_user: Any
    client: Any
    guest_id: str
    guest_name: str
    memory_context: str
    safety_items: list[dict]
    retrieval_ms: float
    synthesis_ms: float
    span: Optional[object]


_VALID_KINDS = {"allergy", "dietary", "medical", "mobility", "other"}
_VALID_SEVERITIES = {"critical", "high", "medium", "low"}


def _parse_items(text: str) -> list[dict]:
    """Parse the LLM JSON output into a clean list of safety items."""
    raw = (text or "").strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, re.DOTALL | re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()

    parsed = None
    try:
        parsed = json.loads(raw)
    except Exception:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except Exception as exc:
                print(f"warning: safety scan JSON fallback parse failed — {exc}")
                parsed = None

    if not isinstance(parsed, dict):
        return []

    raw_items = parsed.get("items", [])
    if not isinstance(raw_items, list):
        return []

    cleaned: list[dict] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "other")).strip().lower() or "other"
        if kind not in _VALID_KINDS:
            kind = "other"
        severity = str(item.get("severity", "low")).strip().lower() or "low"
        if severity not in _VALID_SEVERITIES:
            severity = "low"
        summary = str(item.get("summary", "")).strip()
        evidence = str(item.get("evidence", "")).strip()
        if not summary:
            continue
        cleaned.append(
            {
                "kind": kind,
                "severity": severity,
                "summary": summary,
                "evidence": evidence,
            }
        )
    return cleaned


class SafetyScanAgent:
    """LangGraph node: extract structured safety items from a guest's memory.

    Args:
        llm: Initialised LangChain LLM instance used for safety synthesis.
            Lower temperature is preferred - this is extraction, not
            creative writing.
    """

    def __init__(self, llm: ChatOpenAI) -> None:
        self.llm = llm

    def node(self, state: dict) -> dict:
        """Extract structured safety items from the guest's retrieved memory.

        Returns an empty list immediately if no memory context is available,
        avoiding an unnecessary LLM call.

        Args:
            state: LangGraph state dict. Expected keys: ``memory_context``,
                ``guest_id``, ``guest_name``, and optionally ``span``.

        Returns:
            Partial state dict with ``safety_items`` (list[dict]) and
            ``synthesis_ms`` (float). Each item dict has keys ``kind``
            (str), ``severity`` (str), ``summary`` (str), and
            ``evidence`` (str).
        """
        memory_context = state.get("memory_context", "")
        guest_id = state.get("guest_id", "")
        guest_name = state.get("guest_name", "")
        span = state.get("span")
        if not memory_context:
            return {"safety_items": [], "synthesis_ms": 0.0}

        prompt = renderer.render(
            SAFETY_SCAN_TEMPLATE,
            memory_context=memory_context,
            guest_id=guest_id,
            guest_name=guest_name,
        )
        ctx = (
            span.new("safety-scan-agent")
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

        items = _parse_items(response.content or "")
        return {"safety_items": items, "synthesis_ms": synthesis_ms}


class SafetyScanGraph:
    """Compiled LangGraph for the per-guest safety scan workflow.

    Topology::

        START → memory-retrieval → safety-scan-agent → END
    """

    def __init__(self, model: str | None = None, temperature: float = 0.0) -> None:
        _model = model or os.getenv("MODEL", "gpt-4o-mini")
        llm = ChatOpenAI(model=_model, temperature=temperature)
        self.scan_agent = SafetyScanAgent(llm=llm)
        self.memory_node = make_retrieval_node(
            queries=SAFETY_SCAN_QUERIES,
            k=MEMORY_K["safety_scan"],
            include_block_ids=False,
        )
        self._graph = self._build()

    def _build(self):
        """Compile the safety-scan LangGraph state graph."""
        builder = StateGraph(SafetyScanState)
        builder.add_node("memory-retrieval", self.memory_node)
        builder.add_node("safety-scan-agent", self.scan_agent.node)
        builder.add_edge(START, "memory-retrieval")
        builder.add_edge("memory-retrieval", "safety-scan-agent")
        builder.add_edge("safety-scan-agent", END)
        return builder.compile()

    def run(
        self,
        agentmem_user,
        guest_id: str,
        guest_name: str,
        client=None,
        span=None,
    ) -> dict:
        """Run the safety-scan pipeline for a single guest.

        Args:
            agentmem_user: Couchbase Agent Memory user object for the guest.
            guest_id: User identifier for the guest.
            guest_name: Display name of the guest.
            client: Optional AgentMemoryClient — required for session lookup.
            span: Optional agentc tracing span.

        Returns:
            Final LangGraph state dict. Key fields: ``safety_items``
            (list[dict]), ``retrieval_ms`` (float), ``synthesis_ms`` (float).
        """
        state: dict = {
            "agentmem_user": agentmem_user,
            "client": client,
            "guest_id": guest_id,
            "guest_name": guest_name,
            "memory_context": "",
            "span": span,
        }
        return self._graph.invoke(state)
