"""
Public surface for the ``agents`` package.

Every agent below is a LangGraph node, and every ``*Graph`` is a
compiled :class:`langgraph.StateGraph` with a ``.run()`` API. Retrieval
and formatting primitives are shared across all of them via
:mod:`agents.memory_toolkit` (``search_memories``, ``format_memories``,
``make_retrieval_node``); per-call-site K values live in
:mod:`agents.config`.

Guest-facing agents
* :class:`ConciergeResponseAgent` / :class:`ConciergeGraph` -
  cross-session memory retrieval + concierge reply, writes the new
  turn back to the guest's session.
* :class:`ProfileOverviewAgent` / :class:`ProfileOverviewGraph` -
  build a guest profile (preferences/dislikes/complaints) from cross-
  session memory. Read-only synthesis.

Ops-facing agents (non-chat, system/schedule/event triggered)
* :class:`BriefingAgent` / :class:`BriefingGraph` -
  pre-arrival briefing card. Writes to ``role_front_desk``.
* :class:`FlagAgent` / :class:`FlagGraph` -
  silent allergy/safety cross-check on form submissions. Writes flag
  events to ``role_front_desk``.
* :class:`DigestAgent` / :class:`DigestGraph` -
  monthly ops digest across all guests. Writes to ``role_gm``.
* :class:`GroupEventBriefAgent` / :class:`GroupEventBriefGraph` -
  facilities brief on new group bookings. Writes to ``role_events``.
* :class:`CallNoteAgent` / :class:`CallNoteGraph` -
  classify-and-write pipeline for staff call notes. Writes a
  structured fact directly into the guest's namespace.
* :class:`SafetyScanAgent` / :class:`SafetyScanGraph` -
  per-guest safety extraction with severity. Powers the ops dashboard
  Allergy & Safety panel. Read-only synthesis.

All agents read and write the SAME Couchbase-backed Couchbase Agent
Memory store - guests under their own user_id, ops artifacts under role
namespaces.
"""

from .concierge_agent import (
    ConciergeGraph,
    ConciergeResponseAgent,
    ConciergeState,
    MemoryRetrievalNode,
)
from .briefing_agent import BriefingAgent, BriefingGraph
from .flag_agent import FlagAgent, FlagGraph
from .digest_agent import DigestAgent, DigestGraph
from .group_event_brief_agent import (
    GroupEventBriefAgent,
    GroupEventBriefGraph,
)
from .call_note_agent import CallNoteAgent, CallNoteGraph
from .profile_overview_agent import ProfileOverviewAgent, ProfileOverviewGraph
from .safety_scan_agent import SafetyScanAgent, SafetyScanGraph

__all__ = [
    # Concierge retrieval node (other graphs build retrieval via
    # make_retrieval_node from agents.memory_toolkit).
    "MemoryRetrievalNode",
    # Guest-facing
    "ConciergeGraph",
    "ConciergeResponseAgent",
    "ConciergeState",
    "ProfileOverviewAgent",
    "ProfileOverviewGraph",
    # Ops-facing
    "BriefingAgent",
    "BriefingGraph",
    "FlagAgent",
    "FlagGraph",
    "DigestAgent",
    "DigestGraph",
    "GroupEventBriefAgent",
    "GroupEventBriefGraph",
    "CallNoteAgent",
    "CallNoteGraph",
    "SafetyScanAgent",
    "SafetyScanGraph",
]
