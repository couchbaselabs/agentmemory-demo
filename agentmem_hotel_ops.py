"""
Couchbase Agent Memory Hotel - Operations Portal

Internal staff-facing Streamlit UI. **Non-chat by design** - the
primary surface is structured outputs and triggered automations.
Chat is offered as a secondary "Ask memory" drawer on each view.

Six views, each backed by a different LangGraph agent:

1. Dashboard            - at-a-glance arrivals + flags + last digest
2. Pre-Arrival Briefing - :class:`BriefingGraph` per arriving guest
3. Allergy & Safety     - :class:`FlagGraph` on a form submission
4. Group Event Pre-Brief- :class:`GroupEventBriefGraph` on new booking
5. Monthly Ops Digest   - :class:`DigestGraph` across all guests
6. Role Memory          - read-only view of role-namespaced artifacts

Everything reads and writes the SAME Couchbase-backed Couchbase Agent Memory store
that powers the guest-facing UI. Ops artifacts are written under role
namespaces (``role_gm``, ``role_front_desk``, ``role_events``) so
institutional knowledge persists across staff turnover.

Run::

    streamlit run agentmem_hotel_ops.py
"""

from __future__ import annotations

import json
import os
import time
import contextlib as _contextlib
import traceback
from datetime import datetime, timedelta, timezone

import streamlit as st
from agentmemory import AgentMemoryClient
from dotenv import load_dotenv

from agents import (
    BriefingGraph,
    CallNoteGraph,
    DigestGraph,
    FlagGraph,
    GroupEventBriefGraph,
    SafetyScanGraph,
)
from agents.call_note_agent import CALL_NOTE_CATEGORIES
from agents.agentc_catalog import get_catalog
from agents.config import MEMORY_K

load_dotenv()


# ── agentc helpers ────────────────────────────────────────────────────────────


@_contextlib.contextmanager
def _ops_span(name: str, **kwargs):
    """Context manager that opens a GlobalSpan for an ops agent run.

    Yields the span (or None when tracing is disabled / unavailable).
    Always closes the span on exit, even if the agent raises.
    Avoids 'session_id' in kwargs — that key is reserved by agentc.
    """
    span = None
    try:
        _catalog = get_catalog()
        if _catalog is not None:
            from agentc_core.activity import GlobalSpan
            from agentc_core.version import VersionDescriptor

            span = GlobalSpan(
                config=_catalog,
                version=VersionDescriptor(
                    timestamp=datetime.now(timezone.utc),
                    is_dirty=True,
                ),
                name=name,
                kwargs=kwargs,
            )
            span.enter()
    except Exception as _exc:
        print(f"[agentc] span init failed ({name}): {_exc}")
        span = None
    try:
        yield span
    finally:
        if span is not None:
            try:
                span.exit()
            except Exception as _exc:
                print(f"[agentc] span exit failed ({name}): {_exc}")


# ─────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="Couchbase Agent Memory Hotel - Ops Portal",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────
# Aesthetic - same dark luxury palette as the guest UI
# ─────────────────────────────────────────────

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

*, *::before, *::after { box-sizing: border-box; }

html, body, [data-testid="stAppViewContainer"] {
    background: #FFF8EE !important;
    color: #1A1A1A !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

[data-testid="stAppViewContainer"] {
    background: radial-gradient(ellipse at 85% 0%, #FFE4A8 0%, #FFF8EE 45%, #FFFDF8 100%) !important;
}

#MainMenu, footer, header, [data-testid="stToolbar"],
[data-testid="collapsedControl"] { display: none !important; }

h1, h2, h3, h4 {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    letter-spacing: 0.01em;
    color: #1A1A1A;
}

/* Remove Streamlit's default top padding so the header sits flush */
[data-testid="block-container"],
.block-container {
    padding-top: 0 !important;
}

.hotel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.5rem 2rem;
    border-bottom: 1px solid rgba(230, 32, 32, 0.15);
    background: transparent;
    position: sticky;
    top: 0;
    z-index: 100;
    margin: 0;
}

.hotel-wordmark {
    font-family: 'Inter', sans-serif;
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: #1A1A1A;
    text-transform: uppercase;
}

.hotel-tagline {
    font-size: 0.8rem;
    letter-spacing: 0.2em;
    color: rgba(230, 32, 32, 0.6);
    text-transform: uppercase;
    margin-top: 0.2rem;
}

.role-card {
    border: 1px solid rgba(230, 32, 32, 0.15);
    border-radius: 8px;
    padding: 1rem 1.2rem;
    cursor: pointer;
    transition: all 0.25s ease;
    background: rgba(255, 255, 255, 0.5);
    margin-bottom: 0.6rem;
}
.role-card.active {
    border-color: #E62020;
    background: rgba(230, 32, 32, 0.06);
}
.role-name {
    font-family: 'Inter', sans-serif;
    font-size: 1.05rem;
    font-weight: 600;
    color: #1A1A1A;
}
.role-meta {
    font-size: 0.72rem;
    color: rgba(230, 32, 32, 0.7);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-top: 0.15rem;
}

.panel-section-title {
    font-size: 0.65rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: rgba(230, 32, 32, 0.55);
    margin: 1.2rem 0 0.6rem 0;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid rgba(230, 32, 32, 0.1);
}

.ops-card {
    background: linear-gradient(135deg, rgba(230,32,32,0.04) 0%, rgba(255,248,238,0.7) 100%);
    border: 1px solid rgba(230, 32, 32, 0.18);
    border-radius: 10px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1.2rem;
}

.ops-card h3 {
    margin-top: 0 !important;
    color: #1A1A1A;
}

.trigger-badge {
    display: inline-block;
    font-size: 0.62rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    padding: 0.2rem 0.7rem;
    border-radius: 20px;
    background: rgba(230, 32, 32, 0.08);
    color: #E62020;
    border: 1px solid rgba(230, 32, 32, 0.25);
    margin-right: 0.5rem;
}

.severity-high {
    color: #C62020;
    border: 1px solid rgba(198, 32, 32, 0.4);
    background: rgba(198, 32, 32, 0.06);
    padding: 0.2rem 0.6rem;
    border-radius: 4px;
    font-size: 0.72rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
}
.severity-medium {
    color: #C97B10;
    border: 1px solid rgba(247, 148, 29, 0.4);
    background: rgba(247, 148, 29, 0.06);
    padding: 0.2rem 0.6rem;
    border-radius: 4px;
    font-size: 0.72rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
}
.severity-low {
    color: #666;
    border: 1px solid rgba(150, 150, 150, 0.3);
    padding: 0.2rem 0.6rem;
    border-radius: 4px;
    font-size: 0.72rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
}

.kv-line {
    display: flex;
    justify-content: space-between;
    padding: 0.4rem 0;
    border-bottom: 1px solid rgba(230, 32, 32, 0.08);
    font-size: 0.85rem;
}
.kv-key {
    color: rgba(230, 32, 32, 0.65);
    letter-spacing: 0.05em;
    text-transform: uppercase;
    font-size: 0.7rem;
}
.kv-val {
    color: #1A1A1A;
    text-align: right;
    max-width: 70%;
}

.list-item {
    padding: 0.4rem 0.7rem;
    border-left: 2px solid rgba(230, 32, 32, 0.3);
    background: rgba(255, 255, 255, 0.5);
    margin: 0.3rem 0;
    border-radius: 0 6px 6px 0;
    font-size: 0.85rem;
    color: rgba(26, 26, 26, 0.85);
}

.list-item.warning {
    border-left-color: rgba(198, 32, 32, 0.6);
    background: rgba(198, 32, 32, 0.04);
}

.status-pipeline {
    background: rgba(255, 255, 255, 0.8);
    border: 1px solid rgba(230, 32, 32, 0.1);
    border-radius: 8px;
    padding: 0.8rem 1.1rem;
    margin: 0.5rem 0;
    font-size: 0.78rem;
    font-family: 'Inter', monospace;
}
.status-line {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.2rem 0;
    color: rgba(26, 26, 26, 0.45);
}
.status-line.done { color: rgba(26, 26, 26, 0.8); }
.status-line.active { color: #E62020; }
.status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: rgba(230, 32, 32, 0.25);
    flex-shrink: 0;
}
.status-dot.done { background: #4caf82; }
.status-dot.active { background: #E62020; animation: pulse 1s infinite; }
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
}

.stButton > button {
    border-radius: 6px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.85rem !important;
    background: rgba(230, 32, 32, 0.04) !important;
    border: 1px solid rgba(230, 32, 32, 0.22) !important;
    color: #1A1A1A !important;
    transition: all 0.2s !important;
}
.stButton > button:hover {
    background: rgba(230, 32, 32, 0.1) !important;
    border-color: rgba(230, 32, 32, 0.45) !important;
    color: #1A1A1A !important;
}

.stButton > button:active,
.stButton > button:focus {
    background: rgba(230, 32, 32, 0.14) !important;
    border-color: rgba(230, 32, 32, 0.5) !important;
    color: #1A1A1A !important;
    box-shadow: none !important;
    outline: none !important;
}

/* Primary button */
[data-testid="baseButton-primary"],
button[kind="primary"] {
    background: #E62020 !important;
    color: #ffffff !important;
    border: none !important;
}
[data-testid="baseButton-primary"]:hover,
button[kind="primary"]:hover {
    background: #c91c1c !important;
}
[data-testid="baseButton-primary"]:active,
[data-testid="baseButton-primary"]:focus,
button[kind="primary"]:active,
button[kind="primary"]:focus {
    background: #b01818 !important;
    color: #ffffff !important;
    outline: none !important;
    box-shadow: none !important;
}

hr { border-color: rgba(230, 32, 32, 0.1) !important; }

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(230, 32, 32, 0.2); border-radius: 2px; }

/* ── Streamlit native widgets: force light theme ── */
[data-testid="stTextInput"] input,
[data-testid="stPasswordInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea {
    background: #ffffff !important;
    color: #1A1A1A !important;
    border: 1px solid rgba(26,26,26,0.2) !important;
    border-radius: 6px !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stPasswordInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: #E62020 !important;
    box-shadow: 0 0 0 1px rgba(230,32,32,0.2) !important;
}

[data-baseweb="select"] > div,
[data-baseweb="select"] {
    background: #ffffff !important;
    border-color: rgba(26,26,26,0.2) !important;
    color: #1A1A1A !important;
}
[data-baseweb="popover"] li,
[data-baseweb="menu"] li {
    background: #ffffff !important;
    color: #1A1A1A !important;
}
[data-baseweb="popover"] li:hover {
    background: rgba(230,32,32,0.06) !important;
}

label, [data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] label { color: #1A1A1A !important; }
[data-testid="stMarkdown"] p,
[data-testid="stMarkdown"] li,
[data-testid="stMarkdown"] strong { color: #1A1A1A !important; }
[data-testid="stCaptionContainer"] p { color: rgba(26,26,26,0.6) !important; }
[data-testid="stRadio"] p,
[data-testid="stRadio"] label,
[data-testid="stRadio"] span { color: #1A1A1A !important; }

[data-testid="stAlert"] { background: rgba(255,255,255,0.85) !important; }
[data-testid="stAlert"] p,
[data-testid="stAlert"] div { color: #1A1A1A !important; }
.stAlert p { color: #1A1A1A !important; }

[data-testid="stExpander"] details {
    background: rgba(255,255,255,0.55) !important;
    border: 1px solid rgba(230,32,32,0.1) !important;
    border-radius: 8px !important;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary p { color: #1A1A1A !important; }

[data-testid="stCode"] pre,
code { background: rgba(255,255,255,0.7) !important; color: #1A1A1A !important; }
[data-testid="stSpinner"] p { color: #1A1A1A !important; }
[data-testid="stHorizontalBlock"] { gap: 1.5rem; }

.streamlit-expanderHeader {
    background: transparent !important;
    color: rgba(26, 26, 26, 0.7) !important;
    font-size: 0.8rem !important;
    border: none !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# Roles
# ─────────────────────────────────────────────

# Role-scoped permissions. Each role's `allowed_views` is the
# whitelist of views they can navigate to - anything else is hidden
# from the sidebar AND blocked at the dispatcher (defence in depth).
# Role Memory is shown to everyone but the inspector inside that view
# further restricts WHICH roles each user can read into.
ROLES = {
    "role_gm": {
        "name": "General Manager",
        "user_id": "role_gm",
        "tagline": "Property-wide oversight",
        "default_view": "Dashboard",
        "password": "ops",
        "allowed_views": (
            "Dashboard",
            "Log Guest Call",
            "Pre-Arrival Briefings",
            "Allergy & Safety",
            "Group Event Pre-Brief",
            "Monthly Ops Digest",
            "Role Memory",
            "How It Works",
        ),
        # GM can inspect any role's memory pool.
        "can_read_role_memory": (
            "role_gm",
            "role_front_desk",
            "role_events",
            "role_facilities",
        ),
    },
    "role_front_desk": {
        "name": "Front Desk",
        "user_id": "role_front_desk",
        "tagline": "Arrivals · Check-in · Service Recovery",
        "default_view": "Pre-Arrival Briefings",
        "password": "ops",
        # Front desk handles arrivals and live service touchpoints.
        # No access to GM-level analytics or events-team workflows.
        "allowed_views": (
            "Dashboard",
            "Log Guest Call",
            "Pre-Arrival Briefings",
            "Allergy & Safety",
            "Role Memory",
            "How It Works",
        ),
        "can_read_role_memory": ("role_front_desk",),
    },
    "role_events": {
        "name": "Events Coordinator",
        "user_id": "role_events",
        "tagline": "Group bookings · Facilities pre-briefs",
        "default_view": "Group Event Pre-Brief",
        "password": "ops",
        # Events coordinator owns group bookings. Should NOT see
        # individual guest pre-arrival briefings or allergy flags
        # (privacy - those are front-desk concerns).
        "allowed_views": (
            "Dashboard",
            "Log Guest Call",
            "Group Event Pre-Brief",
            "Role Memory",
            "How It Works",
        ),
        "can_read_role_memory": ("role_events",),
    },
    "role_facilities": {
        "name": "Facilities",
        "user_id": "role_facilities",
        "tagline": "AV · Accessibility · Maintenance",
        "default_view": "Group Event Pre-Brief",
        "password": "ops",
        # Facilities reads the group brief (so they can prep AV,
        # accessibility, etc.) but does NOT access individual guest
        # data or the GM's analytics digest.
        "allowed_views": (
            "Dashboard",
            "Log Guest Call",
            "Group Event Pre-Brief",
            "Role Memory",
            "How It Works",
        ),
        "can_read_role_memory": ("role_facilities",),
    },
}

SEED_GUEST_PERSONAS = {
    "alice_chen": {"name": "Alice Chen", "tier": "Platinum", "type": "Corporate"},
    "bob_morrison": {"name": "Bob Morrison", "tier": "Gold", "type": "Occasion"},
    "charlie_wu": {"name": "Charlie Wu", "tier": "Silver", "type": "Group Organiser"},
}


def _personas() -> dict:
    """Return the live persona registry.

    Merges seed personas with any guest discovered via Couchbase Agent Memory at
    login time. Persisted in ``st.session_state`` so it survives
    Streamlit reruns (module-level dicts get re-initialised every rerun).

    Returns:
        Dict mapping ``user_id`` to persona attributes.
    """
    extra = st.session_state.get("dynamic_guest_personas") or {}
    merged = {**SEED_GUEST_PERSONAS, **extra}
    return merged


# Module-level alias kept for legacy lookups. Reads through to
# st.session_state via _personas() at access time.
class _PersonasView:
    def __getitem__(self, key):
        return _personas()[key]

    def __contains__(self, key):
        return key in _personas()

    def get(self, key, default=None):
        return _personas().get(key, default)

    def items(self):
        return _personas().items()

    def keys(self):
        return _personas().keys()

    def values(self):
        return _personas().values()

    def __iter__(self):
        return iter(_personas())

    def __len__(self):
        return len(_personas())


GUEST_PERSONAS = _PersonasView()

VIEWS = [
    "Dashboard",
    "Log Guest Call",
    "Pre-Arrival Briefings",
    "Allergy & Safety",
    "Group Event Pre-Brief",
    "Monthly Ops Digest",
    "Role Memory",
    "How It Works",
]

# ─────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────


def init_state():
    """Initialise ops-portal Streamlit session state with default values.

    Idempotent: existing keys are not overwritten, so this can be called
    at module level on every Streamlit rerun without resetting live state.
    """
    defaults = {
        "ops_authenticated": False,
        "active_role": None,
        "active_view": None,
        "client": None,
        "guest_users": {},  # user_id -> Couchbase Agent Memory user
        "guest_sessions": {},  # user_id -> first session
        "briefings": {},  # user_id -> {"briefing": dict, "retrieval_ms": .., "synthesis_ms": ..}
        "arrival_times": {},  # user_id -> str (user-set arrival time)
        "flags": [],  # list of {flag, retrieval_ms, synthesis_ms, trigger_payload}
        "digest": None,  # last {"digest": dict, "retrieval_ms": .., "synthesis_ms": ..}
        "digest_run_ts": None,
        "group_briefs": [],  # list of {brief, retrieval_ms, synthesis_ms}
        "role_memory_view": None,
        "safety_scan": None,  # cached scan: list of {guest_id, items: [...]}
        "safety_scan_ts": None,
        "dynamic_guest_personas": {},  # uid -> persona dict for users created via guest portal
        "call_logs": [],  # list of staff-logged guest calls in this session
        "show_delete_confirmation": False,  # flag to show delete confirmation dialog
        "deletion_user_id": None,  # user_id of user being deleted
        "deletion_complete": False,  # flag to show deletion success message
        "deletion_result": None,  # deletion result with timing info
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


# ─────────────────────────────────────────────
# Couchbase Agent Memory client + guest session warm-up
# ─────────────────────────────────────────────


def get_client() -> AgentMemoryClient | None:
    """Return a cached :class:`AgentMemoryClient` for the ops portal.

    Creates and caches the client in ``st.session_state.client`` on first
    call. Subsequent calls return the cached instance. Displays a
    Streamlit error and returns ``None`` if the connection fails.

    Returns:
        A connected :class:`AgentMemoryClient`, or ``None`` on failure.
    """
    if st.session_state.client is not None:
        return st.session_state.client
    base_url = os.getenv("AGENTMEM_BASE_URL", "http://localhost:8080")
    try:
        client = AgentMemoryClient(base_url=base_url, timeout=30.0, verify=False)
        st.session_state.client = client
        return client
    except Exception as e:
        st.error(f"Cannot connect to Couchbase Agent Memory: {e}")
        return None


def _first_session_for_user(user):
    """Return the first available session object for a user, or ``None``.

    Iterates through the user's session list and returns the first session
    that can be successfully retrieved. Handles all session ID formats
    returned by the Couchbase Agent Memory SDK.

    Args:
        user: Couchbase Agent Memory user object with ``list_sessions()``
            and ``get_session()`` methods.

    Returns:
        A Couchbase Agent Memory session object, or ``None`` if no sessions
        exist or none could be loaded.
    """
    try:
        result = user.list_sessions()
        raw = (
            getattr(result, "sessions", None)
            or (result.get("sessions") if isinstance(result, dict) else None)
            or (result if isinstance(result, (list, tuple)) else [])
        )
        for s in raw:
            sid = (
                s
                if isinstance(s, str)
                else (s[0] if isinstance(s, tuple) and s else None)
                or getattr(s, "session_id", None)
                or (s.get("id") if isinstance(s, dict) else None)
                or str(s)
            )
            if sid:
                try:
                    return user.get_session(session_id=sid)
                except Exception as exc:
                    print(f"warning: could not get session '{sid}' — {exc}")
                    continue
    except Exception as exc:
        print(f"warning: could not list sessions for user — {exc}")
        return None
    return None


def _list_all_user_ids(client) -> list[tuple[str, str]]:
    """Return ``[(user_id, display_name)]`` for every user in Couchbase Agent Memory.

    Excludes ``role_*`` namespaces, which are operational, not guests.

    Args:
        client: Initialised Couchbase Agent Memory client.

    Returns:
        List of ``(user_id, display_name)`` tuples; empty list on error.
    """
    out: list[tuple[str, str]] = []
    try:
        result = client.list_users()
    except Exception as exc:
        print(f"warning: could not list users — {exc}")
        return out

    raw = (
        getattr(result, "users", None)
        or (result.get("users") if isinstance(result, dict) else None)
        or (result if isinstance(result, (list, tuple)) else [])
    )
    for u in raw:
        uid = (
            getattr(u, "id", None)
            or getattr(u, "user_id", None)
            or (u.get("id") if isinstance(u, dict) else None)
            or (u.get("user_id") if isinstance(u, dict) else None)
        )
        if not uid:
            continue
        if str(uid).startswith("role_"):
            continue
        name = (
            getattr(u, "name", None)
            or (u.get("name") if isinstance(u, dict) else None)
            or uid
        )
        out.append((str(uid), str(name)))
    return out


def warm_up_guest_users():
    """Load every guest user (and one session each) directly from Couchbase Agent Memory.

    Includes the seeded demo guests AND any user created via the
    guest portal, since both UIs share the same backend store. Mutates
    ``st.session_state.guest_users``, ``guest_sessions``, and
    ``dynamic_guest_personas`` in place.
    """
    client = get_client()
    if not client:
        return

    discovered = _list_all_user_ids(client)

    # Fallback: if list_users isn't available or returns empty, at least
    # try the three seeded demo personas so the dashboard isn't blank.
    if not discovered:
        discovered = [
            (uid, SEED_GUEST_PERSONAS[uid]["name"]) for uid in SEED_GUEST_PERSONAS
        ]

    dyn = st.session_state.get("dynamic_guest_personas") or {}

    for uid, name in discovered:
        # Lazily register guests not in the hard-coded seed list so the
        # rest of the UI (briefings, form selectboxes, dashboard list,
        # group event picker) can render them with a sensible fallback
        # profile. Persisted in session_state so it survives reruns.
        if uid not in SEED_GUEST_PERSONAS and uid not in dyn:
            dyn[uid] = {
                "name": name,
                "tier": "Guest",
                "type": "New member",
            }

        if uid in st.session_state.guest_users:
            continue
        try:
            user = client.get_user(user_id=uid)
        except Exception as exc:
            print(f"warning: could not load guest user '{uid}' — {exc}")
            continue
        st.session_state.guest_users[uid] = user
        sess = _first_session_for_user(user)
        if sess is not None:
            st.session_state.guest_sessions[uid] = sess

    st.session_state.dynamic_guest_personas = dyn


def delete_user(user: object) -> dict | None:
    """Delete a user and all associated sessions and memories from Couchbase Agent Memory.

    Args:
        user: Couchbase Agent Memory user object with a ``user_id`` (or ``id``)
            attribute and a ``delete()`` method.

    Returns:
        Dict ``{"success": bool, "user_id": str, "elapsed_ms": float,
        "message": str}`` on success, or ``None`` if the user object is
        invalid or deletion fails.
    """
    try:
        user_id = getattr(user, "user_id", None) or getattr(user, "id", None)
        if not user_id:
            st.error("Invalid user object")
            return None

        start_time = time.time()
        user.delete()
        elapsed_ms = (time.time() - start_time) * 1000

        return {
            "success": True,
            "user_id": user_id,
            "elapsed_ms": elapsed_ms,
            "message": f"User deleted in {elapsed_ms:.0f} ms",
        }
    except Exception as e:
        st.error(f"Failed to delete user: {e}")
        return None


# ─────────────────────────────────────────────
# Status pipeline helper
# ─────────────────────────────────────────────


def render_status_pipeline(
    placeholder, lines_done: list[str], active: str | None = None
):
    """Render a live status pipeline in a Streamlit placeholder.

    Args:
        placeholder: A Streamlit ``st.empty()`` placeholder to write into.
        lines_done: List of completed step labels to display with a green dot.
        active: Optional label for the currently running step (pulsing red dot).
    """
    html = '<div class="status-pipeline">'
    for line in lines_done:
        html += f"""
        <div class="status-line done">
            <div class="status-dot done"></div>{line}
        </div>"""
    if active:
        html += f"""
        <div class="status-line active">
            <div class="status-dot active"></div>{active}
        </div>"""
    html += "</div>"
    placeholder.markdown(html, unsafe_allow_html=True)


def render_timing_pipeline(
    placeholder,
    retrieval_ms: float,
    synthesis_ms: float,
    extra: list[str] | None = None,
):
    """Render a small two-line timing pipeline with explicit split."""
    lines = [
        f"Memory search · {retrieval_ms:.0f}ms",
        f"LLM synthesis · {synthesis_ms:.0f}ms",
        f"Total · {(retrieval_ms + synthesis_ms):.0f}ms",
    ]
    if extra:
        lines.extend(extra)
    html = '<div class="status-pipeline">'
    for line in lines:
        html += f"""
        <div class="status-line done">
            <div class="status-dot done"></div>{line}
        </div>"""
    html += "</div>"
    placeholder.markdown(html, unsafe_allow_html=True)


def scan_for_safety_items(force: bool = False) -> list[dict]:
    """Scan all loaded guests' memory for safety items via SafetyScanGraph.

    Each guest is processed by the agent, which retrieves safety-focused
    memories and asks an LLM to extract structured items with severity.
    The flat list returned to the UI keeps the original keys
    (``guest_id``, ``guest_name``, ``snippet``, ``full``) so existing
    rendering still works, plus the structured ``kind`` / ``severity`` /
    ``summary`` / ``evidence`` fields for richer display.

    Caches the result in ``st.session_state.safety_scan`` so subsequent
    calls return immediately unless ``force=True``.

    Args:
        force: When ``True``, bypasses the cache and re-runs the scan.

    Returns:
        Flat list of dicts with keys ``guest_id``, ``guest_name``,
        ``snippet``, ``full``, ``kind``, ``severity``, ``summary``,
        ``evidence``.
    """
    if not force and st.session_state.safety_scan is not None:
        return st.session_state.safety_scan

    scan_graph = SafetyScanGraph()
    items: list[dict] = []

    _SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    for uid, sess in st.session_state.guest_sessions.items():
        if sess is None:
            continue
        user = st.session_state.guest_users.get(uid)
        if user is None:
            continue
        guest_name = GUEST_PERSONAS.get(uid, {}).get("name", uid)
        try:
            with _ops_span("safety-scan", guest_id=uid, guest_name=guest_name) as _span:
                result = scan_graph.run(
                    agentmem_user=user,
                    guest_id=uid,
                    guest_name=guest_name,
                    span=_span,
                )
        except Exception as exc:
            print(f"warning: safety scan failed for guest '{uid}' — {exc}")
            continue

        for entry in result.get("safety_items", []) or []:
            summary = entry.get("summary", "")
            evidence = entry.get("evidence", "")
            severity = entry.get("severity", "low")
            kind = entry.get("kind", "other")
            snippet_text = f"[{severity.upper()}] {summary}"
            if evidence:
                snippet_text += f" - {evidence}"
            items.append(
                {
                    "guest_id": uid,
                    "guest_name": guest_name,
                    "snippet": snippet_text[:240]  # truncate for dashboard display
                    + ("…" if len(snippet_text) > 240 else ""),
                    "full": (
                        f"{summary}\n\nEvidence: {evidence}\n\n"
                        f"Kind: {kind} · Severity: {severity}"
                    ),
                    "kind": kind,
                    "severity": severity,
                    "summary": summary,
                    "evidence": evidence,
                }
            )

    # Sort the dashboard list with the most urgent items first.
    items.sort(key=lambda i: _SEVERITY_ORDER.get(i.get("severity", "low"), 9))

    st.session_state.safety_scan = items
    st.session_state.safety_scan_ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return items


def severity_badge(sev: str) -> str:
    """Return an HTML badge string for a severity label.

    Args:
        sev: Severity string (e.g. ``"high"``, ``"medium"``, ``"low"``).

    Returns:
        An HTML ``<span>`` string with the appropriate CSS class applied.
    """
    sev_l = (sev or "").lower()
    if sev_l == "high":
        return f'<span class="severity-high">{sev}</span>'
    if sev_l == "medium":
        return f'<span class="severity-medium">{sev}</span>'
    return f'<span class="severity-low">{sev or "low"}</span>'


# ─────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────

st.markdown(
    """
<div class="hotel-header">
    <div style="display:flex; align-items:center; flex-shrink:0;">
        <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 2000 456.5" height="40" style="display:block;">
            <style>.cb0{fill-rule:evenodd;clip-rule:evenodd;fill:#EC1218;}.cb1{fill-rule:evenodd;clip-rule:evenodd;}</style>
            <g><g>
            <path class="cb0" d="M380.5,268.5c0,13.6-8,26-23.6,28.4c-26.8,4.8-82.8,7.6-130,7.6s-103.2-2.8-130-7.6c-15.6-2.8-23.2-15.2-23.2-28.4v-89.2c0-13.6,10.4-26.4,23.2-28.4c8-1.6,26.4-2.8,40.8-2.8c5.6,0,9.6,4.4,10,10.8v62c27.6,0,51.6-1.6,79.6-1.6s51.6,1.6,79.6,1.6v-62c0-6.4,4.4-10.8,9.6-10.8c14.4,0,32.8,1.2,40.8,2.8c12.8,2.4,23.6,15.2,23.6,28.4L380.5,268.5L380.5,268.5z M226.4,0C101.6,0,0,102.4,0,228.4s101.6,228,226.4,228s226.4-102.4,226.4-228S352.1,0,226.4,0L226.4,0z"/>
            <g transform="translate(150.220000, 27.826087)">
            <path class="cb1" d="M543.6,309.9c-70.4,0-105.6-51.2-105.6-108c0-56.4,36.8-107.2,106.4-107.2c26.8,0,46,5.6,61.6,16.4l-20,33.2c-11.2-7.2-24-12-42.4-12c-38,0-58,30.4-58,68.4c0,38.8,19.2,71.6,58.8,71.6c22,0,35.6-7.6,46.4-16l18.4,32C598.4,297.9,573.6,309.9,543.6,309.9"/>
            <path class="cb1" d="M694,309.9c-52.4,0-75.6-40-75.6-79.6s22.8-80.4,75.2-80.4c52.4,0,76.4,39.6,76.4,79.2C770,267.9,746.8,309.9,694,309.9 M692.8,181.9c-22.8,0-29.6,19.2-29.6,47.2s8.8,48.4,31.2,48.4c22.8,0,30.4-18.8,30.4-47.2S716,181.9,692.8,181.9"/>
            <path class="cb1" d="M836.9,153.9v97.6c0,15.2,5.2,22.4,19.6,22.4c15.2,0,26.8-14.8,29.6-18.4V153.9h42.4v107.6c0,20,2.4,35.6,4.4,44.8h-41.6c-1.2-4.4-2.8-14-3.2-20c-8,10.4-23.6,24-48.4,24c-33.2,0-45.2-21.6-45.2-49.6V153.9H836.9z"/>
            <path class="cb1" d="M1032.5,309.9c-48.8,0-78.4-32-78.4-80c0-51.2,33.6-80.4,80-80.4c24.4,0,38.8,7.2,46,12l-13.6,29.2c-6.4-4.4-16.4-8.8-31.2-8.8c-23.6,0-36.4,18.4-36.4,46.4s12,48,37.2,48c16.8,0,27.6-6,32-8.8l12.8,28.4C1073.7,300.7,1060.1,309.9,1032.5,309.9"/>
            <path class="cb1" d="M1194.5,306.3v-97.6c0-15.2-5.2-22.4-19.2-22.4c-15.6,0-27.2,14.4-30,18.4v102h-42.4V81.1h42.4v90.8c7.6-8.4,22-22,46.8-22c33.2,0,45.2,21.2,45.2,49.6v106.4L1194.5,306.3L1194.5,306.3z"/>
            <path class="cb1" d="M1314.1,81.1v84.4c6.8-6.8,20-16,36.8-16c37.6,0,63.6,26,63.6,78.8c0,52.4-34.8,81.2-80.4,81.2c-34.4,0-55.2-8.4-62.4-12.4v-216C1271.3,81.1,1314.1,81.1,1314.1,81.1z M1314.1,273.1c2.8,0.8,9.2,3.2,20,3.2c22,0,35.2-16.4,35.2-47.6c0-28-9.2-44.8-30.8-44.8c-12.8,0-22,8-24.8,11.2L1314.1,273.1L1314.1,273.1z"/>
            <path class="cb1" d="M1519.8,306.3c-1.2-4-2.4-11.6-2.8-16.4c-6.4,8-20.8,20-42,20c-25.6,0-45.6-15.6-45.6-42.8c0-39.6,40-54,80.4-54h5.2v-8.8c0-12.8-5.2-20.4-24-20.4c-19.2,0-32.4,10-38.4,14.4l-18-26.4c9.2-8,28.8-22,61.2-22c41.6,0,61.2,16.4,61.2,56.8v53.6c0,20.8,2.4,36,4.4,46C1561.4,306.3,1519.8,306.3,1519.8,306.3z M1515,239.1h-5.2c-23.2,0-39.2,6.8-39.2,24.4c0,10.8,8.4,15.6,17.6,15.6c14.4,0,22.4-8,26.8-12.8L1515,239.1L1515,239.1z"/>
            <path class="cb1" d="M1633.8,309.9c-27.2,0-44.4-8-53.6-14.4l14.4-30c5.6,4,20.4,12.4,37.2,12.4c15.6,0,24.4-4.4,24.4-13.2c0-10-16.8-12.8-38.4-23.2c-20.8-10-32.8-22-32.8-44.8c0-28.8,22.4-47.2,56.8-47.2c26,0,41.6,8,48.8,12l-14.8,29.2c-5.6-4-17.6-9.6-32-9.6c-14.4,0-20.4,5.2-20.4,12.8c0,10,14,12.4,30.8,19.2c23.6,9.6,40.4,20.8,40.4,46.8C1693.8,293.1,1671,309.9,1633.8,309.9"/>
            <path class="cb1" d="M1792.2,277.9c20.4,0,31.6-6.4,38.8-10.4l13.6,27.6c-10,5.6-25.6,14.8-56.4,14.8c-50.4,0-79.2-32-79.2-80.8c0-48.4,33.2-79.2,74.8-79.2c47.6,0,70.4,33.2,65.2,90.4h-94C1756.6,263.1,1767.8,277.9,1792.2,277.9L1792.2,277.9z M1808.2,211.1c-0.4-16.8-6.8-30.4-25.2-30.4c-16.8,0-26.4,10.8-28.8,30.4H1808.2z"/>
            </g></g></g>
        </svg>
    </div>
    <div style="flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;">
        <div class="hotel-wordmark">Agent Memory Hotel</div>
        <div class="hotel-tagline">Operations Portal · Internal Use</div>
    </div>
    <div style="width: 175px; flex-shrink:0;"></div>
</div>
""",
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────
# DELETION SUCCESS SCREEN (shown for ops role too)
# ─────────────────────────────────────────────

if st.session_state.get("deletion_complete", False) and st.session_state.get(
    "deletion_result"
):
    result = st.session_state.deletion_result
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown(
            f"""
        <div style="max-width: 420px; margin: 80px auto; padding: 2.5em; background: rgba(76,175,130,0.08); 
                    border: 1px solid rgba(76,175,130,0.3); border-radius: 12px;">
            <div style="text-align: center; color: #4caf82; margin-bottom: 1em; font-size: 2.5em;">✓</div>
            <div style="text-align: center; font-size: 1.3em; font-weight: 600; color: #4caf82; margin-bottom: 0.8em;
                        font-family: 'Inter', sans-serif;">Guest User Deleted</div>
            <div style="text-align: center; color: rgba(200,230,210,0.8); margin-bottom: 0.5em; font-size: 0.95em;
                        line-height: 1.6;">
                User "{result.get("user_id", "unknown")}" and all associated data have been permanently removed.
            </div>
            <div style="text-align: center; color: rgba(76,175,130,0.7); margin-bottom: 2em; font-size: 0.85em;
                        font-family: 'Inter', monospace;">
                {result.get("message", "Deleted successfully")}
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

        # Add back to dashboard button
        st.markdown('<div style="height:1.2rem"></div>', unsafe_allow_html=True)
        if st.button("Back to Dashboard", use_container_width=True, type="primary"):
            st.session_state.deletion_complete = False
            st.session_state.deletion_result = None
            st.session_state.active_view = "Dashboard"
            st.rerun()

    # Reset deletion state after display (if button not clicked)
    st.session_state.deletion_complete = False
    st.session_state.deletion_result = None
    st.stop()


# ─────────────────────────────────────────────
# Login (role-based)
# ─────────────────────────────────────────────

if not st.session_state.ops_authenticated:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown(
            """
        <div style="max-width: 460px; margin: 60px auto; padding: 2.5em;
                    background: rgba(255,255,255,0.7);
                    border: 1px solid rgba(230,32,32,0.15);
                    border-radius: 12px;">
            <div style="text-align: center; font-size: 1.8em; font-weight: 700;
                        color: #1A1A1A; margin-bottom: 0.3em;
                        font-family: 'Inter', sans-serif;">Sign in by Role</div>
            <div style="text-align: center; color: rgba(230,32,32,0.5);
                        margin-bottom: 1.5em; font-size: 0.85em;
                        letter-spacing: 0.1em;">
                Memory belongs to the role · Staff turnover does not erase institutional knowledge
            </div>
        """,
            unsafe_allow_html=True,
        )

        role_id = st.selectbox(
            "Role",
            options=list(ROLES.keys()),
            format_func=lambda r: f"{ROLES[r]['name']} - {ROLES[r]['tagline']}",
        )
        password = st.text_input("Password", type="password", placeholder="ops")

        if st.button("Sign In", use_container_width=True, type="primary"):
            if password == ROLES[role_id]["password"]:
                st.session_state.ops_authenticated = True
                st.session_state.active_role = role_id
                st.session_state.active_view = ROLES[role_id]["default_view"]
                st.rerun()
            else:
                st.error("Invalid password (default: ops)")

        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


# ─────────────────────────────────────────────
# Warm-up
# ─────────────────────────────────────────────

warm_up_guest_users()


# ─────────────────────────────────────────────
# Layout: sidebar (role + nav) + main view
# ─────────────────────────────────────────────

sidebar_col, main_col = st.columns([0.7, 2.3], gap="medium")


with sidebar_col:
    role = ROLES[st.session_state.active_role]
    st.markdown(
        '<div class="panel-section-title" style="margin-top:0;">Active Role</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
    <div class="role-card active">
        <div class="role-name">{role["name"]}</div>
        <div class="role-meta">{role["tagline"]}</div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    if st.button("Sign Out", use_container_width=True):
        st.session_state.ops_authenticated = False
        st.session_state.active_role = None
        st.session_state.active_view = None
        st.rerun()

    allowed = ROLES[st.session_state.active_role].get("allowed_views", VIEWS)
    st.markdown('<div class="panel-section-title">Views</div>', unsafe_allow_html=True)
    for view in VIEWS:
        if view not in allowed:
            continue
        is_active = view == st.session_state.active_view
        prefix = "→ " if is_active else "   "
        if st.button(f"{prefix}{view}", use_container_width=True, key=f"nav_{view}"):
            st.session_state.active_view = view
            st.rerun()

    # ── Delete guest user section ──────────────────────
    st.markdown('<div style="height:0.8rem"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="panel-section-title">Guest Management</div>',
        unsafe_allow_html=True,
    )

    # Only show selector when not confirming deletion
    if not st.session_state.get("show_delete_confirmation", False):
        # Guest user selector for deletion
        guest_users = st.session_state.guest_users
        if guest_users:
            guest_options = {
                uid: st.session_state.dynamic_guest_personas.get(uid, {}).get(
                    "name", uid
                )
                for uid in guest_users.keys()
            }
            delete_user_id = st.selectbox(
                "Select guest to delete:",
                options=list(guest_options.keys()),
                format_func=lambda x: guest_options[x],
                key="delete_guest_selector",
            )

            if st.button(
                "Delete Guest", use_container_width=True, key="delete_guest_button"
            ):
                st.session_state.show_delete_confirmation = True
                st.session_state.deletion_user_id = delete_user_id

    # Delete confirmation dialog
    if st.session_state.get("show_delete_confirmation", False):
        st.markdown('<div style="height:0.4rem"></div>', unsafe_allow_html=True)
        st.markdown(
            '<div style="background: rgba(220,80,60,0.08); border: 1px solid rgba(220,80,60,0.3); border-radius: 8px; padding: 0.9rem; margin: 0.5rem 0;">'
            '<div style="color: rgba(255,160,140,0.9); font-weight: 600; margin-bottom: 0.5rem;">⚠️ Delete Guest Confirmation</div>'
            '<div style="color: rgba(26,26,26,0.7); font-size: 0.85rem; margin-bottom: 0.8rem;">'
            "This will permanently delete the guest and all associated data. Please enter your ops password to confirm."
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )

        # Password input
        delete_password = st.text_input(
            "Enter ops password to confirm deletion:",
            type="password",
            key="delete_ops_password_input",
        )

        col_confirm, col_cancel = st.columns([1, 1])
        with col_confirm:
            if st.button("Confirm Delete", use_container_width=True):
                # Get the correct password for this role
                correct_password = ROLES[st.session_state.active_role].get(
                    "password", "ops"
                )

                if delete_password and delete_password == correct_password:
                    # Perform deletion
                    user_id_to_delete = st.session_state.deletion_user_id
                    with st.spinner("Deleting guest and all data…"):
                        user = st.session_state.guest_users.get(user_id_to_delete)
                        if user:
                            result = delete_user(user)

                            if result and result.get("success"):
                                st.session_state.show_delete_confirmation = False
                                st.session_state.deletion_complete = True
                                st.session_state.deletion_result = result
                                # Clean up guest user caches
                                if user_id_to_delete in st.session_state.guest_users:
                                    del st.session_state.guest_users[user_id_to_delete]
                                if user_id_to_delete in st.session_state.guest_sessions:
                                    del st.session_state.guest_sessions[
                                        user_id_to_delete
                                    ]
                                st.rerun()
                            else:
                                st.error("Failed to delete guest")
                                st.session_state.show_delete_confirmation = False
                        else:
                            st.error("Guest not found")
                            st.session_state.show_delete_confirmation = False
                else:
                    st.error("Incorrect password")

        with col_cancel:
            if st.button("Cancel", use_container_width=True):
                st.session_state.show_delete_confirmation = False
                st.rerun()

    st.markdown(
        '<div class="panel-section-title">Hotel memory database</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
    <div style="font-size:0.78rem; color:rgba(26,26,26,0.55); line-height:1.6; padding:0.5rem 0;">
        <span style="color:rgba(230,32,32,0.6);">Guests:</span> {len(st.session_state.guest_users)} loaded<br>
        <span style="color:rgba(230,32,32,0.6);">Roles:</span> 4
    </div>
    """,
        unsafe_allow_html=True,
    )


# ═════════════════════════════════════════════════════════════════════
# VIEW: Dashboard
# ═════════════════════════════════════════════════════════════════════


def render_dashboard():
    """Render the ops portal dashboard view.

    Shows at-a-glance arrival summaries, recent allergy/safety flags from
    the cached :func:`scan_for_safety_items` result, and the last
    monthly digest headline. Uses ``st.session_state`` data loaded by
    :func:`warm_up_guest_users` at login.
    """
    st.markdown(f"## Dashboard - {ROLES[st.session_state.active_role]['name']}")
    st.markdown(
        '<span class="trigger-badge">Live view</span>',
        unsafe_allow_html=True,
    )

    # Run safety scan once per session (cached)
    safety_items = scan_for_safety_items(force=False)
    safety_count = len(safety_items)

    cols = st.columns(3)
    with cols[0]:
        st.markdown(
            f"""
        <div class="ops-card">
            <h3>Guests on file</h3>
            <div style="font-size: 2.4rem; color: #E62020;
                        font-family: 'Inter', sans-serif;">
                {len(st.session_state.guest_users)}
            </div>
            <div style="color:rgba(26,26,26,0.5); font-size:0.78rem;">
                Loaded from hotel memory database
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )
    with cols[1]:
        st.markdown(
            f"""
        <div class="ops-card">
            <h3>Known guest allergies &amp; restrictions</h3>
            <div style="font-size: 2.4rem; color: #ff8a72;
                        font-family: 'Inter', sans-serif;">
                {safety_count}
            </div>
            <div style="color:rgba(26,26,26,0.5); font-size:0.78rem;">
                Allergy / dietary / accessibility · auto-scanned
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )
    with cols[2]:
        last_run = st.session_state.digest_run_ts or "Never"
        st.markdown(
            f"""
        <div class="ops-card">
            <h3>Last monthly ops report</h3>
            <div style="font-size: 1.4rem; color: #E62020;
                        font-family: 'Inter', sans-serif; margin-top:0.4rem;">
                {last_run}
            </div>
            <div style="color:rgba(26,26,26,0.5); font-size:0.78rem;">
                Monthly ops report
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    if st.button("Re-scan safety memory now", key="rescan_safety"):
        scan_for_safety_items(force=True)
        st.rerun()

    st.markdown("### Guests in memory store")

    # Get all users from session state (loaded via list_users)
    all_guest_uids = set(st.session_state.guest_users.keys()) | set(
        st.session_state.dynamic_guest_personas.keys()
    )

    if not all_guest_uids:
        st.markdown(
            '<div class="list-item">No guests loaded in memory store yet.</div>',
            unsafe_allow_html=True,
        )
    else:
        for uid in sorted(all_guest_uids):
            # Get persona info from predefined personas or dynamic personas
            persona = GUEST_PERSONAS.get(
                uid
            ) or st.session_state.dynamic_guest_personas.get(uid, {})
            name = persona.get("name", uid)
            tier = persona.get("tier", "Guest")
            ptype = persona.get("type", "Unknown")

            # Check if user is in guest_users (loaded from backend)
            has_memory = uid in st.session_state.guest_users

            if not has_memory:
                st.markdown(
                    f"""
                <div class="list-item">
                    <strong>{name}</strong> - {tier} · {ptype}
                    <span style="color:rgba(255,160,140,0.7); margin-left:0.5rem;">
                        (no memory found in store)
                    </span>
                </div>
                """,
                    unsafe_allow_html=True,
                )
                continue

            existing = st.session_state.briefings.get(uid)
            status = "Briefing ready" if existing else "No briefing generated yet"
            st.markdown(
                f"""
            <div class="list-item">
                <strong>{name}</strong> - {tier} · {ptype}
                <span style="color:rgba(230,32,32,0.7); margin-left:0.5rem;">{status}</span>
            </div>
            """,
                unsafe_allow_html=True,
            )

    with st.expander(
        f"Allergies & restrictions found in guest memory ({len(safety_items)})",
        expanded=False,
    ):
        st.markdown(
            '<div style="color:rgba(26,26,26,0.55); font-size:0.78rem; margin-bottom:0.6rem;">'
            f"Surfaced by a parallel memory scan across all guests · last run {st.session_state.safety_scan_ts or '-'}."
            " Each item is a memory excerpt that matched safety / allergy / accessibility keywords."
            " Click an item to see the full memory."
            "</div>",
            unsafe_allow_html=True,
        )
        if not safety_items:
            st.markdown(
                '<div class="list-item">No safety items detected in memory yet. '
                'If the seed data was just loaded, click "Re-scan" above.</div>',
                unsafe_allow_html=True,
            )
        else:
            for idx, item in enumerate(safety_items):
                preview = item["snippet"].replace("\n", " ")[:120]
                with st.expander(
                    f"{item['guest_name']} - {preview}{'…' if len(item['snippet']) > 120 else ''}",
                    expanded=False,
                ):
                    st.markdown(
                        f"<div style='color:rgba(230,32,32,0.75); font-size:0.72rem; "
                        f"letter-spacing:0.1em; text-transform:uppercase; margin-bottom:0.4rem;'>"
                        f"{item['guest_name']}</div>",
                        unsafe_allow_html=True,
                    )
                    st.code(item.get("full") or item["snippet"], language="text")

    st.markdown("### Allergy &amp; safety alerts (this session)")
    st.markdown(
        '<div style="color:rgba(26,26,26,0.55); font-size:0.78rem; margin-bottom:0.6rem;">'
        "Alerts raised when staff submitted an order or booking form during this session. "
        "Each alert is also saved to the front desk's shared memory."
        "</div>",
        unsafe_allow_html=True,
    )
    raised = [
        e
        for e in st.session_state.flags
        if isinstance(e, dict) and (e.get("flag") or {}).get("has_flag")
    ]
    if not raised:
        st.markdown(
            '<div class="list-item">No flags raised this session. '
            "Submit a form on the Allergy &amp; Safety view to test.</div>",
            unsafe_allow_html=True,
        )
    else:
        for entry in raised[-5:]:  # show the last 5 flags raised this session
            f = entry.get("flag") or {}
            sev = (f.get("severity") or "low").lower()
            cls = "warning" if sev == "high" else ""
            type_label = _humanise_flag_type(f.get("type", "flag"))
            summary = f.get("conflict_summary", "") or "(no summary)"
            badge = severity_badge(f.get("severity", "low"))
            st.markdown(
                f'<div class="list-item {cls}"><strong>{type_label}</strong> &middot; '
                f"{summary} {badge}</div>",
                unsafe_allow_html=True,
            )


# ═════════════════════════════════════════════════════════════════════
# VIEW: Log Guest Call
# ═════════════════════════════════════════════════════════════════════


def render_call_log():
    """Render the Log Guest Call view.

    Provides a form for staff to log a free-text note about a guest
    interaction. On submission the :class:`CallNoteGraph` pipeline
    classifies the note, checks for near-duplicates, and writes the
    structured fact into the guest's memory. Logged calls are shown
    below the form for the current session.
    """
    st.markdown("## Log Guest Call")
    st.markdown(
        '<span class="trigger-badge">Phoned-in or in-person</span>'
        '<span class="trigger-badge">Saved to guest memory</span>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="color:rgba(26,26,26,0.6); font-size:0.85rem; margin-bottom:1.2rem;">'
        "Use this when a guest calls or speaks to staff and shares something the system should remember: "
        "an allergy, a complaint, a preference, a special request, an incident. "
        "The note is written into the guest's memory namespace and becomes available to every other "
        "agent (concierge, briefings, allergy checks, digests) on the next read."
        "</div>",
        unsafe_allow_html=True,
    )

    client = get_client()
    if not client:
        return

    if not st.session_state.guest_users:
        st.markdown(
            '<div class="list-item">No guests loaded from the memory store.</div>',
            unsafe_allow_html=True,
        )
        return

    with st.form("call_log_form", clear_on_submit=True):
        guest_id = st.selectbox(
            "Guest",
            options=list(st.session_state.guest_users.keys()),
            format_func=lambda u: GUEST_PERSONAS.get(u, {}).get("name", u),
        )
        category = st.selectbox(
            "Category",
            options=list(CALL_NOTE_CATEGORIES.keys()),
            format_func=lambda c: CALL_NOTE_CATEGORIES[c],
            help="Used as a memory annotation so this note can be retrieved by category later.",
        )
        note = st.text_area(
            "What did the guest say?",
            placeholder=(
                "e.g. 'Called to mention her husband has a severe shellfish allergy. "
                "Wants this on file before next arrival.'"
            ),
            height=140,
        )
        submitted = st.form_submit_button("Add to guest memory", type="primary")

    if submitted:
        if not note.strip():
            st.warning("Enter what the guest said before saving.")
            return

        guest_name = GUEST_PERSONAS.get(guest_id, {}).get("name", guest_id)
        role_id = st.session_state.active_role
        role_name = ROLES.get(role_id, {}).get("name", role_id)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")

        # ── Run the CallNoteGraph (LangGraph state graph) ──
        # Topology: classify → memory-search → enrich → write
        placeholder = st.empty()
        log: list[str] = []
        try:
            render_status_pipeline(
                placeholder,
                log,
                "Classifying note (call-note agent)…",
            )
            graph = CallNoteGraph()
            log.append("Note classified · category and severity normalised")
            render_status_pipeline(
                placeholder,
                log,
                "Searching guest memory for near-duplicates…",
            )
            with _ops_span(
                "call-note", guest_id=guest_id, guest_name=guest_name, category=category
            ) as _span:
                state = graph.run(
                    client=client,
                    agentmem_session=st.session_state.guest_sessions.get(guest_id),
                    agentmem_user=st.session_state.guest_users.get(guest_id),
                    guest_id=guest_id,
                    guest_name=guest_name,
                    raw_note=note.strip(),
                    staff_category=category,
                    logged_by_role=role_id,
                    logged_by_role_name=role_name,
                    timestamp=ts,
                    span=_span,
                )
        except Exception as e:
            st.error(f"Call-note agent failed: {e}")
            st.code(traceback.format_exc())
            return

        if not state.get("write_ok"):
            st.error("Call-note agent could not write to guest memory.")
            return

        classify_ms = float(state.get("classify_ms") or 0.0)
        retrieval_ms = float(state.get("retrieval_ms") or 0.0)
        enrich_ms = float(state.get("enrich_ms") or 0.0)
        write_ms = float(state.get("write_ms") or 0.0)
        final_category = state.get("classified_category", category)
        final_category_label = CALL_NOTE_CATEGORIES.get(final_category, final_category)
        severity = state.get("classified_severity", "none")
        block_id = state.get("block_id", "")
        near_dupes = state.get("near_duplicate_block_ids") or []

        extras = [
            f"Classified as {final_category_label} · severity {severity}",
            f"Near-duplicate scan · {len(near_dupes)} related block(s)",
            f"Fact written to {guest_name}'s memory"
            + (f" (block {block_id[:8]}…)" if block_id else ""),
        ]
        # Reuse the timing pipeline; map classify→synthesis, retrieval→retrieval.
        # Total includes enrich + write so the whole graph latency is honest.
        total_ms = classify_ms + retrieval_ms + enrich_ms + write_ms
        timing_lines = [
            f"Classify (LLM) · {classify_ms:.0f}ms",
            f"Memory search · {retrieval_ms:.0f}ms",
            f"Enrich · {enrich_ms:.0f}ms",
            f"Write · {write_ms:.0f}ms",
            f"Total · {total_ms:.0f}ms",
        ]
        timing_lines.extend(extras)
        html = '<div class="status-pipeline">'
        for line in timing_lines:
            html += f"""
            <div class="status-line done">
                <div class="status-dot done"></div>{line}
            </div>"""
        html += "</div>"
        placeholder.markdown(html, unsafe_allow_html=True)

        st.session_state.call_logs.append(
            {
                "guest_id": guest_id,
                "guest_name": guest_name,
                "category": final_category,
                "category_label": final_category_label,
                "note": note.strip(),
                "logged_by": role_name,
                "logged_at": ts,
                "severity": severity,
                "block_id": block_id,
            }
        )

        # Drop cached safety scan so a newly-logged allergy / incident
        # shows up on the dashboard scan immediately.
        if final_category in ("allergy", "incident"):
            st.session_state.safety_scan = None

        st.success(f"Saved to {guest_name}'s memory.")

    if st.session_state.call_logs:
        st.markdown("### Recent notes (this session)")
        for entry in reversed(
            st.session_state.call_logs[-10:]
        ):  # display the last 10 call log entries
            st.markdown(
                f"""
                <div class="list-item">
                    <strong>{entry["guest_name"]}</strong> &middot;
                    <span style="color:rgba(230,32,32,0.8);">{entry["category_label"]}</span>
                    &middot; <span style="color:rgba(26,26,26,0.55); font-size:0.78rem;">
                        {entry["logged_at"]} by {entry["logged_by"]}
                    </span>
                    <div style="margin-top:0.3rem; color:rgba(26,26,26,0.85);">
                        {entry["note"]}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ═════════════════════════════════════════════════════════════════════
# VIEW: Pre-Arrival Briefings
# ═════════════════════════════════════════════════════════════════════


def render_briefings():
    """Render the Pre-Arrival Briefings view.

    Provides a guest selector and arrival-time picker. On "Generate
    Briefing" the :class:`BriefingGraph` retrieves the guest's full
    memory and synthesises a structured pre-arrival briefing JSON,
    then writes it to the ``role_front_desk`` memory pool. Generated
    briefings are cached in ``st.session_state.briefings`` and displayed
    via :func:`render_briefing_card`.
    """
    st.markdown("## Pre-Arrival Briefings")
    st.markdown(
        '<span class="trigger-badge">Generated on demand</span>'
        '<span class="trigger-badge">Or scheduled before arrival</span>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="color:rgba(26,26,26,0.6); font-size:0.85rem; margin-bottom:1.2rem;">'
        "Briefings are auto-generated from cross-session memory and delivered to the front desk before the guest arrives. "
        "Set a real arrival time per guest, then generate. Existing briefings stay collapsed below until you re-open them."
        "</div>",
        unsafe_allow_html=True,
    )

    client = get_client()
    if not client:
        return

    for uid, persona in GUEST_PERSONAS.items():
        if uid not in st.session_state.guest_users:
            continue

        st.markdown(f"### {persona['name']} · {persona['tier']} · {persona['type']}")

        col_d, col_t, col_btn = st.columns([1.4, 1, 1.2])
        with col_d:
            arr_date = st.date_input(
                "Arrival date",
                value=datetime.now().date() + timedelta(days=1),
                key=f"arr_date_{uid}",
            )
        with col_t:
            arr_time = st.time_input(
                "Arrival time",
                value=datetime.now().time().replace(microsecond=0),
                key=f"arr_time_{uid}",
            )
        with col_btn:
            st.markdown('<div style="height:1.85rem;"></div>', unsafe_allow_html=True)
            run_btn = st.button("Generate briefing", key=f"brief_{uid}")

        arrival_str = f"{arr_date} {arr_time}"
        st.session_state.arrival_times[uid] = arrival_str

        existing = st.session_state.briefings.get(uid)

        if run_btn:
            placeholder = st.empty()
            log: list[str] = []
            try:
                render_status_pipeline(
                    placeholder, log, "Searching guest memory across all sessions…"
                )
                graph = BriefingGraph()
                user = st.session_state.guest_users.get(uid)
                if user is None:
                    st.error(f"Guest {uid} user not loaded. Skipping briefing.")
                    continue
                with _ops_span(
                    "pre-arrival-briefing", guest_id=uid, guest_name=persona["name"]
                ) as _span:
                    state = graph.run(
                        client=client,
                        agentmem_user=user,
                        guest_id=uid,
                        guest_name=persona["name"],
                        arrival_time=arrival_str,
                        span=_span,
                    )
                retrieval_ms = float(state.get("retrieval_ms") or 0.0)
                synthesis_ms = float(state.get("synthesis_ms") or 0.0)
                extras = []
                if state.get("write_ok"):
                    extras.append("Briefing written to role_front_desk memory")
                else:
                    extras.append("Briefing not persisted (role write skipped)")
                render_timing_pipeline(
                    placeholder, retrieval_ms, synthesis_ms, extra=extras
                )
                st.session_state.briefings[uid] = {
                    "briefing": state.get("briefing"),
                    "retrieval_ms": retrieval_ms,
                    "synthesis_ms": synthesis_ms,
                    "arrival": arrival_str,
                }
                existing = st.session_state.briefings[uid]
            except Exception as exc:
                log.append(f"Error: {exc}")
                render_status_pipeline(placeholder, log)
                st.code(traceback.format_exc())

        if existing:
            briefing = (
                existing.get("briefing")
                if isinstance(existing, dict) and "briefing" in existing
                else existing
            )
            label = (
                f"Briefing · {persona['name']} · arrival {existing.get('arrival', '')}"
                if isinstance(existing, dict) and "arrival" in existing
                else f"Briefing · {persona['name']}"
            )
            with st.expander(label, expanded=False):
                if isinstance(existing, dict) and "retrieval_ms" in existing:
                    r_ms = existing.get("retrieval_ms", 0.0)
                    s_ms = existing.get("synthesis_ms", 0.0)
                    st.markdown(
                        f'<div style="color:rgba(26,26,26,0.55); font-size:0.78rem; margin-bottom:0.6rem;">'
                        f"Memory search · {r_ms:.0f}ms &nbsp;|&nbsp; LLM synthesis · {s_ms:.0f}ms &nbsp;|&nbsp; "
                        f"Total · {(r_ms + s_ms):.0f}ms</div>",
                        unsafe_allow_html=True,
                    )
                render_briefing_card(briefing or {})


def render_briefing_card(b: dict):
    """Render a single pre-arrival briefing card using Streamlit markdown.

    Args:
        b: Briefing dict as returned by :class:`BriefingGraph`. Expected
            keys: ``guest``, ``arrival``, ``tier``, ``preferences``,
            ``prior_complaints``, ``safety_flags``,
            ``occasion_context``, ``recovery_actions``, ``summary``.
    """
    st.markdown('<div class="ops-card">', unsafe_allow_html=True)
    st.markdown(f"<h3>Briefing - {b.get('guest', '')}</h3>", unsafe_allow_html=True)
    st.markdown(
        f"""
    <div class="kv-line"><span class="kv-key">Arrival</span><span class="kv-val">{b.get("arrival", "")}</span></div>
    <div class="kv-line"><span class="kv-key">Tier</span><span class="kv-val">{b.get("tier", "")}</span></div>
    <div class="kv-line"><span class="kv-key">Summary</span><span class="kv-val">{b.get("summary", "")}</span></div>
    <div class="kv-line"><span class="kv-key">Occasion</span><span class="kv-val">{b.get("occasion_context", "") or "-"}</span></div>
    """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Preferences**")
        for p in b.get("preferences") or []:
            st.markdown(f'<div class="list-item">{p}</div>', unsafe_allow_html=True)
        if not b.get("preferences"):
            st.markdown(
                '<div class="list-item">None on file.</div>', unsafe_allow_html=True
            )
    with c2:
        st.markdown("**Recovery actions**")
        for a in b.get("recovery_actions") or []:
            st.markdown(f'<div class="list-item">{a}</div>', unsafe_allow_html=True)
        if not b.get("recovery_actions"):
            st.markdown(
                '<div class="list-item">No recovery needed.</div>',
                unsafe_allow_html=True,
            )

    st.markdown("**Prior complaints**")
    for c in b.get("prior_complaints") or []:
        sev = c.get("severity", "low")
        st.markdown(
            f"""
        <div class="list-item {"warning" if sev == "high" else ""}">
            {c.get("event", "")} {severity_badge(sev)}
        </div>
        """,
            unsafe_allow_html=True,
        )
    if not b.get("prior_complaints"):
        st.markdown(
            '<div class="list-item">No prior complaints.</div>', unsafe_allow_html=True
        )

    st.markdown("**Safety / Allergy Flags**")
    for tp in b.get("safety_flags") or []:
        st.markdown(
            f"""
        <div class="list-item warning">
            <strong>{tp.get("person", "")}</strong> · {tp.get("flag", "")}
            {severity_badge(tp.get("severity", "low"))}
        </div>
        """,
            unsafe_allow_html=True,
        )
    if not b.get("safety_flags"):
        st.markdown(
            '<div class="list-item">No safety flags on file.</div>',
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════
# VIEW: Allergy & Safety Flags (form-triggered)
# ═════════════════════════════════════════════════════════════════════


def render_flags():
    """Render the Allergy & Safety Flags view.

    Provides a form for triggering a :class:`FlagGraph` run against a
    guest's memory. On submission the agent cross-checks the trigger
    payload against the guest's stored dietary, allergy, and safety
    records and emits a structured flag card. Raised flags are appended
    to ``st.session_state.flags`` and displayed via
    :func:`render_flag_card`.
    """
    st.markdown("## Allergy & Safety Flags")
    st.markdown(
        '<span class="trigger-badge">Triggered by form submission</span>'
        '<span class="trigger-badge">Silent background check</span>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="color:rgba(26,26,26,0.6); font-size:0.85rem; margin-bottom:1.2rem;">'
        "Enter a guest's food order below. The flag agent silently cross-checks the dish or ingredients "
        "against the guest's memory, including any third-party allergies, and surfaces a flag card "
        "if a conflict is detected. Allergies are scored <strong>HIGH</strong> automatically."
        "</div>",
        unsafe_allow_html=True,
    )

    client = get_client()
    if not client:
        return

    with st.form("flag_form", clear_on_submit=False):
        guest_id = st.selectbox(
            "Guest",
            options=list(GUEST_PERSONAS.keys()),
            format_func=lambda u: GUEST_PERSONAS[u]["name"],
        )
        # Scoped to food orders only - the demo's flag agent is tuned
        # for ingredient-vs-allergen checks, so we hard-code the trigger
        # type here and ask only for the order text.
        trigger = "food_order"
        payload = st.text_area(
            "What did the guest order?",
            placeholder="e.g. 'Grilled sea bass with chili oil, side salad with peanuts'",
            height=120,
            help="The dish names or ingredients from the food order.",
        )
        submitted = st.form_submit_button("Check against guest memory")

    if submitted:
        if guest_id not in st.session_state.guest_users:
            st.warning(f"No memory for {GUEST_PERSONAS[guest_id]['name']} in store.")
            return
        if not payload.strip():
            st.warning("Enter what the guest ordered before checking.")
            return

        placeholder = st.empty()
        log: list[str] = []
        try:
            render_status_pipeline(
                placeholder, log, "Cross-checking against safety memory…"
            )
            graph = FlagGraph()
            user = st.session_state.guest_users.get(guest_id)
            if user is None:
                st.error(f"Guest {guest_id} user not loaded. Cannot check flag.")
                return
            with _ops_span(
                "safety-flag", guest_id=guest_id, trigger_type=trigger
            ) as _span:
                state = graph.run(
                    client=client,
                    agentmem_user=user,
                    guest_id=guest_id,
                    guest_name=GUEST_PERSONAS[guest_id]["name"],
                    trigger_type=trigger,
                    trigger_payload=payload,
                    span=_span,
                )
            retrieval_ms = float(state.get("retrieval_ms") or 0.0)
            synthesis_ms = float(state.get("synthesis_ms") or 0.0)
            extras = []
            if state.get("write_ok"):
                extras.append("Flag persisted to role_front_desk memory")
            render_timing_pipeline(
                placeholder, retrieval_ms, synthesis_ms, extra=extras
            )
            flag = state.get("flag") or {}
            st.session_state.flags.append(
                {
                    "flag": flag,
                    "retrieval_ms": retrieval_ms,
                    "synthesis_ms": synthesis_ms,
                    "trigger_payload": payload,
                }
            )
            render_flag_card(flag, retrieval_ms=retrieval_ms, synthesis_ms=synthesis_ms)
        except Exception as exc:
            log.append(f"Error: {exc}")
            render_status_pipeline(placeholder, log)
            st.code(traceback.format_exc())

    if st.session_state.flags:
        st.markdown("### Past checks (this session)")
        for entry in reversed(st.session_state.flags):
            flag = entry.get("flag") or entry  # tolerate older entries
            r = entry.get("retrieval_ms", 0.0) if isinstance(entry, dict) else 0.0
            s = entry.get("synthesis_ms", 0.0) if isinstance(entry, dict) else 0.0
            with st.expander(
                f"{_humanise_flag_type(flag.get('type', 'flag'))} · {flag.get('conflict_summary', '-')[:80]}",
                expanded=False,
            ):
                render_flag_card(flag, retrieval_ms=r, synthesis_ms=s)


_FLAG_TYPE_LABELS = {
    "allergy_conflict": "Allergy conflict",
    "dietary_conflict": "Dietary conflict",
    "accessibility_issue": "Accessibility issue",
    "safety_hazard": "Safety hazard",
    "none": "None",
}

_TRIGGER_LABELS_VIEW = {
    "food_order": "Food order",
    "room_service_order": "Room service order",
    "dining_reservation": "Dining reservation",
    "booking_form": "Room booking",
}


def _humanise_flag_type(v: str) -> str:
    """Convert a raw flag-type key to a human-readable label."""
    if not v:
        return "-"
    return _FLAG_TYPE_LABELS.get(v.lower(), v.replace("_", " ").capitalize())


def _humanise_trigger(v: str) -> str:
    """Convert a raw trigger-type key to a human-readable label."""
    if not v:
        return "-"
    return _TRIGGER_LABELS_VIEW.get(v.lower(), v.replace("_", " ").capitalize())


def render_flag_card(f: dict, retrieval_ms: float = 0.0, synthesis_ms: float = 0.0):
    """Render a single safety/allergy flag card.

    Args:
        f: Flag dict as returned by :class:`FlagGraph`. Expected keys:
            ``has_flag``, ``severity``, ``type``, ``trigger``,
            ``conflict_summary``, ``evidence``, ``recommended_action``,
            ``citation``.
        retrieval_ms: Memory retrieval latency in milliseconds (shown in
            the timing footer).
        synthesis_ms: LLM synthesis latency in milliseconds (shown in
            the timing footer).
    """
    has_flag = bool(f.get("has_flag"))
    sev = (f.get("severity") or "none").lower()
    title_color = "#ff8a72" if has_flag else "#4caf82"
    title = "FLAG RAISED" if has_flag else "No conflict detected"
    citation = f.get("citation") or "-"
    timing_html = ""
    if retrieval_ms or synthesis_ms:
        timing_html = (
            f'<div style="color:rgba(26,26,26,0.55); font-size:0.78rem; margin-top:0.4rem;">'
            f"Memory search · {retrieval_ms:.0f}ms &nbsp;|&nbsp; AI response generation · {synthesis_ms:.0f}ms &nbsp;|&nbsp; "
            f"Total · {(retrieval_ms + synthesis_ms):.0f}ms</div>"
        )
    st.markdown(
        f"""
    <div class="ops-card">
        <h3 style="color:{title_color};">{title}</h3>
        <div class="kv-line"><span class="kv-key">Severity</span>
            <span class="kv-val">{severity_badge(sev)}</span></div>
        <div class="kv-line"><span class="kv-key">Conflict category</span>
            <span class="kv-val">{_humanise_flag_type(f.get("type", "none"))}</span></div>
        <div class="kv-line"><span class="kv-key">Form type</span>
            <span class="kv-val">{_humanise_trigger(f.get("trigger", ""))}</span></div>
        <div class="kv-line"><span class="kv-key">What conflicts</span>
            <span class="kv-val">{f.get("conflict_summary", "-")}</span></div>
        <div class="kv-line"><span class="kv-key">Why we flagged it</span>
            <span class="kv-val">{f.get("evidence", "-")}</span></div>
        <div class="kv-line"><span class="kv-key">Recommended action</span>
            <span class="kv-val">{f.get("recommended_action", "-")}</span></div>
        <div class="kv-line"><span class="kv-key">Source (memory ID)</span>
            <span class="kv-val" style="font-family:monospace; font-size:0.78rem;">{citation}</span></div>
        {timing_html}
    </div>
    """,
        unsafe_allow_html=True,
    )


# ═════════════════════════════════════════════════════════════════════
# VIEW: Group Event Pre-Brief
# ═════════════════════════════════════════════════════════════════════


def render_group_event():
    """Render the Group Event Pre-Brief view.

    Provides a form for entering new group booking details (organiser,
    event date, attendee count). On "Generate Brief" the
    :class:`GroupEventBriefGraph` retrieves the organiser's memory and
    synthesises a structured facilities brief, written to the
    ``role_events`` memory pool. Generated briefs are appended to
    ``st.session_state.group_briefs`` and displayed via
    :func:`render_group_brief_card`.
    """
    st.markdown("## Group Event Pre-Brief")
    st.markdown(
        '<span class="trigger-badge">Generated when a group booking is confirmed</span>'
        '<span class="trigger-badge">Pulls from organiser\'s history</span>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="color:rgba(26,26,26,0.6); font-size:0.85rem; margin-bottom:1.2rem;">'
        "When a new group booking is confirmed, this agent reads the organiser's past-event memory and "
        "auto-briefs facilities. The organiser is not the guest - accessibility needs and prior failures "
        "are pulled from the organiser's past events and applied to the new event."
        "</div>",
        unsafe_allow_html=True,
    )

    client = get_client()
    if not client:
        return

    with st.form("group_event_form", clear_on_submit=False):
        all_users = list(GUEST_PERSONAS.keys())
        organiser_id = st.selectbox(
            "Organiser",
            options=all_users,
            format_func=lambda u: (
                f"{GUEST_PERSONAS[u]['name']} ({GUEST_PERSONAS[u]['type']})"
            ),
        )
        event_date = st.date_input(
            "Event date", value=datetime.now() + timedelta(days=14)
        )
        attendees = st.number_input(
            "Attendee count",
            min_value=1,
            max_value=500,
            value=42,  # demo default matching Charlie's group size
        )
        submitted = st.form_submit_button("Generate facilities brief")

    if submitted:
        if organiser_id not in st.session_state.guest_users:
            st.warning(
                f"No memory for {GUEST_PERSONAS[organiser_id]['name']} in store."
            )
            return

        placeholder = st.empty()
        log: list[str] = []
        try:
            render_status_pipeline(
                placeholder, log, "Reading organiser's past event memory…"
            )
            graph = GroupEventBriefGraph()
            with _ops_span(
                "group-event-brief",
                organiser_id=organiser_id,
                event_date=str(event_date),
            ) as _span:
                state = graph.run(
                    client=client,
                    agentmem_user=st.session_state.guest_users.get(organiser_id),
                    organiser_id=organiser_id,
                    organiser_name=GUEST_PERSONAS[organiser_id]["name"],
                    event_date=str(event_date),
                    attendee_count=int(attendees),
                    span=_span,
                )
            retrieval_ms = float(state.get("retrieval_ms") or 0.0)
            synthesis_ms = float(state.get("synthesis_ms") or 0.0)
            extras = []
            if state.get("write_ok"):
                extras.append("Brief persisted to role_events memory")
            render_timing_pipeline(
                placeholder, retrieval_ms, synthesis_ms, extra=extras
            )
            brief = state.get("brief") or {}
            entry = {
                "organiser_id": organiser_id,
                "brief": brief,
                "retrieval_ms": retrieval_ms,
                "synthesis_ms": synthesis_ms,
            }
            st.session_state.group_briefs.append(entry)
            render_group_brief_card(
                brief,
                organiser_id=organiser_id,
                retrieval_ms=retrieval_ms,
                synthesis_ms=synthesis_ms,
            )
        except Exception as exc:
            log.append(f"Error: {exc}")
            render_status_pipeline(placeholder, log)
            st.code(traceback.format_exc())

    if st.session_state.group_briefs:
        st.markdown("### Recent briefs")
        for entry in reversed(st.session_state.group_briefs):
            brief = entry.get("brief") or entry
            oid = entry.get("organiser_id") if isinstance(entry, dict) else None
            r = entry.get("retrieval_ms", 0.0) if isinstance(entry, dict) else 0.0
            s = entry.get("synthesis_ms", 0.0) if isinstance(entry, dict) else 0.0
            label = f"{brief.get('organiser', '')} · {brief.get('event_date', '')}"
            with st.expander(label, expanded=False):
                render_group_brief_card(
                    brief, organiser_id=oid, retrieval_ms=r, synthesis_ms=s
                )


def render_group_brief_card(
    b: dict,
    organiser_id: str | None = None,
    retrieval_ms: float = 0.0,
    synthesis_ms: float = 0.0,
):
    """Render a single group-event facilities brief card.

    Args:
        b: Brief dict as returned by :class:`GroupEventBriefGraph`.
            Expected keys: ``organiser``, ``event_date``,
            ``attendee_count``, ``past_failures``,
            ``accessibility_needs``, ``privacy_flags``,
            ``facilities_actions``, ``summary``.
        organiser_id: User ID of the event organiser (used for display).
        retrieval_ms: Memory retrieval latency in milliseconds.
        synthesis_ms: LLM synthesis latency in milliseconds.
    """
    # Detect "no past events" state - empty failures + accessibility +
    # privacy + actions suggests this organiser has no group history.
    has_history = any(
        [
            b.get("past_failures"),
            b.get("accessibility_needs"),
            b.get("privacy_flags"),
            b.get("facilities_actions"),
        ]
    )
    if not has_history:
        name = b.get("organiser") or (
            GUEST_PERSONAS.get(organiser_id, {}).get("name", organiser_id)
            if organiser_id
            else "Organiser"
        )
        timing_html = ""
        if retrieval_ms or synthesis_ms:
            timing_html = (
                f'<div style="color:rgba(26,26,26,0.55); font-size:0.78rem; margin-top:0.4rem;">'
                f"Memory search · {retrieval_ms:.0f}ms &nbsp;|&nbsp; LLM synthesis · {synthesis_ms:.0f}ms &nbsp;|&nbsp; "
                f"Total · {(retrieval_ms + synthesis_ms):.0f}ms</div>"
            )
        st.markdown(
            f"""
        <div class="ops-card">
            <h3>{name} · Event {b.get("event_date", "")}</h3>
            <div class="kv-line"><span class="kv-key">Status</span>
                <span class="kv-val" style="color:rgba(230,32,32,0.8);">Has not organised large events before</span></div>
            <div class="kv-line"><span class="kv-key">Attendees</span>
                <span class="kv-val">{b.get("attendee_count", 0)}</span></div>
            <div class="kv-line"><span class="kv-key">Summary</span>
                <span class="kv-val">{b.get("summary", "No prior event history found in memory.")}</span></div>
            {timing_html}
        </div>
        """,
            unsafe_allow_html=True,
        )
        return

    timing_html = ""
    if retrieval_ms or synthesis_ms:
        timing_html = (
            f'<div style="color:rgba(26,26,26,0.55); font-size:0.78rem; margin-top:0.4rem;">'
            f"Memory search · {retrieval_ms:.0f}ms &nbsp;|&nbsp; LLM synthesis · {synthesis_ms:.0f}ms &nbsp;|&nbsp; "
            f"Total · {(retrieval_ms + synthesis_ms):.0f}ms</div>"
        )
    st.markdown(
        f"""
    <div class="ops-card">
        <h3>{b.get("organiser", "")} · Event {b.get("event_date", "")}</h3>
        <div class="kv-line"><span class="kv-key">Attendees</span>
            <span class="kv-val">{b.get("attendee_count", 0)}</span></div>
        <div class="kv-line"><span class="kv-key">Summary</span>
            <span class="kv-val">{b.get("summary", "")}</span></div>
        {timing_html}
    """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Past failures**")
        for f in b.get("past_failures") or []:
            sev = f.get("severity", "low")
            st.markdown(
                f"""
            <div class="list-item {"warning" if sev == "high" else ""}">
                <strong>{f.get("event", "")}</strong> - {f.get("issue", "")}
                {severity_badge(sev)}
            </div>
            """,
                unsafe_allow_html=True,
            )
        if not b.get("past_failures"):
            st.markdown(
                '<div class="list-item">No prior failures.</div>',
                unsafe_allow_html=True,
            )

    with c2:
        st.markdown("**Accessibility needs**")
        for n in b.get("accessibility_needs") or []:
            st.markdown(
                f"""
            <div class="list-item">
                {n.get("need", "")}
                <span style="color:rgba(230,32,32,0.6); font-size:0.72rem;">
                    · {n.get("source", "")}
                </span>
            </div>
            """,
                unsafe_allow_html=True,
            )
        if not b.get("accessibility_needs"):
            st.markdown(
                '<div class="list-item">No accessibility needs noted.</div>',
                unsafe_allow_html=True,
            )

    st.markdown("**Privacy flags**")
    for p in b.get("privacy_flags") or []:
        st.markdown(f'<div class="list-item warning">{p}</div>', unsafe_allow_html=True)
    if not b.get("privacy_flags"):
        st.markdown(
            '<div class="list-item">No privacy flags.</div>', unsafe_allow_html=True
        )

    st.markdown("**Facilities actions**")
    for a in b.get("facilities_actions") or []:
        st.markdown(f'<div class="list-item">{a}</div>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════
# VIEW: Monthly Ops Digest
# ═════════════════════════════════════════════════════════════════════


def render_digest():
    """Render the Monthly Ops Digest view.

    Provides a period picker and "Run Digest" button. On trigger the
    :class:`DigestGraph` fans out memory searches across all guests in
    parallel and synthesises a structured operational digest, written to
    the ``role_gm`` memory pool. The result is cached in
    ``st.session_state.digest`` and displayed via
    :func:`render_digest_card`.
    """
    st.markdown("## Monthly Ops Digest")
    st.markdown(
        '<span class="trigger-badge">Runs monthly (or on demand)</span>'
        '<span class="trigger-badge">Reads across all guests</span>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="color:rgba(26,26,26,0.6); font-size:0.85rem; margin-bottom:1.2rem;">'
        "The digest agent reads memory across all guests in parallel and surfaces recurring "
        "patterns - complaints, requests, spend signals - for the GM. No analyst required."
        "</div>",
        unsafe_allow_html=True,
    )

    client = get_client()
    if not client:
        return

    last_run = st.session_state.digest_run_ts or "Never"
    st.markdown(
        f"""
    <div class="ops-card">
        <div class="kv-line"><span class="kv-key">Last run</span>
            <span class="kv-val">{last_run}</span></div>
        <div class="kv-line"><span class="kv-key">Coverage</span>
            <span class="kv-val">{len(st.session_state.guest_users)} guests on file</span></div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    if st.button("Run digest now", type="primary"):
        placeholder = st.empty()
        log: list[str] = []
        try:
            user_list = [
                (uid, st.session_state.guest_users.get(uid))
                for uid in st.session_state.guest_users.keys()
            ]
            user_list = [(uid, u) for uid, u in user_list if u is not None]
            render_status_pipeline(
                placeholder, log, "Fanning out memory search across all guests…"
            )
            graph = DigestGraph()
            period = datetime.now().strftime("%B %Y")
            with _ops_span("monthly-ops-digest", period=period) as _span:
                state = graph.run(
                    client=client,
                    user_list=user_list,
                    period=period,
                    span=_span,
                )
            retrieval_ms = float(state.get("retrieval_ms") or 0.0)
            synthesis_ms = float(state.get("synthesis_ms") or 0.0)
            extras = []
            if state.get("write_ok"):
                extras.append("Digest persisted to role_gm memory")
            render_timing_pipeline(
                placeholder, retrieval_ms, synthesis_ms, extra=extras
            )
            st.session_state.digest = {
                "digest": state.get("digest"),
                "retrieval_ms": retrieval_ms,
                "synthesis_ms": synthesis_ms,
            }
            st.session_state.digest_run_ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        except Exception as exc:
            log.append(f"Error: {exc}")
            render_status_pipeline(placeholder, log)
            st.code(traceback.format_exc())

    entry = st.session_state.digest
    if entry:
        if isinstance(entry, dict) and "digest" in entry:
            render_digest_card(
                entry["digest"] or {},
                retrieval_ms=entry.get("retrieval_ms", 0.0),
                synthesis_ms=entry.get("synthesis_ms", 0.0),
            )
        else:
            render_digest_card(entry)


def render_digest_card(d: dict, retrieval_ms: float = 0.0, synthesis_ms: float = 0.0):
    """Render a single monthly ops digest card.

    Args:
        d: Digest dict as returned by :class:`DigestGraph`. Expected keys:
            ``period``, ``headline``, ``recurring_complaints``,
            ``recurring_requests``, ``spend_or_loyalty_signals``,
            ``operational_action_items``.
        retrieval_ms: Memory retrieval latency in milliseconds.
        synthesis_ms: LLM synthesis latency in milliseconds.
    """
    timing_html = ""
    if retrieval_ms or synthesis_ms:
        timing_html = (
            f'<div style="color:rgba(26,26,26,0.55); font-size:0.78rem; margin-top:0.4rem;">'
            f"Memory search · {retrieval_ms:.0f}ms &nbsp;|&nbsp; LLM synthesis · {synthesis_ms:.0f}ms &nbsp;|&nbsp; "
            f"Total · {(retrieval_ms + synthesis_ms):.0f}ms</div>"
        )
    st.markdown(
        f"""
    <div class="ops-card">
        <h3>Digest · {d.get("period", "")}</h3>
        <div class="kv-line"><span class="kv-key">Headline</span>
            <span class="kv-val">{d.get("headline", "")}</span></div>
        {timing_html}
    </div>
    """,
        unsafe_allow_html=True,
    )

    st.markdown("**Recurring complaints**")
    for c in d.get("recurring_complaints") or []:
        sev = c.get("severity", "low")
        st.markdown(
            f"""
        <div class="list-item {"warning" if sev == "high" else ""}">
            <strong>{c.get("issue", "")}</strong>
            · count: {c.get("count", 0)} {severity_badge(sev)}
        </div>
        """,
            unsafe_allow_html=True,
        )
    if not d.get("recurring_complaints"):
        st.markdown(
            '<div class="list-item">No recurring complaints this period.</div>',
            unsafe_allow_html=True,
        )

    st.markdown("**Recurring requests**")
    for r in d.get("recurring_requests") or []:
        st.markdown(
            f"""
        <div class="list-item">
            <strong>{r.get("request", "")}</strong> · count: {r.get("count", 0)}
        </div>
        """,
            unsafe_allow_html=True,
        )
    if not d.get("recurring_requests"):
        st.markdown(
            '<div class="list-item">No recurring requests this period.</div>',
            unsafe_allow_html=True,
        )

    st.markdown("**Spend / loyalty signals**")
    for s in d.get("spend_or_loyalty_signals") or []:
        st.markdown(f'<div class="list-item">{s}</div>', unsafe_allow_html=True)

    st.markdown("**What the GM should act on**")
    for a in d.get("operational_action_items") or []:
        st.markdown(f'<div class="list-item">{a}</div>', unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════
# VIEW: Role Memory
# ═════════════════════════════════════════════════════════════════════


def render_role_memory():
    """Render the Role Knowledge Base view.

    Read-only view of all artifacts written to role-namespaced memory
    pools (``role_gm``, ``role_front_desk``, ``role_events``,
    ``role_facilities``). Artifacts are surfaced by a keyword search
    within each role namespace; raw JSON blocks are rendered in
    collapsible expanders.
    """
    st.markdown("## Role Knowledge Base")
    st.markdown(
        '<span class="trigger-badge">Read-only</span>'
        '<span class="trigger-badge">Survives staff turnover</span>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="color:rgba(26,26,26,0.6); font-size:0.85rem; margin-bottom:1.2rem;">'
        "Every operational record is saved under a role (front desk, GM, events, facilities), "
        "not under an individual staff member. A new GM joining the property inherits everything "
        "the previous GM knew."
        "</div>",
        unsafe_allow_html=True,
    )

    client = get_client()
    if not client:
        return

    active_role = ROLES[st.session_state.active_role]
    readable = active_role.get("can_read_role_memory", (st.session_state.active_role,))
    options = [r for r in ROLES.keys() if r in readable]

    if not options:
        st.markdown(
            '<div class="list-item">You do not have permission to inspect '
            "any role memory pool.</div>",
            unsafe_allow_html=True,
        )
        return

    if len(options) == 1:
        role_id = options[0]
        st.markdown(
            f'<div style="color:rgba(26,26,26,0.65); font-size:0.85rem; margin-bottom:0.6rem;">'
            f"You can inspect: <strong>{ROLES[role_id]['name']}</strong> only. "
            f"Other role pools are restricted by your current role.</div>",
            unsafe_allow_html=True,
        )
    else:
        try:
            default_idx = options.index(st.session_state.active_role)
        except ValueError:
            default_idx = 0
        role_id = st.selectbox(
            "Inspect role",
            options=options,
            format_func=lambda r: ROLES[r]["name"],
            index=default_idx,
        )

    try:
        role_user = client.get_user(user_id=role_id)
    except Exception:
        st.markdown(
            '<div class="list-item">No records yet for this role. Run any operations action '
            "(briefing, allergy check, digest, group brief) from the other views to populate this.</div>",
            unsafe_allow_html=True,
        )
        return

    try:
        sess = role_user.get_session(session_id="ops_log")
        result = sess.list_memories(limit=MEMORY_K["role_memory"])
        memory_blocks = getattr(result, "memory_blocks", None) or []
    except Exception as e:
        st.error(f"Could not read role memory: {e}")
        return

    if not memory_blocks:
        st.markdown(
            '<div class="list-item">No records written under this role yet.</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(f"### {ROLES[role_id]['name']} · {len(memory_blocks)} record(s)")
    for block in memory_blocks:
        fact = getattr(block, "fact", None) or ""
        msg = getattr(block, "message", None)

        if fact:
            # New format: "{label}: {json_payload}"
            if ": " in fact:
                label, _, payload = fact.partition(": ")
            else:
                label, payload = fact[:80] or "(unlabelled)", fact
        elif msg:
            # Old chat format
            label = getattr(msg, "user_content", "") or "(unlabelled)"
            payload = getattr(msg, "assistant_content", "") or ""
        else:
            continue

        try:
            parsed = json.loads(payload)
            payload_disp = json.dumps(parsed, indent=2, ensure_ascii=False)
        except Exception as exc:
            print(f"warning: role memory payload JSON parse failed — {exc}")
            payload_disp = payload
        with st.expander(label[:120]):
            st.code(payload_disp, language="json")


# ═════════════════════════════════════════════════════════════════════
# VIEW: How It Works (workflow diagrams)
# ═════════════════════════════════════════════════════════════════════


def render_how_it_works():
    """Render the How It Works explanatory view.

    Static educational content describing the multi-agent architecture,
    memory namespaces, and the LangGraph pipeline topology for each
    ops agent. No side effects.
    """
    st.markdown("## How It Works")
    st.markdown(
        '<div style="color:rgba(26,26,26,0.7); font-size:0.9rem; margin-bottom:1.2rem;">'
        "Five LangGraph agents share <strong>one</strong> Couchbase-backed Couchbase Agent Memory store. "
        "Guests live under their own <code>user_id</code>. Ops artifacts (briefings, flags, digests, "
        "group briefs) are written under <strong>role namespaces</strong> so institutional knowledge "
        "persists across staff turnover."
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown("### System overview")
    st.code(
        """
                ┌────────────────────────────────────────────┐
                │     Couchbase Agent Memory (Couchbase-backed)            │
                │     Single shared memory store             │
                │                                            │
                │   Guest namespaces                         │
                │     alice_chen, bob_morrison, charlie_wu   │
                │                                            │
                │   Role namespaces                          │
                │     role_gm, role_front_desk,              │
                │     role_events, role_facilities           │
                └────────────────────────────────────────────┘
                          ▲ ▲ ▲ ▲ ▲ ▲ ▲     (read / write)
                          │ │ │ │ │ │ │
   ConciergeGraph ────────┘ │ │ │ │ │ │   reads guest, writes new turns
   BriefingGraph ───────────┘ │ │ │ │ │   reads guest, writes role_front_desk
   FlagGraph ─────────────────┘ │ │ │ │   reads guest (safety scope), writes flag
   DigestGraph ─────────────────┘ │ │ │   reads many guests, writes role_gm
   GroupEventBriefGraph ──────────┘ │ │   reads organiser, writes role_events
   Role Memory inspector ───────────┘ │   reads role_*
                                      │
                          ┌───────────┴───────────┐
                          │  Two Streamlit UIs    │
                          │  agentmem_hotel.py    │
                          │  agentmem_hotel_ops.py│
                          └───────────────────────┘
""",
        language="text",
    )

    st.markdown("### Per-agent LangGraph topology")

    diagrams = [
        (
            "ConciergeGraph",
            "guest chat",
            """
START
  │
  ▼
search-refinement   ──  refines raw query into 2–3 search strings
  │
  ▼
memory-search       ──  cross-session retrieval against guest namespace
  │
  ▼
response-agent      ──  generates reply, persists turn back to guest session
  │
  ▼
END
""",
        ),
        (
            "BriefingGraph",
            "pre-arrival briefing (manual / scheduled)",
            """
START
  │
  ▼
memory-search (fan-out, parallel)
   ├─ "room preference floor view"
   ├─ "complaint issue problem wait service"
   ├─ "allergy dietary food restriction"
   ├─ "occasion anniversary celebration"
   ├─ "loyalty tier spend booking"
   ├─ "third party husband wife companion family"
   └─ "recovery apology compensation upgrade"
  │
  ▼
briefing-agent      ──  LLM synthesises structured briefing JSON
  │                     (preferences, prior_complaints, safety_flags,
  │                      recovery_actions, summary)
  ▼                     and writes it to role_front_desk memory
END
""",
        ),
        (
            "FlagGraph",
            "form-triggered allergy / safety check",
            """
START
  │
  ▼
memory-search (fan-out, parallel · safety-scoped)
   ├─ "allergy allergic reaction"
   ├─ "dietary restriction intolerance"
   ├─ "fish shellfish nuts gluten dairy"
   ├─ "mobility wheelchair accessibility"
   ├─ "medical condition health"
   └─ "safety hazard incident"
  │   each excerpt carries a [block:<id>] tag so the LLM can cite it
  ▼
flag-agent          ──  LLM checks form payload vs memory
  │                     emits {has_flag, severity, type, conflict, action,
  │                            citation: <block_id>}
  ▼                     writes flag event to role_front_desk if flagged
END
""",
        ),
        (
            "DigestGraph",
            "monthly ops digest (multi-user)",
            """
START
  │
  ▼
multi-user-memory-fan-out
   ├─ for each guest in store …
   │     ├─ "complaint issue problem"
   │     ├─ "wait delay slow"
   │     ├─ "request preference repeat"
   │     ├─ "spend booking loyalty tier"
   │     ├─ "allergy dietary safety"
   │     ├─ "event group facilities"
   │     └─ "compliment positive feedback"
   │   → all run in parallel
  │
  ▼
digest-agent        ──  LLM aggregates, surfaces patterns
  │                     (recurring_complaints, recurring_requests,
  │                      spend_or_loyalty_signals, action_items)
  ▼                     writes report to role_gm memory
END
""",
        ),
        (
            "GroupEventBriefGraph",
            "new group booking confirmation",
            """
START
  │
  ▼
memory-search (fan-out, parallel · organiser scope)
   ├─ "event past failure issue complaint AV breakout"
   ├─ "accessibility wheelchair mobility ramp"
   ├─ "privacy confidentiality executive retreat"
   ├─ "catering dietary group meal allergy"
   ├─ "schedule logistics setup teardown"
   ├─ "attendee feedback post-event"
   └─ "room reservation block accessible"
  │
  ▼
group-event-brief-agent  ── LLM synthesises facilities brief
  │                         (past_failures, accessibility_needs,
  │                          privacy_flags, facilities_actions, summary)
  ▼                         writes brief to role_events memory
END
""",
        ),
    ]

    for name, subtitle, diagram in diagrams:
        with st.expander(f"{name} - {subtitle}", expanded=False):
            st.code(diagram, language="text")

    st.markdown("### Where each agent reads / writes")
    st.markdown("""
| Agent | Reads from | Writes to | Triggered by |
|---|---|---|---|
| ConciergeGraph | Guest namespace (all sessions) | Guest namespace (current session) | Guest chat message |
| BriefingGraph | Guest namespace (all sessions) | `role_front_desk` | Manual / scheduled timer |
| FlagGraph | Guest namespace (safety scope) | `role_front_desk` (only if `has_flag`) | Form submission |
| DigestGraph | All guest namespaces (parallel) | `role_gm` | Monthly schedule (or manual) |
| GroupEventBriefGraph | Organiser namespace (event scope) | `role_events` | New group booking confirmed |
""")

    st.markdown("### Role-based memory")
    st.markdown(
        '<div style="color:rgba(26,26,26,0.75); font-size:0.88rem; line-height:1.7;">'
        "Memory belongs to the <strong>role</strong>, not the person. When a new GM joins, "
        "they inherit the same memory pool as the previous GM - every digest ever generated, "
        "every escalation note ever written. Same for front desk and events. "
        "Role memory is just a Couchbase Agent Memory user (e.g. <code>role_gm</code>) that ops agents write to. "
        "You can see what each role currently knows in the <strong>Role Memory</strong> view."
        "</div>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────
# Main view dispatch
# ─────────────────────────────────────────────

with main_col:
    view = st.session_state.active_view
    allowed_views = ROLES[st.session_state.active_role].get("allowed_views", VIEWS)

    # Defence-in-depth: if the active view is not allowed for this
    # role (e.g. set programmatically before a permission change),
    # silently bounce them back to the role's default view.
    if view not in allowed_views:
        fallback = ROLES[st.session_state.active_role].get("default_view", "Dashboard")
        if fallback in allowed_views:
            st.session_state.active_view = fallback
            view = fallback
        elif allowed_views:
            st.session_state.active_view = allowed_views[0]
            view = allowed_views[0]
        else:
            st.markdown(
                '<div class="ops-card"><h3>Access denied</h3>'
                "<div>This role has no views configured. Contact admin.</div></div>",
                unsafe_allow_html=True,
            )
            view = None

    if view == "Dashboard":
        render_dashboard()
    elif view == "Log Guest Call":
        render_call_log()
    elif view == "Pre-Arrival Briefings":
        render_briefings()
    elif view == "Allergy & Safety":
        render_flags()
    elif view == "Group Event Pre-Brief":
        render_group_event()
    elif view == "Monthly Ops Digest":
        render_digest()
    elif view == "Role Memory":
        render_role_memory()
    elif view == "How It Works":
        render_how_it_works()
    elif view is not None:
        st.markdown("Select a view from the sidebar.")


# ─────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────

st.markdown(
    """
<div style="text-align:center; padding:2rem 0 1rem;
            color:rgba(230,32,32,0.2); font-size:0.7rem;
            letter-spacing:0.2em; text-transform:uppercase;">
    Couchbase Agent Memory Hotel · Operations Portal · Powered by Couchbase Agent Memory
</div>
""",
    unsafe_allow_html=True,
)
