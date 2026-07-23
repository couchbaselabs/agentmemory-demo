"""
Allergy / safety flag detection agent (ops side).

Trigger: form submission (room-service order, booking form, dietary
intake). Non-chat - silently cross-checks the form payload against
the guest's memory and emits a structured flag card.

Pipeline::

    START → memory-search (safety/dietary) → flag-agent → END

Reads: guest's memory, focused on allergies, dietary, accessibility,
mobility, and prior safety incidents.
Writes: flag event back into the ``role_front_desk`` memory pool with
``severity`` annotation so future digests can pick it up.
"""

from __future__ import annotations

import contextlib
import os
import time
from typing import Any, Optional, TypedDict

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from prompts import SAFETY_FLAG_TEMPLATE, renderer

from ._ops_utils import safe_parse_json, write_artifact_to_role
from .config import MEMORY_K

try:
    from agentc_core.activity.models.content import (
        ChatCompletionContent,
        SystemContent,
    )

    _AGENTC = True
except ImportError:
    _AGENTC = False


BASE_SAFETY_QUERIES = [
    "food allergy allergic reaction",
    "dietary intolerance restriction cannot eat",
    "food avoidance dislike preference",
    "family member child son daughter companion allergy intolerance",
    "guest child relative allergic cannot have",
]

# Words too generic to use as standalone ingredient queries
_STOP_WORDS = {
    "and",
    "the",
    "with",
    "for",
    "from",
    "some",
    "that",
    "this",
    "have",
    "has",
    "will",
    "are",
    "was",
    "can",
}

# Allergen categories → the words that represent them in both evidence and orders.
# Used to verify the LLM flag is grounded: evidence category must overlap order category.
_ALLERGEN_MAP: dict[str, list[str]] = {
    "seafood": [
        "seafood",
        "fish",
        "salmon",
        "tuna",
        "cod",
        "halibut",
        "tilapia",
        "mackerel",
        "sardine",
        "anchovy",
        "trout",
        "sea bass",
        "snapper",
        "shrimp",
        "prawn",
        "crab",
        "lobster",
        "oyster",
        "clam",
        "mussel",
        "scallop",
        "squid",
        "octopus",
        "shellfish",
    ],
    "peanut": ["peanut", "peanuts", "groundnut", "groundnuts"],
    "tree_nut": [
        "almond",
        "cashew",
        "walnut",
        "pecan",
        "pistachio",
        "hazelnut",
        "macadamia",
        "brazil nut",
        "pine nut",
        "chestnut",
        "tree nut",
    ],
    "dairy": [
        "dairy",
        "milk",
        "cheese",
        "butter",
        "cream",
        "yogurt",
        "yoghurt",
        "lactose",
        "whey",
        "casein",
        "ghee",
        "ice cream",
    ],
    "gluten": [
        "gluten",
        "wheat",
        "bread",
        "flour",
        "pasta",
        "barley",
        "rye",
        "cereal",
        "biscuit",
        "cracker",
        "croissant",
    ],
    "egg": ["egg", "eggs", "omelette", "omelet"],
    "soy": ["soy", "soya", "soybean", "tofu", "edamame", "miso", "tempeh"],
    "sesame": ["sesame", "tahini", "hummus"],
}


def _text_allergen_categories(text: str) -> set[str]:
    """Return the set of allergen category keys whose terms appear in `text`."""
    lower = text.lower()
    return {
        cat for cat, terms in _ALLERGEN_MAP.items() if any(t in lower for t in terms)
    }


def _validate_flag(parsed: dict, trigger_payload: str) -> dict:
    """Clear an LLM flag when evidence allergen category doesn't match the order.

    Catches cross-category hallucinations (e.g. seafood allergy cited for a cheese flag).
    All nuance (severity, co-guest attribution) is left to the LLM prompt.
    """
    if not parsed.get("has_flag"):
        return parsed

    evidence = parsed.get("evidence", "")
    evidence_cats = _text_allergen_categories(evidence)
    order_cats = _text_allergen_categories(trigger_payload)

    if evidence_cats & order_cats:
        return parsed  # categories overlap — flag stands

    print(
        f"  [flag-validator] clearing flag: evidence cats={evidence_cats} "
        f"don't overlap order cats={order_cats}"
    )
    return {
        **parsed,
        "has_flag": False,
        "severity": "none",
        "type": "none",
        "conflict_summary": "",
        "recommended_action": "No conflict detected.",
    }


class FlagState(TypedDict, total=False):
    client: Any
    agentmem_user: Any
    guest_id: str
    guest_name: str
    trigger_type: str
    trigger_payload: str
    memory_context: str
    flag: dict
    write_ok: bool
    retrieval_ms: float
    synthesis_ms: float
    span: Optional[object]


class FlagAgent:
    """LangGraph node: detect safety/allergy conflicts in form payload.

    Args:
        llm: Initialised LangChain LLM instance used for conflict articulation.
    """

    def __init__(self, llm: ChatOpenAI) -> None:
        self.llm = llm

    def node(self, state: dict) -> dict:
        """Detect safety/allergy conflicts by passing memory directly to the LLM.

        Fully memory-driven: no hardcoded allergen lists. The LLM reads
        the guest's retrieved memory (facts, summaries, contexts) and
        decides whether the trigger payload conflicts with anything documented.

        Args:
            state: LangGraph state dict. Expected keys: ``memory_context``,
                ``trigger_payload``, ``trigger_type``, ``guest_name``,
                ``client``, and optionally ``span``.

        Returns:
            Partial state dict with ``flag`` (dict), ``write_ok`` (bool),
            and ``synthesis_ms`` (float).
        """
        memory_context = state.get("memory_context", "")
        payload = state.get("trigger_payload", "")
        trigger_type = state.get("trigger_type", "")

        if not memory_context:
            return {
                "flag": {
                    "has_flag": False,
                    "severity": "none",
                    "type": "none",
                    "trigger": trigger_type,
                    "conflict_summary": "",
                    "evidence": "",
                    "recommended_action": "No guest memory found.",
                    "citation": "",
                },
                "write_ok": False,
                "synthesis_ms": 0.0,
            }

        prompt = renderer.render(
            SAFETY_FLAG_TEMPLATE,
            guest_name=state.get("guest_name", ""),
            trigger_type=trigger_type,
            trigger_payload=payload,
            memory_context=memory_context,
        )
        span = state.get("span")
        ctx = span.new("flag-agent") if span is not None else contextlib.nullcontext()
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
            "has_flag": False,
            "severity": "none",
            "type": "none",
            "trigger": trigger_type,
            "conflict_summary": "",
            "evidence": "",
            "recommended_action": "Could not parse LLM response.",
            "citation": "",
        }

        parsed = _validate_flag(parsed, payload)

        write_ok = False
        client = state.get("client")
        if client is not None and parsed.get("has_flag"):
            write_ok = write_artifact_to_role(
                client=client,
                role_id="role_front_desk",
                role_name="Front Desk",
                artifact=parsed,
                artifact_type="safety_flag",
                ref_user=state.get("guest_id"),
            )
        return {
            "flag": parsed,
            "write_ok": write_ok,
            "synthesis_ms": synthesis_ms,
        }


class FlagGraph:
    """Compiled LangGraph for safety/allergy flag detection.

    Topology::

        START → memory-search → flag-agent → END
    """

    def __init__(self, model: str | None = None, temperature: float = 0.0) -> None:
        _model = model or os.getenv("MODEL", "gpt-4o-mini")
        llm = ChatOpenAI(model=_model, temperature=temperature)
        self.flag_agent = FlagAgent(llm=llm)
        self._k = MEMORY_K["flag"]
        self._graph = self._build()

    def _memory_node(self, state: dict) -> dict:
        """Retrieve allergy/restriction memory relevant to the specific order payload.

        Query strategy (most-specific first, so the LLM gets the right context):
        1. Base safety queries (generic allergy/intolerance/family-member patterns)
        2. Per-allergen-category queries built from every allergen keyword in the order
           (e.g. "salmon" in order → add "seafood fish salmon allergy intolerance restriction")
        3. Per-ingredient word queries for less common items not in _ALLERGEN_MAP
        """
        import time as _time
        from .memory_toolkit import format_memories, search_memories
        from ._ops_utils import get_user_session

        user = state.get("agentmem_user")
        if user is None:
            return {"memory_context": "", "retrieval_ms": 0.0}

        client = state.get("client")
        user_id = state.get("guest_id")
        session = get_user_session(user, client=client, user_id=user_id)
        if session is None:
            return {"memory_context": "", "retrieval_ms": 0.0}

        payload = state.get("trigger_payload", "").strip()
        queries = list(BASE_SAFETY_QUERIES)

        if payload:
            # Per-allergen-category: multiple short focused queries beat one long one
            # because vector search ranks shorter queries more reliably.
            detected_cats = _text_allergen_categories(payload)
            for cat in detected_cats:
                terms = _ALLERGEN_MAP[cat]
                # Broad category query
                queries.append(f"{cat} allergy intolerance restriction")
                queries.append(f"{cat} aversion avoid cannot eat")
                # Specific ingredient queries for terms found in the order
                order_terms = [t for t in terms if t in payload.lower()]
                for ot in order_terms[:3]:
                    queries.append(f"{ot} allergy intolerance cannot eat")
                    queries.append(f"{ot} {cat} allergic restriction avoid")
                # Representative synonym query so blocks using alternate words are found
                queries.append(" ".join(terms[:5]) + " allergy")

            # Fallback per-word queries for items not in _ALLERGEN_MAP
            ingredients = [
                w.strip(".,!?;:'\"")
                for w in payload.lower().split()
                if len(w) > 3 and w.strip(".,!?;:'\"") not in _STOP_WORDS
            ]
            for ingredient in ingredients[:4]:
                queries.append(f"{ingredient} allergy intolerance")

        t0 = _time.time()
        records = search_memories(session, queries, k=self._k, cross_session=True)
        memory_context = format_memories(records, include_block_ids=True)
        return {
            "memory_context": memory_context,
            "retrieval_ms": (_time.time() - t0) * 1000,
        }

    def _build(self):
        """Compile the flag-detection LangGraph state graph."""
        builder = StateGraph(FlagState)
        builder.add_node("memory-search", self._memory_node)
        builder.add_node("flag-agent", self.flag_agent.node)
        builder.add_edge(START, "memory-search")
        builder.add_edge("memory-search", "flag-agent")
        builder.add_edge("flag-agent", END)
        return builder.compile()

    def run(
        self,
        client,
        agentmem_user,
        guest_id: str,
        guest_name: str,
        trigger_type: str,
        trigger_payload: str,
        span=None,
    ) -> dict:
        """Run the flag-detection pipeline for a single form submission.

        Args:
            client: Couchbase Agent Memory client instance.
            agentmem_user: Couchbase Agent Memory user object for the guest.
            guest_id: User identifier for the guest.
            guest_name: Display name of the guest.
            trigger_type: Category of the triggering event (e.g. ``"food_order"``).
            trigger_payload: Free-text description of the event payload.
            span: Optional agentc tracing span.

        Returns:
            Final LangGraph state dict. Key fields: ``flag`` (dict),
            ``write_ok`` (bool), ``retrieval_ms`` (float),
            ``synthesis_ms`` (float).
        """
        state: dict = {
            "client": client,
            "agentmem_user": agentmem_user,
            "guest_id": guest_id,
            "guest_name": guest_name,
            "trigger_type": trigger_type,
            "trigger_payload": trigger_payload,
            "memory_context": "",
            "span": span,
        }
        return self._graph.invoke(state)
