"""
Couchbase Agent Memory Hotel — Guest Concierge Portal

A guest-facing Streamlit interface for the Couchbase Agent Memory Hotel demo.
Shows Alice (Corporate), Bob (Occasion), and Charlie (Group Organizer) personas.

Run:
    streamlit run agentmem_hotel.py
"""

from __future__ import annotations

import html
import os
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

import datetime

import streamlit as st
from agentmemory import AgentMemoryClient
from dotenv import load_dotenv
from agents.agentc_catalog import get_catalog
from agents.concierge_agent import ConciergeGraph
from agents.profile_overview_agent import ProfileOverviewGraph
from prompts import (
    HOTEL_CONCIERGE_NO_MEMORY_TEMPLATE,
    HOTEL_CONCIERGE_WITH_MEMORY_TEMPLATE,
)

load_dotenv()

# ─────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="Couchbase Agent Memory Hotel — Concierge",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────
# Global CSS — dark luxury aesthetic
# ─────────────────────────────────────────────

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

*, *::before, *::after { box-sizing: border-box; }

html, body, [data-testid="stAppViewContainer"] {
    background: #FFF8EE !important;
    color: #1A1A1A !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
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

.persona-card {
    border: 1px solid rgba(230, 32, 32, 0.15);
    border-radius: 8px;
    padding: 1rem 1.2rem;
    cursor: pointer;
    transition: all 0.25s ease;
    background: rgba(255, 255, 255, 0.5);
    margin-bottom: 0.6rem;
}

.persona-card:hover {
    border-color: rgba(230, 32, 32, 0.4);
    background: rgba(230, 32, 32, 0.04);
}

.persona-card.active {
    border-color: #E62020;
    background: rgba(230, 32, 32, 0.06);
}

.persona-name {
    font-family: 'Inter', sans-serif;
    font-size: 1.05rem;
    font-weight: 600;
    color: #1A1A1A;
}

.persona-meta {
    font-size: 0.72rem;
    color: rgba(230, 32, 32, 0.7);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-top: 0.15rem;
}

.persona-desc {
    font-size: 0.8rem;
    color: rgba(26, 26, 26, 0.55);
    margin-top: 0.4rem;
    line-height: 1.4;
}

.guest-card {
    background: linear-gradient(135deg, rgba(230,32,32,0.06) 0%, rgba(255,248,238,0.8) 100%);
    border: 1px solid rgba(230, 32, 32, 0.2);
    border-radius: 10px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1.2rem;
}

.guest-avatar {
    width: 52px;
    height: 52px;
    border-radius: 50%;
    background: linear-gradient(135deg, #E62020, #F7941D);
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'Inter', sans-serif;
    font-size: 1.2rem;
    font-weight: 700;
    color: #ffffff;
    float: left;
    margin-right: 1rem;
}

.guest-name {
    font-family: 'Inter', sans-serif;
    font-size: 1.2rem;
    font-weight: 600;
    color: #1A1A1A;
}


.guest-stay {
    font-size: 0.78rem;
    color: rgba(26, 26, 26, 0.5);
    margin-top: 0.2rem;
}

.memory-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid rgba(230, 32, 32, 0.1);
    clear: both;
}

.memory-pill {
    font-size: 0.72rem;
    padding: 0.25rem 0.7rem;
    border-radius: 20px;
    border: 1px solid rgba(230, 32, 32, 0.2);
    background: rgba(230, 32, 32, 0.04);
    color: rgba(26, 26, 26, 0.75);
    white-space: nowrap;
}

.memory-pill.warning {
    border-color: rgba(198, 32, 32, 0.3);
    background: rgba(198, 32, 32, 0.05);
    color: rgba(180, 30, 30, 0.85);
}

.stButton > button {
    border-radius: 6px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.8rem !important;
    font-weight: 400 !important;
    padding: 0.5rem 0.8rem !important;
    text-align: left !important;
    width: 100% !important;
    background: rgba(230, 32, 32, 0.04) !important;
    border: 1px solid rgba(230, 32, 32, 0.15) !important;
    color: rgba(26, 26, 26, 0.8) !important;
    transition: all 0.2s !important;
    white-space: normal !important;
    height: auto !important;
    min-height: 2.5rem !important;
}

.stButton > button:hover {
    background: rgba(230, 32, 32, 0.09) !important;
    border-color: rgba(230, 32, 32, 0.35) !important;
    color: #1A1A1A !important;
    transform: none !important;
    box-shadow: none !important;
}

.stButton > button:active,
.stButton > button:focus {
    background: rgba(230, 32, 32, 0.14) !important;
    border-color: rgba(230, 32, 32, 0.5) !important;
    color: #1A1A1A !important;
    box-shadow: none !important;
    outline: none !important;
}

/* Primary button (Sign In, etc.) */
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

.chat-area {
    height: calc(100vh - 320px);
    overflow-y: auto;
    padding: 1rem 0.5rem;
    scrollbar-width: thin;
    scrollbar-color: rgba(230, 32, 32, 0.2) transparent;
}

.msg-guest {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 1rem;
}

.msg-guest .bubble {
    background: rgba(230, 32, 32, 0.08);
    border: 1px solid rgba(230, 32, 32, 0.2);
    border-radius: 16px 16px 4px 16px;
    padding: 0.8rem 1.1rem;
    max-width: 70%;
    font-size: 0.88rem;
    color: #1A1A1A;
    line-height: 1.5;
}

.msg-concierge {
    display: flex;
    justify-content: flex-start;
    margin-bottom: 0.5rem;
    gap: 0.7rem;
}

.concierge-avatar {
    width: 34px;
    height: 34px;
    border-radius: 50%;
    background: linear-gradient(135deg, #E62020, #F7941D);
    border: none;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.85rem;
    font-weight: 700;
    color: white;
    flex-shrink: 0;
    margin-top: 0.2rem;
}

.msg-concierge .bubble {
    background: rgba(255, 255, 255, 0.75);
    border: 1px solid rgba(230, 32, 32, 0.12);
    border-left: 2px solid rgba(230, 32, 32, 0.5);
    border-radius: 4px 16px 16px 16px;
    padding: 0.8rem 1.1rem;
    max-width: 75%;
    font-size: 0.88rem;
    color: rgba(26, 26, 26, 0.9);
    line-height: 1.6;
}

.concierge-label {
    font-size: 0.65rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: rgba(230, 32, 32, 0.6);
    margin-bottom: 0.3rem;
}

.status-pipeline {
    background: rgba(255, 255, 255, 0.8);
    border: 1px solid rgba(230, 32, 32, 0.12);
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

.memory-update-card {
    background: rgba(76, 175, 130, 0.05);
    border: 1px solid rgba(76, 175, 130, 0.2);
    border-radius: 8px;
    padding: 0.7rem 1rem;
    margin: 0.5rem 0 1rem 3rem;
    font-size: 0.76rem;
    color: rgba(50, 120, 80, 0.8);
}

.memory-update-title {
    font-size: 0.7rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #4caf82;
    margin-bottom: 0.35rem;
    font-weight: 500;
}

.memory-update-item {
    padding: 0.1rem 0;
    color: rgba(50, 120, 80, 0.7);
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

/* Selectbox */
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

/* Labels, captions, text everywhere */
label, [data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] label {
    color: #1A1A1A !important;
}
[data-testid="stMarkdown"] p,
[data-testid="stMarkdown"] li,
[data-testid="stMarkdown"] strong,
[data-testid="stMarkdown"] a { color: #1A1A1A !important; }
[data-testid="stCaptionContainer"] p { color: rgba(26,26,26,0.6) !important; }

/* Radio */
[data-testid="stRadio"] p,
[data-testid="stRadio"] label,
[data-testid="stRadio"] span { color: #1A1A1A !important; }

/* Alerts / info / warning / success boxes */
[data-testid="stAlert"] { background: rgba(255,255,255,0.85) !important; }
[data-testid="stAlert"] p,
[data-testid="stAlert"] div { color: #1A1A1A !important; }
.stAlert p { color: #1A1A1A !important; }

/* Expanders */
[data-testid="stExpander"] details {
    background: rgba(255,255,255,0.55) !important;
    border: 1px solid rgba(230,32,32,0.1) !important;
    border-radius: 8px !important;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary p { color: #1A1A1A !important; }

/* Code blocks */
[data-testid="stCode"] pre,
code { background: rgba(255,255,255,0.7) !important; color: #1A1A1A !important; }

/* Spinner */
[data-testid="stSpinner"] p { color: #1A1A1A !important; }

/* Columns gap */
[data-testid="stHorizontalBlock"] { gap: 1.5rem; }

/* ── Chat input bar ── */
[data-testid="stChatInput"] {
    background: #ffffff !important;
    border: 1px solid rgba(230, 32, 32, 0.2) !important;
    border-radius: 10px !important;
}
[data-testid="stChatInput"] textarea,
[data-testid="stChatInput"] * {
    background: #ffffff !important;
    color: #1A1A1A !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.88rem !important;
}
[data-testid="stChatInput"] button { color: #E62020 !important; background: transparent !important; }

/* Bottom fixed bar – must be fully opaque cream so chat input never floats on black */
[data-testid="stBottom"],
[data-testid="stBottom"] > div {
    background: #FFF8EE !important;
    padding-bottom: 0.5rem !important;
}
[data-testid="stBottom"] > div > div {
    background: #FFF8EE !important;
}

[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"]:last-child,
section.main > div[data-testid="stVerticalBlock"] {
    padding-bottom: 110px !important;
}

hr { border-color: rgba(230, 32, 32, 0.1) !important; margin: 0.8rem 0 !important; }

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(230, 32, 32, 0.2); border-radius: 2px; }

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
# Persona definitions
# ─────────────────────────────────────────────

PERSONAS = {
    "alice": {
        "user_id": "alice_chen",
        "display_name": "Alice",
        "full_name": "Alice",
        "type": "Corporate Traveler",
        "desc": "Frequent business traveler. Dense history, high stakes.",
        "initials": "AC",
        "password": "123",
    },
    "bob": {
        "user_id": "bob_morrison",
        "display_name": "Bob",
        "full_name": "Bob",
        "type": "Occasion Traveler",
        "desc": "Anniversary stays, emotionally significant trips.",
        "initials": "BO",
        "password": "123",
    },
    "charlie": {
        "user_id": "charlie_wu",
        "display_name": "Charlie",
        "full_name": "Charlie",
        "type": "Group Organizer",
        "desc": "Books for 30–50 people. Doesn't stay himself.",
        "initials": "CM",
        "password": "123",
    },
}


# ─────────────────────────────────────────────
# Session state init
# ─────────────────────────────────────────────


def init_state():
    """Initialise Streamlit session state with default values.

    Idempotent: existing keys are not overwritten, so this can be called
    at module level on every Streamlit rerun without resetting live state.
    """
    defaults = {
        "authenticated": False,
        "login_attempts": 0,
        "active_persona": None,
        "agentmem_user": None,
        "agentmem_session": None,
        "current_session_id": None,  # track which session we're viewing
        "all_sessions_for_persona": [],  # list of available sessions for current persona
        "chat_messages": [],  # list of dicts: role, content, status_log, memory_update
        "pending_prompt": None,
        "profile_overview": None,  # cached profile overview {visits, preferences, dislikes, complaints}
        "profile_loading": False,  # flag to prevent multiple simultaneous loads
        "profile_persona": None,  # track which persona this profile belongs to
        "login_mode": "signin",  # "signin", "newuser", or "user_created"
        "is_session_readonly": False,  # True when viewing a previous (non-active) session
        "created_user_name": None,  # name of newly created user (for user_created screen)
        "created_user_ms": 0,  # ms taken to create user (for user_created screen)
        "ended_session_ids": set(),  # session_ids the user has explicitly ended this app session
        "memory_mode": "persistent",  # "persistent" | "stay" | "anonymous" (GDPR retention policy)
        "memory_ttl_seconds": 0,  # 0 = never expire; only meaningful when mode == "stay"
        "memory_ttl_label": "Forever",  # human-readable label for the active policy
        "show_delete_confirmation": False,  # flag to show delete confirmation dialog
        "deletion_complete": False,  # flag to show deletion success message
        "deletion_result": None,  # deletion result with timing info
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


# ─────────────────────────────────────────────
# Authentication helpers
# ─────────────────────────────────────────────


def authenticate(user_id: str, password: str) -> bool:
    """Authenticate a user against the persona registry or the default password.

    Predefined personas are checked against their individual passwords.
    Dynamically created users use the default password ``"123"``.

    Args:
        user_id: User identifier (persona key or dynamic user ID).
        password: Password submitted by the user.

    Returns:
        ``True`` if authentication succeeded; ``False`` otherwise.
        Also updates ``st.session_state.login_attempts``.
    """
    # Check if it's a predefined persona
    if user_id in PERSONAS:
        if PERSONAS[user_id]["password"] == password:
            st.session_state.authenticated = True
            st.session_state.active_persona = user_id
            st.session_state.login_attempts = 0
            return True
    else:
        # For new users, default password is "123"
        if password == "123":
            st.session_state.authenticated = True
            st.session_state.active_persona = user_id
            st.session_state.login_attempts = 0
            return True

    st.session_state.login_attempts += 1
    return False


def logout():
    """Reset all authentication and session state for a clean sign-out.

    Clears the authenticated flag, active persona, all session references,
    and the profile cache. After calling this the app re-shows the login
    screen on the next Streamlit rerun.
    """
    st.session_state.authenticated = False
    st.session_state.active_persona = None
    st.session_state.login_attempts = 0
    st.session_state.agentmem_user = None
    st.session_state.agentmem_session = None
    st.session_state.current_session_id = None
    st.session_state.all_sessions_for_persona = []
    st.session_state.chat_messages = []
    st.session_state.profile_overview = None
    st.session_state.profile_loading = False
    st.session_state.profile_persona = None
    st.session_state.login_mode = "signin"
    st.session_state.is_session_readonly = False
    st.session_state.created_user_name = None
    st.session_state.created_user_ms = 0
    st.session_state.ended_session_ids = set()
    st.session_state.memory_mode = "persistent"
    st.session_state.memory_ttl_seconds = 0
    st.session_state.memory_ttl_label = "Forever"
    st.session_state.show_delete_confirmation = False
    st.session_state.deletion_complete = False
    st.session_state.deletion_result = None
    if "session_selector" in st.session_state:
        del st.session_state["session_selector"]


# ─────────────────────────────────────────────
# Memory retention policy (GDPR / data minimization)
# ─────────────────────────────────────────────

# Presets shown in the "Stay-only" picker.
MEMORY_TTL_PRESETS = {
    "1 day": 86400,
    "3 days": 86400 * 3,
    "1 week": 86400 * 7,
}


def _apply_memory_policy(session):
    """Wrap ``session.add_memory`` so it honours the user's retention policy.

    Behaviour by mode:
      * ``persistent``: pass-through (``memory_block_ttl=0`` means never expire).
      * ``stay``: inject ``memory_block_ttl=<configured seconds>``.
      * ``anonymous``: no-op; nothing is written to Couchbase Agent Memory.

    Idempotent: re-wrapping is harmless because we tag the wrapper.

    Args:
        session: Couchbase Agent Memory session to wrap (may be ``None``).

    Returns:
        The same session, with ``add_memory`` replaced by a wrapper that
        applies the active retention policy. Returns ``None`` if
        ``session`` is ``None``.
    """
    if session is None:
        return session
    if getattr(session, "_agentmem_policy_wrapped", False):
        return session

    mode = st.session_state.get("memory_mode", "persistent")
    ttl_seconds = int(st.session_state.get("memory_ttl_seconds", 0) or 0)

    original_add_memory = session.add_memory

    def _wrapped_add_memory(*args, **kwargs):
        if mode == "anonymous":
            # GDPR mode: silently drop the write. Nothing lands in Couchbase Agent Memory.
            return None
        if "memory_block_ttl" not in kwargs:
            if mode == "stay":
                kwargs["memory_block_ttl"] = ttl_seconds
            else:  # persistent
                kwargs["memory_block_ttl"] = 0
        return original_add_memory(*args, **kwargs)

    session.add_memory = _wrapped_add_memory
    session._agentmem_policy_wrapped = True
    return session


def memory_policy_label() -> str:
    """Short human-readable label for the active retention policy."""
    mode = st.session_state.get("memory_mode", "persistent")
    if mode == "anonymous":
        return "Anonymous - nothing saved"
    if mode == "stay":
        label = st.session_state.get("memory_ttl_label", "Stay duration")
        return f"Stay-only ({label})"
    return "Persistent (no expiry)"


# ─────────────────────────────────────────────
# Couchbase Agent Memory helpers
# ─────────────────────────────────────────────


def get_client():
    """Return an :class:`AgentMemoryClient` connected to the local server.

    Uses the ``AGENTMEM_BASE_URL`` environment variable (default
    ``http://localhost:8080``). Displays a Streamlit error and returns
    ``None`` if the connection fails.

    Returns:
        A connected :class:`AgentMemoryClient`, or ``None`` on failure.
    """
    base_url = os.getenv("AGENTMEM_BASE_URL", "http://localhost:8080")
    try:
        return AgentMemoryClient(base_url=base_url, timeout=30.0, verify=False)
    except Exception as e:
        st.error(f"Cannot connect to Couchbase Agent Memory: {e}")
        return None


def get_all_users() -> list[dict]:
    """Fetch all users from the Couchbase Agent Memory server.

    Returns:
        List of dicts with keys ``"user_id"`` (str) and ``"name"`` (str).
        Returns an empty list if the server is unreachable or returns no users.
    """
    client = get_client()
    if not client:
        return []

    users = []
    try:
        result = client.list_users()
        if hasattr(result, "users"):
            agentmem_users = result.users
        elif isinstance(result, dict) and "users" in result:
            agentmem_users = result["users"]
        elif isinstance(result, (list, tuple)):
            agentmem_users = result
        else:
            agentmem_users = []

        for user in agentmem_users:
            user_id = getattr(user, "id", getattr(user, "user_id", None)) or (
                user.get("id") if isinstance(user, dict) else str(user)
            )
            name = (
                getattr(user, "name", None)
                or (user.get("name") if isinstance(user, dict) else None)
                or user_id
            )

            users.append(
                {
                    "user_id": user_id,
                    "name": name,
                }
            )
    except Exception as exc:
        print(f"warning: could not list users — {exc}")

    return users


def _speaker_to_user_id(speaker: str) -> str:
    """Convert a display name to a snake_case user ID (e.g. ``"Alice Chen"`` → ``"alice_chen"``)."""
    return re.sub(r"\s+", "_", speaker.lower().strip())


def discover_persona_user(persona_key: str) -> dict | None:
    """Try to find the Couchbase Agent Memory user for a persona.

    Tries the defined ``user_id`` first, then ``persona_key``, persona
    display-name variants, and ``speaker_a`` style. Also handles
    dynamically created users that are not in ``PERSONAS``.

    Args:
        persona_key: Persona key from ``PERSONAS`` or a raw user ID.

    Returns:
        Dict ``{"user_id": str, "user": user_obj}`` if a match is
        found, else ``None``.
    """
    client = get_client()
    if not client:
        return None

    candidates = []

    # If it's a predefined persona, use that logic
    if persona_key in PERSONAS:
        persona = PERSONAS[persona_key]

        # Try the explicitly defined user_id first
        if "user_id" in persona:
            candidates.append(persona["user_id"])

        # Fall back to other variants
        candidates.extend(
            [
                persona_key,
                persona["display_name"].lower(),
                _speaker_to_user_id(persona["display_name"]),
                _speaker_to_user_id(persona["full_name"]),
            ]
        )
    else:
        # For dynamic users, just try the persona_key as user_id directly
        candidates.append(persona_key)

    for uid in candidates:
        try:
            user = client.get_user(user_id=uid)
            return {"user_id": uid, "user": user}
        except Exception:
            continue

    return None


def create_new_user(display_name: str) -> dict | None:
    """Create a new user in Couchbase Agent Memory.

    Derives the ``user_id`` from the display name via :func:`_speaker_to_user_id`
    (e.g. ``"John Doe"`` → ``"john_doe"``). Displays a Streamlit error if
    the server is unreachable or creation fails.

    Args:
        display_name: Human-readable name for the new user.

    Returns:
        Dict ``{"user_id": str, "user": user_obj, "name": str}``, or
        ``None`` on failure.
    """
    client = get_client()
    if not client:
        st.error("Cannot connect to Couchbase Agent Memory")
        return None

    try:
        user_id = _speaker_to_user_id(display_name)
        user = client.create_user(user_id=user_id, name=display_name)
        return {"user_id": user_id, "user": user, "name": display_name}
    except Exception as e:
        st.error(f"Failed to create user: {e}")
        return None


def delete_user(user: object) -> dict | None:
    """Delete a user and all associated sessions and memories from Couchbase Agent Memory.

    Args:
        user: Couchbase Agent Memory user object with a ``user_id`` attribute
            and a ``delete()`` method.

    Returns:
        Dict ``{"success": bool, "user_id": str, "elapsed_ms": float,
        "message": str}`` on success, or ``None`` if the client is
        unavailable or the user object is invalid.
    """
    client = get_client()
    if not client:
        st.error("Cannot connect to Couchbase Agent Memory")
        return None

    try:
        user_id = getattr(user, "user_id", None)
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


def _fetch_session_preview(session_obj):
    """Build a short summary preview for a session.

    Uses the first three user messages (chronologically) to produce a
    short snippet. Reads raw chat blocks via list_memories directly —
    no search call needed for a simple snippet.

    Designed to be safe to call from worker threads.

    Args:
        session_obj: Couchbase Agent Memory session to preview.

    Returns:
        A short snippet string (max ~120 chars), or ``"No messages yet"``
        if the session has no readable content.
    """
    try:
        # Fetch a small slice of raw blocks directly — no search roundtrip.
        resp = session_obj.list_memories(limit=10, offset=0, order_by="ingested_at")
        messages = []
        for block in resp.memory_blocks:
            msg = block.message
            if msg and msg.user_content:
                annotations = block.annotations or {}
                ts = annotations.get("timestamp") or block.ingested_at or ""
                messages.append((ts, msg.user_content))

        if not messages:
            return "No messages yet"

        # Sort chronologically (oldest first), take first 3
        messages.sort(key=lambda x: x[0] or "")
        first_three = [m[1] for m in messages[:3]]

        # Strip any leading "Speaker: " prefix for cleaner preview
        cleaned = []
        for content in first_three:
            if ": " in content:
                parts = content.split(": ", 1)
                if len(parts) == 2 and not parts[0].startswith("{"):
                    content = parts[1]
            content = content.strip().replace("\n", " ")
            cleaned.append(content[:35] + ("…" if len(content) > 35 else ""))

        summary = " | ".join(cleaned)
        return summary[:120] + ("…" if len(summary) > 120 else "")
    except Exception as exc:
        print(f"warning: session preview fetch failed — {exc}")
    return "No messages yet"


def _short_ts(ts: str) -> str:
    """Trim a Couchbase Agent Memory timestamp to the ``YYYY-MM-DD`` date portion for display."""
    if not ts:
        return ""
    for sep in ("T", " "):
        if sep in ts:
            return ts.split(sep, 1)[0]
    return ts[:10] if len(ts) > 10 else ts


def _record_summary(rec: dict) -> str:
    """One-line summary for the inner <details> header."""
    kind = rec.get("kind", "")
    ts = _short_ts(rec.get("timestamp", ""))
    if kind == "chat":
        snippet = (rec.get("text") or "").strip().replace("\n", " ")
        snippet = snippet[:90] + ("…" if len(snippet) > 90 else "")
        prefix = f"[chat · {ts}]" if ts else "[chat]"
        return f"{prefix} Summary: {snippet or '(empty)'}"
    if kind == "fact":
        snippet = (rec.get("text") or "").strip().replace("\n", " ")
        snippet = snippet[:120] + ("…" if len(snippet) > 120 else "")
        return f"[fact] {snippet or '(empty)'}"
    if kind == "summary":
        snippet = (rec.get("text") or "").strip().replace("\n", " ")
        snippet = snippet[:120] + ("…" if len(snippet) > 120 else "")
        return f"[summary] {snippet or '(empty)'}"
    if kind == "context":
        snippet = (rec.get("text") or "").strip().replace("\n", " ")
        snippet = snippet[:120] + ("…" if len(snippet) > 120 else "")
        return f"[context window] {snippet or '(empty)'}"
    return f"[{kind or 'unknown'}]"


def _render_memory_records(records: list[dict]) -> None:
    """Render the retrieved memories as a nested-dropdown expander.

    Outer = st.expander listing the count. Inner = HTML <details> per
    record, since Streamlit forbids nesting st.expander inside an
    st.expander.
    """
    if not records:
        return

    header = f"{len(records)} memories used in this reply"
    with st.expander(header, expanded=False):
        for rec in records:
            kind = rec.get("kind", "")
            ts = _short_ts(rec.get("timestamp", ""))
            block_id = rec.get("block_id", "") or ""
            query = rec.get("query", "") or ""
            summary_line = html.escape(_record_summary(rec))

            if kind == "chat":
                text = rec.get("text") or ""
                body_html = (
                    f"<strong>Summary:</strong> {html.escape(text)}"
                    if text
                    else "(empty)"
                )
            else:
                body_html = html.escape(rec.get("text") or "(empty)").replace(
                    "\n", "<br>"
                )

            meta_bits: list[str] = []
            if ts:
                meta_bits.append(f"timestamp: {html.escape(ts)}")
            if block_id:
                meta_bits.append(f"block: {html.escape(block_id)}")
            if query:
                meta_bits.append(f"matched query: {html.escape(query)}")
            meta_html = (
                f"<div style='margin-top:0.5rem;font-size:0.7rem;"
                f"color:rgba(26,26,26,0.55);'>{' · '.join(meta_bits)}</div>"
                if meta_bits
                else ""
            )

            st.markdown(
                f"""
<details style="margin-bottom: 0.4rem; padding: 0.5rem 0.75rem;
               background: rgba(255,255,255,0.5);
               border: 1px solid rgba(230,32,32,0.12);
               border-radius: 6px;">
  <summary style="cursor: pointer; font-size: 0.82rem;
                  color: rgba(26,26,26,0.85);">{summary_line}</summary>
  <div style="margin-top: 0.6rem; font-size: 0.85rem;
              line-height: 1.45; color: rgba(26,26,26,0.9);">
    {body_html}
    {meta_html}
  </div>
</details>
""",
                unsafe_allow_html=True,
            )


def _session_sort_key(sess_info):
    """Sort key: numeric session number ascending; non-numeric IDs go last."""
    sid = sess_info.get("session_id", "")
    if isinstance(sid, str) and sid.startswith("session_"):
        try:
            return (0, int(sid.split("_", 1)[1]))
        except (ValueError, IndexError):
            pass
    return (1, sid)


def get_all_sessions(user):
    """Fetch all sessions for a user with parallel preview text fetching.

    Session previews are fetched in parallel using a :class:`ThreadPoolExecutor`
    and cached in ``st.session_state`` so repeated Streamlit reruns do not
    re-fetch previews that are already available.

    Args:
        user: Couchbase Agent Memory user object with ``list_sessions()``
            and ``get_session()`` methods.

    Returns:
        List of dicts with keys ``"session_id"`` (str), ``"session"``
        (session object), and ``"preview"`` (str). Sorted ascending by
        session number.
    """
    sessions_list = []
    try:
        result = user.list_sessions()
        if hasattr(result, "sessions"):
            raw = result.sessions
        elif isinstance(result, dict) and "sessions" in result:
            raw = result["sessions"]
        elif isinstance(result, (list, tuple)):
            raw = result
        else:
            return []

        # First pass: collect all session objects
        session_objects = []
        for s in raw:
            if isinstance(s, str):
                sid = s
            elif isinstance(s, tuple):
                sid = s[0] if s else None
            elif hasattr(s, "session_id"):
                sid = s.session_id
            elif isinstance(s, dict) and "id" in s:
                sid = s["id"]
            else:
                sid = str(s)
            if sid:
                try:
                    session_obj = user.get_session(session_id=sid)
                    session_objects.append((sid, session_obj))
                except Exception as exc:
                    print(f"warning: could not get session '{sid}' — {exc}")
                    continue

        # Second pass: fetch previews in parallel, using a session-state
        # cache so re-renders don't re-fetch previews already retrieved.
        if session_objects:
            _cache = st.session_state.setdefault("_session_preview_cache", {})

            # Only submit work for sessions whose preview isn't cached yet.
            uncached = [
                (sid, sess_obj)
                for sid, sess_obj in session_objects
                if sid not in _cache
            ]

            if uncached:
                # 5 workers: balanced to avoid overwhelming the backend.
                with ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_sid = {
                        executor.submit(_fetch_session_preview, sess_obj): (
                            sid,
                            sess_obj,
                        )
                        for sid, sess_obj in uncached
                    }
                    for future in as_completed(future_to_sid):
                        sid, sess_obj = future_to_sid[future]
                        try:
                            # 5-second hard timeout per preview fetch.
                            preview_text = future.result(timeout=5)
                        except Exception:
                            preview_text = "No messages yet"
                        _cache[sid] = preview_text

            # Build the final list from the cache (all sessions, cached or fresh).
            for sid, sess_obj in session_objects:
                sessions_list.append(
                    {
                        "session_id": sid,
                        "session": sess_obj,
                        "preview": _cache.get(sid, "No messages yet"),
                    }
                )

    except Exception as exc:
        print(f"warning: could not list sessions — {exc}")

    # Order by session number ascending (Session 1, 2, 3, ...)
    sessions_list.sort(key=_session_sort_key)
    return sessions_list


def create_new_session(user) -> dict | None:
    """Create a new incrementally numbered session for the user.

    Inspects all existing sessions to find the highest ``session_N``
    number and creates ``session_N+1``. The new session has the active
    memory-retention policy applied via :func:`_apply_memory_policy`.

    Args:
        user: Couchbase Agent Memory user object with ``list_sessions()``
            and ``create_session()`` methods.

    Returns:
        Dict ``{"session_id": str, "session": session_obj}`` on success,
        or ``None`` on failure.
    """
    try:
        # Get all existing sessions to find the highest number
        all_sessions = get_all_sessions(user)
        max_num = 0
        for sess_info in all_sessions:
            sid = sess_info["session_id"]
            # Extract number from session_X format
            if sid.startswith("session_"):
                try:
                    num = int(sid.split("_")[1])
                    max_num = max(max_num, num)
                except (ValueError, IndexError):
                    pass

        # Create next session ID
        next_num = max_num + 1
        session_id = f"session_{next_num}"

        # Most session management APIs support create_session with session_id
        if hasattr(user, "create_session"):
            new_session = user.create_session(session_id=session_id)
        else:
            # Fallback: some implementations might use a different method
            st.warning(
                "Session creation not available in this Couchbase Agent Memory version."
            )
            return None

        if new_session:
            retrieved_id = getattr(new_session, "session_id", session_id)
            return {
                "session_id": retrieved_id,
                "session": _apply_memory_policy(new_session),
            }
    except Exception as e:
        st.error(f"Failed to create new session: {e}")
    return None


def load_session_history(session_obj, max_messages: int | None = None) -> list[dict]:
    """Load chat message pairs from Couchbase Agent Memory session memory.

    Each pair is one user message followed by one assistant message.
    Pass ``max_messages`` to limit to the last N pairs — the fetch is
    size-bounded so it never pages through a full long session just to
    show a handful of messages.

    Uses ``list_memories()`` directly (scoped to this session only) to
    retrieve raw chat blocks, keeping this path separate from the
    ``search_memories`` path that passes facts/summaries/contexts to agents.

    Args:
        session_obj: Couchbase Agent Memory session to read from.
        max_messages: Optional cap on the number of trailing pairs to
            return. ``None`` means no limit (full pagination).

    Returns:
        List of chat-message dicts with role, content, and timestamp.
    """
    chat_history = []
    try:
        all_blocks = []
        offset = 0
        page_size = 200  # max blocks per list_memories page; capped below when max_messages is set

        # When max_messages is set, fetch only enough raw blocks to satisfy
        # the cap. Multiply by 3 to account for non-chat blocks mixed in
        # (summaries, facts, and context blocks outnumber raw chat blocks).
        # This avoids paginating a 1000-block session to display 15 messages.
        if max_messages is not None and max_messages > 0:
            page_size = min(
                200, max_messages * 3
            )  # * 3: typical ratio of non-chat to chat blocks

        while True:
            resp = session_obj.list_memories(
                limit=page_size, offset=offset, order_by="ingested_at"
            )
            all_blocks.extend(resp.memory_blocks)
            if len(resp.memory_blocks) < page_size or len(all_blocks) >= resp.total:
                break
            # If we're capped, stop as soon as we have enough to slice from.
            if max_messages is not None and len(all_blocks) >= max_messages * 3:
                break
            offset += page_size

        if not all_blocks:
            return []

        # Extract only blocks that have a chat message.
        all_messages = []
        for block in all_blocks:
            msg = block.message
            if msg is None:
                continue
            user_content = msg.user_content or ""
            assistant_content = msg.assistant_content or ""
            if not user_content and not assistant_content:
                continue
            annotations = block.annotations or {}
            timestamp = annotations.get("timestamp") or block.ingested_at or ""
            all_messages.append(
                {
                    "timestamp": timestamp,
                    "user_content": user_content,
                    "assistant_content": assistant_content,
                }
            )

        # Sort chronologically (oldest first) so the chat reads top-to-bottom
        all_messages.sort(key=lambda m: m.get("timestamp") or "")

        # Optionally limit to the last N pairs; otherwise return everything
        if max_messages is not None and max_messages > 0:
            recent = all_messages[-max_messages:]
        else:
            recent = all_messages

        # Convert to chat message format
        for msg_data in recent:
            # Guest message
            if msg_data["user_content"]:
                chat_history.append(
                    {
                        "role": "user",
                        "content": msg_data["user_content"],
                        "timestamp": msg_data["timestamp"],
                    }
                )

            # Concierge message
            if msg_data["assistant_content"]:
                chat_history.append(
                    {
                        "role": "assistant",
                        "content": msg_data["assistant_content"],
                        "timestamp": msg_data["timestamp"],
                        "status_log": [],
                        "memory_update": None,
                    }
                )
    except Exception as e:
        print(f"Error loading session history: {e}")

    return chat_history


def switch_to_session(
    session_id: str, session_obj, readonly: bool | None = None
) -> bool:
    """Switch the active session.

    Read-only resolution:
      * If ``readonly`` is explicitly passed (True/False), it is used
        as-is. This is what "New Chat" relies on (always writable).
      * If ``readonly`` is ``None`` (typical dropdown switch), the
        session is treated as writable UNLESS the user has previously
        ended it in this app session, in which case it opens read-only.

    Sessions are NOT auto-ended when switching away. A session is only
    marked as done when the user explicitly clicks "End Session", so a
    new session created and then navigated away from remains chattable
    when the user comes back to it via the dropdown.

    Args:
        session_id: Identifier of the session being switched to.
        session_obj: Couchbase Agent Memory session object.
        readonly: Force read-only state, or ``None`` to auto-resolve.

    Returns:
        ``True`` if the switch succeeded, ``False`` otherwise.
    """
    try:
        if readonly is None:
            ended = st.session_state.get("ended_session_ids", set())
            readonly = session_id in ended

        st.session_state.current_session_id = session_id
        st.session_state.agentmem_session = _apply_memory_policy(session_obj)
        # Load the most recent messages from the previous session. Showing
        # the last 20 pairs is enough context for the UI; older turns are
        # still retrievable by the agent via cross-session memory search.
        st.session_state.chat_messages = load_session_history(
            session_obj, max_messages=20
        )
        st.session_state.is_session_readonly = bool(readonly)
        return True
    except Exception as e:
        st.error(f"Failed to switch session: {e}")
        return False


def get_dynamic_profile_overview(
    user, persona_key: str, status_placeholder=None
) -> dict:
    """Render the profile card by invoking ProfileOverviewGraph.

    The retrieval + synthesis pipeline lives in the agent. This function
    only wires session selection and renders the status pipeline.

    Args:
        user: Couchbase Agent Memory user object whose sessions are searched.
        persona_key: Persona key (used for status messages).
        status_placeholder: Optional Streamlit placeholder for live
            progress updates.

    Returns:
        Dict ``{"visits": int, "preferences": str, "dislikes": str,
        "complaints": str}``. May also include ``"empty": True`` when no
        memory is found.
    """

    def update_status(lines_done: list, active_line: str | None = None):
        if status_placeholder is None:
            return
        html = '<div class="status-pipeline">'
        for line in lines_done:
            html += f"""
            <div class="status-line done">
                <div class="status-dot done"></div>
                {line}
            </div>"""
        if active_line:
            html += f"""
            <div class="status-line active">
                <div class="status-dot active"></div>
                {active_line}
            </div>"""
        html += "</div>"
        status_placeholder.markdown(html, unsafe_allow_html=True)

    empty_profile = {
        "visits": 0,
        "preferences": "No memories for user yet",
        "dislikes": "No memories for user yet",
        "complaints": "No memories for user yet",
        "empty": True,
    }

    try:
        # Count visits via the session list; the agent doesn't read
        # session metadata so we still resolve it here for display.
        update_status([], "Fetching sessions…")
        sessions_start = time.time()
        all_sessions = get_all_sessions(user)
        sessions_ms = (time.time() - sessions_start) * 1000

        if not all_sessions:
            return empty_profile

        update_status(
            [f"Sessions fetched · {len(all_sessions)} sessions · {sessions_ms:.0f}ms"],
            "Running ProfileOverviewAgent…",
        )

        agent_start = time.time()
        # Pass the most recent session so the agent skips its own list_sessions()
        # + get_session() calls — it still searches cross-session via session_ids="all".
        _preloaded_session = all_sessions[-1]["session"] if all_sessions else None
        result = ProfileOverviewGraph().run(
            agentmem_user=user,
            guest_id=getattr(user, "id", "") or persona_key,
            guest_name=getattr(user, "name", "") or persona_key,
            agentmem_session=_preloaded_session,
        )
        agent_ms = (time.time() - agent_start) * 1000

        profile = result.get("profile") or empty_profile
        if profile.get("empty"):
            return profile

        # Backfill visits from the actual session count rather than the
        # LLM's guess - the LLM only sees retrieved excerpts, not the
        # full session list.
        profile["visits"] = len(all_sessions)

        retrieval_ms = result.get("retrieval_ms", 0.0) or 0.0
        synthesis_ms = result.get("synthesis_ms", 0.0) or 0.0
        update_status(
            [
                f"Sessions fetched · {len(all_sessions)} sessions · {sessions_ms:.0f}ms",
                f"Memory retrieval · {retrieval_ms:.0f}ms",
                f"Profile extracted · {synthesis_ms:.0f}ms",
                f"Total time · {(sessions_ms + agent_ms):.0f}ms",
            ]
        )

        return profile

    except Exception as e:
        print(f"Error generating profile overview: {e}")
        return empty_profile


def load_persona(persona_key: str) -> bool:
    """Load the Couchbase Agent Memory user and all sessions for a persona into session state.

    Existing sessions at login time are automatically marked as ended so
    they open read-only. The most recent session is selected and loaded
    in read-only mode as the initial view.

    Args:
        persona_key: Persona key from ``PERSONAS`` or a dynamic user ID.

    Returns:
        ``True`` if the user was found and state was updated; ``False``
        if the user could not be discovered (triggers a Streamlit error).
    """
    result = discover_persona_user(persona_key)
    if not result:
        st.error(
            f"Could not find user '{persona_key}' in Couchbase Agent Memory. Check user_id seeding."
        )
        return False

    user = result["user"]

    # Fetch all sessions for this persona
    all_sessions = get_all_sessions(user)

    # Store user and all sessions (even if empty for new users)
    st.session_state.all_sessions_for_persona = all_sessions
    st.session_state.agentmem_user = user
    st.session_state.active_persona = persona_key

    # Treat every session that already exists in the backend at login
    # time as an ended/historical session. Only sessions created in this
    # app run via "New Chat" are writable. The seed/loaded sessions in
    # the demo data don't actually carry an end_time on the backend, so
    # we synthesise the "ended" state client-side here.
    preloaded_ids = {sess["session_id"] for sess in all_sessions}
    st.session_state.ended_session_ids = set(preloaded_ids)

    # Sessions are sorted ascending by session number. Initial load picks
    # the LATEST session purely so the user has something visible to read.
    # It opens READ-ONLY because it is one of the preloaded sessions.
    if all_sessions:
        latest_session = all_sessions[-1]
        st.session_state.current_session_id = latest_session["session_id"]
        st.session_state.agentmem_session = _apply_memory_policy(
            latest_session["session"]
        )
        st.session_state.is_session_readonly = True
        st.session_state.chat_messages = load_session_history(
            latest_session["session"], max_messages=20
        )
    else:
        # New user with no sessions - will be created on first chat
        st.session_state.current_session_id = None
        st.session_state.agentmem_session = None
        st.session_state.is_session_readonly = False
        st.session_state.chat_messages = []

    return True


# ─────────────────────────────────────────────
# Hotel header
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
        <div class="hotel-tagline">Personal Concierge · Available 24 hours</div>
    </div>
    <div style="width: 175px; flex-shrink:0;"></div>
</div>
""",
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────
# DELETION SUCCESS SCREEN
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
                        font-family: 'Inter', sans-serif;">User Deleted</div>
            <div style="text-align: center; color: rgba(200,230,210,0.8); margin-bottom: 0.5em; font-size: 0.95em;
                        line-height: 1.6;">
                Your account and all associated data have been permanently removed.
            </div>
            <div style="text-align: center; color: rgba(76,175,130,0.7); margin-bottom: 2em; font-size: 0.85em;
                        font-family: 'Inter', monospace;">
                {result.get("message", "Deleted successfully")}
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

        # Add return to sign in button
        st.markdown('<div style="height:1.2rem"></div>', unsafe_allow_html=True)
        if st.button("Return to Sign In", use_container_width=True, type="primary"):
            st.session_state.deletion_complete = False
            st.session_state.deletion_result = None
            st.rerun()

    # Reset deletion state after display (if button not clicked)
    st.session_state.deletion_complete = False
    st.session_state.deletion_result = None
    st.stop()


# ─────────────────────────────────────────────
# LOGIN SCREEN
# ─────────────────────────────────────────────

if not st.session_state.authenticated:
    # Add login mode to session state
    if "login_mode" not in st.session_state:
        st.session_state.login_mode = "signin"  # "signin" or "newuser"

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown(
            """
        <div style="max-width: 420px; margin: 80px auto; padding: 2.5em; background: rgba(255,255,255,0.7);
                    border: 1px solid rgba(230,32,32,0.15); border-radius: 12px;">
            <div style="text-align: center; font-size: 2em; font-weight: 700; color: #1A1A1A; margin-bottom: 0.5em;
                        font-family: 'Inter', sans-serif;">Couchbase Agent Memory Hotel</div>
            <div style="text-align: center; color: rgba(230,32,32,0.5); margin-bottom: 1.5em; font-size: 0.9em;
                        letter-spacing: 0.1em;">Concierge Portal</div>
        """,
            unsafe_allow_html=True,
        )

        # Mode toggle buttons (hidden on the "user_created" confirmation page)
        if st.session_state.login_mode != "user_created":
            mode_col1, mode_col2 = st.columns(2)
            with mode_col1:
                if st.button("Sign In", use_container_width=True, key="mode_signin"):
                    st.session_state.login_mode = "signin"
                    st.rerun()
            with mode_col2:
                if st.button("New User", use_container_width=True, key="mode_newuser"):
                    st.session_state.login_mode = "newuser"
                    st.rerun()

        st.markdown('<div style="height:0.8rem"></div>', unsafe_allow_html=True)

        # SIGN IN MODE
        if st.session_state.login_mode == "signin":
            # Load all users dynamically
            all_users = get_all_users()
            if all_users:
                user_options = {user["user_id"]: user["name"] for user in all_users}
                selected_user_id = st.selectbox(
                    "Select Profile:",
                    options=list(user_options.keys()),
                    format_func=lambda x: user_options[x],
                )
                password = st.text_input(
                    "Password:", type="password", placeholder="Enter password"
                )

                # ── Memory retention policy (GDPR / data minimization) ──
                st.markdown(
                    '<div class="panel-section-title" style="margin-top:0.6rem;">'
                    "Memory retention</div>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    "How should Couchbase Agent Memory treat memories from this stay? "
                    "You can pick the policy that matches your data preferences."
                )
                memory_mode_choice = st.radio(
                    "Memory retention policy",
                    options=["persistent", "stay"],
                    format_func=lambda m: {
                        "persistent": "Persistent — remember me across stays",
                        "stay": "Stay-only — forget after my stay",
                    }[m],
                    index=0,
                    label_visibility="collapsed",
                    key="memory_mode_choice_radio",
                )
                ttl_label = "Forever"
                ttl_seconds = 0
                if memory_mode_choice == "stay":
                    ttl_label = st.selectbox(
                        "Stay duration (memories expire after this):",
                        options=list(MEMORY_TTL_PRESETS.keys()),
                        index=1,  # default to "3 days"
                        key="memory_ttl_choice",
                    )
                    ttl_seconds = MEMORY_TTL_PRESETS[ttl_label]

                if st.button(
                    "Sign In",
                    use_container_width=True,
                    type="primary",
                    key="btn_signin",
                ):
                    if authenticate(selected_user_id, password):
                        # Persist the chosen retention policy for this app session.
                        st.session_state.memory_mode = memory_mode_choice
                        st.session_state.memory_ttl_seconds = ttl_seconds
                        st.session_state.memory_ttl_label = ttl_label
                        user_name = user_options[selected_user_id]
                        st.success(f"Welcome, {user_name}!")
                        st.rerun()
                    else:
                        st.error("Invalid password")
                        if st.session_state.login_attempts >= 3:
                            st.warning("Too many attempts")
            else:
                st.warning("No users available. Please create a new account.")

        # NEW USER MODE
        elif st.session_state.login_mode == "newuser":
            new_user_name = st.text_input("Full Name:", placeholder="e.g., John Doe")

            if st.button(
                "Create Account",
                use_container_width=True,
                type="primary",
                key="btn_create",
            ):
                if not new_user_name.strip():
                    st.error("Please enter a name")
                else:
                    with st.spinner("Creating account…"):
                        create_start = time.time()
                        result = create_new_user(new_user_name.strip())
                        create_ms = (time.time() - create_start) * 1000
                        if result:
                            # Stash details for the confirmation page and switch
                            # to the "user_created" mode so the user can review
                            # how long it took before going back to sign in.
                            st.session_state.created_user_name = result["name"]
                            st.session_state.created_user_ms = create_ms
                            st.session_state.login_mode = "user_created"
                            st.rerun()

        # USER CREATED CONFIRMATION PAGE
        elif st.session_state.login_mode == "user_created":
            _name = st.session_state.created_user_name or "your account"
            _ms = st.session_state.created_user_ms or 0
            st.success(f"Account created for {_name}")
            st.info(f"New user made in {_ms:.0f}ms")
            st.info("Password: 123 (default)")
            st.markdown('<div style="height:0.4rem"></div>', unsafe_allow_html=True)
            if st.button(
                "Go back to Sign In",
                use_container_width=True,
                type="primary",
                key="btn_back_to_signin",
            ):
                st.session_state.login_mode = "signin"
                st.session_state.created_user_name = None
                st.session_state.created_user_ms = 0
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


# ─────────────────────────────────────────────
# Main layout: left sidebar (narrow) + main chat area (wide)
# ─────────────────────────────────────────────

sidebar_col, main_col = st.columns([0.7, 2.3], gap="medium")


# ══════════════════════════════════════════════
# LEFT SIDEBAR — Chat History & Session Controls
# ══════════════════════════════════════════════

with sidebar_col:
    # ── User profile section ──────────────────────
    pkey = st.session_state.active_persona

    st.markdown(
        '<div class="panel-section-title" style="margin-top:0;">User Profile</div>',
        unsafe_allow_html=True,
    )

    # Check if it's a predefined persona or a new user
    if pkey in PERSONAS:
        pdata = PERSONAS[pkey]
        display_name = pdata["display_name"]
        desc = pdata.get("desc", "")

        st.markdown(
            f"""
        <div class="persona-card active">
            <span class="persona-name">{display_name}</span>
            <div class="persona-desc">{desc}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )
    else:
        # New user - get name from agentmem_user
        user = st.session_state.agentmem_user
        user_name = getattr(user, "name", pkey) if user else pkey

        st.markdown(
            f"""
        <div class="persona-card active">
            <span class="persona-name">{user_name}</span>
            <div class="persona-desc">Welcome to Couchbase Agent Memory Hotel</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    # Get display name for loading spinner
    if pkey in PERSONAS:
        display_name = PERSONAS[pkey]["display_name"]
    else:
        user = st.session_state.agentmem_user
        display_name = getattr(user, "name", pkey) if user else pkey

    # Load persona's sessions on first load
    if not st.session_state.agentmem_user:
        with st.spinner(f"Loading {display_name}'s profile…"):
            success = load_persona(pkey)
        if success:
            st.rerun()

    # Check if persona changed and clear cached profile if so
    if st.session_state.profile_persona != pkey:
        st.session_state.profile_overview = None
        st.session_state.profile_loading = False
        st.session_state.profile_persona = pkey

    # Load dynamic profile on first load (or after "Update Profile" click).
    # try/finally ensures profile_loading is always cleared even on exception,
    # so the UI can never get permanently stuck in the loading state.
    if (
        st.session_state.agentmem_user
        and st.session_state.profile_overview is None
        and not st.session_state.profile_loading
    ):
        st.session_state.profile_loading = True
        status_placeholder = st.empty()
        try:
            profile = get_dynamic_profile_overview(
                st.session_state.agentmem_user, pkey, status_placeholder
            )
            st.session_state.profile_overview = profile
            st.session_state.profile_persona = pkey
        finally:
            st.session_state.profile_loading = False
        st.rerun()

    # Display dynamic profile overview
    if st.session_state.profile_overview:
        profile = st.session_state.profile_overview
        if profile.get("empty"):
            st.markdown(
                """
            <div style="background: rgba(255,255,255,0.6); border: 1px solid rgba(230,32,32,0.12); border-radius: 8px; padding: 1rem; margin: 0.5rem 0; font-size: 0.85rem; line-height: 1.6;">
                <div style="color: rgba(230,32,32,0.8); font-weight: 600; margin-bottom: 0.5rem;">Profile Overview</div>
                <div style="color: rgba(26,26,26,0.55); font-style: italic;">No memories for user yet — start a chat to build your profile.</div>
            </div>
            """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
            <div style="background: rgba(255,255,255,0.6); border: 1px solid rgba(230,32,32,0.12); border-radius: 8px; padding: 1rem; margin: 0.5rem 0; font-size: 0.85rem; line-height: 1.6;">
                <div style="color: rgba(230,32,32,0.8); font-weight: 600; margin-bottom: 0.5rem;">Profile Overview</div>
                <div style="color: rgba(26,26,26,0.85); margin-bottom: 0.3rem;"><strong>Likes:</strong> {profile.get("preferences", "None mentioned")}</div>
                <div style="color: rgba(26,26,26,0.85); margin-bottom: 0.3rem;"><strong>Dislikes:</strong> {profile.get("dislikes", "None mentioned")}</div>
                <div style="color: rgba(26,26,26,0.85);"><strong>Previous Complaints:</strong> {profile.get("complaints", "None mentioned")}</div>
            </div>
            """,
                unsafe_allow_html=True,
            )

        if st.button(
            "Update Profile", use_container_width=True, key="update_profile_btn"
        ):
            st.session_state.profile_overview = None
            st.session_state.profile_loading = False
            st.rerun()

    if st.button("Sign Out", use_container_width=True):
        logout()
        st.rerun()

    # ── Delete user section ──────────────────────
    if st.button("Delete User", use_container_width=True, key="delete_user_button"):
        st.session_state.show_delete_confirmation = True

    # Delete confirmation dialog
    if st.session_state.get("show_delete_confirmation", False):
        st.markdown('<div style="height:0.4rem"></div>', unsafe_allow_html=True)
        st.markdown(
            '<div style="background: rgba(220,80,60,0.08); border: 1px solid rgba(220,80,60,0.3); border-radius: 8px; padding: 0.9rem; margin: 0.5rem 0;">'
            '<div style="color: rgba(255,160,140,0.9); font-weight: 600; margin-bottom: 0.5rem;">⚠️ Delete User Confirmation</div>'
            '<div style="color: rgba(26,26,26,0.7); font-size: 0.85rem; margin-bottom: 0.8rem;">'
            "This will permanently delete your account and all associated data. Please enter your password to confirm."
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )

        # Password input
        delete_password = st.text_input(
            "Enter password to confirm deletion:",
            type="password",
            key="delete_password_input",
        )

        col_confirm, col_cancel = st.columns([1, 1])
        with col_confirm:
            if st.button("Confirm Delete", use_container_width=True):
                # Get the persona and password
                pkey = st.session_state.active_persona
                correct_password = None

                if pkey in PERSONAS:
                    correct_password = PERSONAS[pkey].get("password")
                else:
                    # New users default to "123"
                    correct_password = "123"

                if delete_password and delete_password == correct_password:
                    # Perform deletion
                    with st.spinner("Deleting user and all data…"):
                        user = st.session_state.agentmem_user
                        result = delete_user(user)

                    if result and result.get("success"):
                        st.session_state.show_delete_confirmation = False
                        st.session_state.deletion_complete = True
                        st.session_state.deletion_result = result
                        logout()
                        st.rerun()
                    else:
                        st.error("Failed to delete user")
                        st.session_state.show_delete_confirmation = False
                else:
                    st.error("Incorrect password")

        with col_cancel:
            if st.button("Cancel", use_container_width=True):
                st.session_state.show_delete_confirmation = False
                st.rerun()

    # ── Chat history section ──────────────────────
    st.markdown('<div style="height:0.8rem"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="panel-section-title">Sessions</div>', unsafe_allow_html=True
    )

    # "New Chat" button
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("New Chat", use_container_width=True):
            user = st.session_state.agentmem_user
            with st.spinner("Creating new session…"):
                new_session = create_new_session(user)
                if new_session:
                    # Refresh the sessions list so all previous sessions
                    # remain visible alongside the newly created one
                    new_sessions = get_all_sessions(user)
                    st.session_state.all_sessions_for_persona = new_sessions
                    # Switch to the new session as an ACTIVE (writable) session
                    switch_to_session(
                        new_session["session_id"],
                        new_session["session"],
                        readonly=False,
                    )
                    st.rerun()

    with col2:
        if st.button("End Session", use_container_width=True):
            # Record the id BEFORE we clear it so we can later open this
            # session as read-only if the user navigates back to it.
            ended_id = st.session_state.current_session_id

            # End current session in Couchbase Agent Memory
            try:
                current_session = st.session_state.agentmem_session
                if hasattr(current_session, "end"):
                    current_session.end()
            except Exception as exc:
                print(f"warning: session end call failed — {exc}")

            if ended_id:
                ended_set = st.session_state.get("ended_session_ids") or set()
                ended_set.add(ended_id)
                st.session_state.ended_session_ids = ended_set

            # Refresh sessions list from backend
            user = st.session_state.agentmem_user
            new_sessions = get_all_sessions(user)
            st.session_state.all_sessions_for_persona = new_sessions

            # Clear current session
            st.session_state.pending_prompt = None
            st.session_state.chat_messages = []
            st.session_state.current_session_id = None
            st.session_state.agentmem_session = None
            st.session_state.is_session_readonly = False
            # Drop the dropdown's stored label so the top-of-dropdown
            # sync picks up the (now changed) current session on rerun.
            if "session_selector" in st.session_state:
                del st.session_state["session_selector"]

            st.info(
                "Session ended. Click 'New Chat' to start a new conversation, or pick a previous session to review."
            )
            st.rerun()

    st.markdown('<div style="height:0.6rem"></div>', unsafe_allow_html=True)

    # Dropdown selector for sessions
    current_session_id = st.session_state.current_session_id
    sessions_list = st.session_state.all_sessions_for_persona

    if sessions_list:
        # Build session options with cached previews
        session_options = []
        session_ids = []

        for sess_info in sessions_list:
            sid = sess_info["session_id"]
            preview_text = sess_info.get("preview", "No messages yet")

            # Extract the session number from session_X format
            session_num = sid.split("_")[-1] if "_" in sid else sid
            display_label = f"Session {session_num} - {preview_text}"
            session_options.append(display_label)
            session_ids.append(sid)

        # Find current index
        try:
            current_idx = session_ids.index(current_session_id)
        except ValueError:
            current_idx = 0

        expected_label = session_options[current_idx]

        # Synchronise the widget state to whatever the application thinks the
        # current session is. This MUST happen before the selectbox renders so
        # Streamlit picks up the updated value as the widget's current value.
        # Without this, the persisted widget state can lag behind programmatic
        # session changes (e.g. after "New Chat" or "End Session"), and the
        # diff check below would re-fire switch_to_session every rerun and
        # wedge the UI into read-only mode.
        if st.session_state.get("session_selector") != expected_label:
            st.session_state["session_selector"] = expected_label

        def _on_session_change():
            new_label = st.session_state.get("session_selector")
            if new_label not in session_options:
                return
            new_idx = session_options.index(new_label)
            new_sid = session_ids[new_idx]
            if new_sid == st.session_state.get("current_session_id"):
                return
            new_sess = sessions_list[new_idx]["session"]
            # readonly=None → switch_to_session will mark the session as
            # read-only ONLY if it was previously ended via the End
            # Session button. Sessions you simply navigated away from
            # remain chattable when you come back to them.
            switch_to_session(new_sid, new_sess, readonly=None)

        # Dropdown selector — on_change fires ONLY when the user actually
        # picks a different option, so programmatic state changes never
        # accidentally trigger a session switch.
        st.selectbox(
            "Switch session:",
            options=session_options,
            key="session_selector",
            on_change=_on_session_change,
        )


# ══════════════════════════════════════════════
# MAIN CHAT AREA
# ══════════════════════════════════════════════

with main_col:
    if not st.session_state.active_persona:
        st.markdown(
            """
        <div style="display:flex; flex-direction:column; align-items:center;
                    justify-content:center; height:60vh; text-align:center;">
            <div style="font-family:'Inter',sans-serif; font-size:2.5rem;
                        font-weight:700; color:rgba(230,32,32,0.2); letter-spacing:0.08em;">
                Couchbase Agent Memory Hotel
            </div>
            <div style="font-size:0.8rem; color:rgba(26,26,26,0.3);
                        letter-spacing:0.15em; text-transform:uppercase; margin-top:1rem;">
                Select a guest from the left sidebar to begin
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    else:
        pkey = st.session_state.active_persona

        # Get display data - handle both personas and new users
        if pkey in PERSONAS:
            pdata = PERSONAS[pkey]
            initials = pdata.get("initials", pdata["display_name"][0].upper())
            full_name = pdata.get("full_name", pdata["display_name"])
        else:
            # New user
            user = st.session_state.agentmem_user
            user_name = getattr(user, "name", pkey) if user else pkey
            full_name = user_name
            initials = (
                "".join([word[0].upper() for word in user_name.split()])[:2] or "?"
            )

        session = st.session_state.agentmem_session

        # ── Guest header in main area ────────────────
        session_id = getattr(session, "session_id", "–") if session else "–"
        st.markdown(
            f"""
        <div style="padding: 0.8rem 1.2rem; background:rgba(255,248,238,0.8);
                    border: 1px solid rgba(230,32,32,0.12); border-radius:8px; margin-bottom:1rem;">
            <div style="display:flex; align-items:center; gap:1rem;">
                <div class="guest-avatar" style="width:40px; height:40px; font-size:1rem;">{initials}</div>
                <div>
                    <span style="font-family:'Inter',sans-serif; font-size:1.1rem;
                                 font-weight:600; color:#1A1A1A;">{full_name}</span>
                    <div style="font-size:0.75rem; color:rgba(26,26,26,0.5);">Session: {session_id}</div>
                </div>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

        # ── Memory retention policy badge ────────────
        _policy_mode = st.session_state.get("memory_mode", "persistent")
        _policy_label = memory_policy_label()
        _policy_color = {
            "persistent": "rgba(120, 180, 120, 0.85)",
            "stay": "rgba(230, 32, 32, 0.9)",
        }.get(_policy_mode, "rgba(230,32,32,0.9)")
        _policy_bg = {
            "persistent": "rgba(120,180,120,0.08)",
            "stay": "rgba(230,32,32,0.06)",
        }.get(_policy_mode, "rgba(230,32,32,0.06)")
        st.markdown(
            f"""
            <div style="padding:0.5rem 0.9rem; background:{_policy_bg};
                        border:1px solid {_policy_color}; border-radius:6px;
                        margin-bottom:0.8rem; font-size:0.78rem;
                        color:{_policy_color}; letter-spacing:0.05em;
                        display:flex; align-items:center; gap:0.5rem;">
                <span style="font-weight:600; text-transform:uppercase;
                             font-size:0.7rem; letter-spacing:0.12em;">Memory:</span>
                <span>{_policy_label}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.session_state.get("is_session_readonly"):
            st.markdown(
                """
            <div style="padding:0.6rem 1rem; background:rgba(255,248,238,0.8);
                        border:1px solid rgba(230,32,32,0.15); border-radius:6px;
                        margin-bottom:0.8rem; font-size:0.78rem;
                        color:rgba(26,26,26,0.7); letter-spacing:0.05em;">
                Viewing a previous session (read-only). Click <strong>New Chat</strong> to start a new conversation.
            </div>
            """,
                unsafe_allow_html=True,
            )

        # ── Render chat history ────────────────
        for msg in st.session_state.chat_messages:
            if msg["role"] == "user":
                timestamp_str = (
                    f"<div style='font-size: 0.65rem; color: rgba(230,32,32,0.45); margin-top: 0.3rem;'>{msg.get('timestamp', '')}</div>"
                    if msg.get("timestamp")
                    else ""
                )
                # Strip speaker name prefix if present (e.g., "Alice Chen: text" -> "text")
                content = msg["content"]
                if ": " in content:
                    parts = content.split(": ", 1)
                    if len(parts) == 2 and not parts[0].startswith("{"):
                        content = parts[1]
                st.markdown(
                    f"""
                <div class="msg-guest">
                    <div class="bubble">{content}{timestamp_str}</div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

            elif msg["role"] == "assistant":
                # Status log (collapsed after response is done)
                if msg.get("status_log") and msg.get("status_log"):
                    log = msg["status_log"]
                    with st.expander("View pipeline", expanded=False):
                        lines_html = '<div class="status-pipeline">'
                        for line in log:
                            lines_html += f"""
                            <div class="status-line done">
                                <div class="status-dot done"></div>
                                {line}
                            </div>"""
                        lines_html += "</div>"
                        st.markdown(lines_html, unsafe_allow_html=True)

                # The concierge response bubble
                timestamp_str = (
                    f"<div style='font-size: 0.65rem; color: rgba(230,32,32,0.45); margin-top: 0.3rem;'>{msg.get('timestamp', '')}</div>"
                    if msg.get("timestamp")
                    else ""
                )
                # Strip speaker name prefix if present (e.g., "C: text" -> "text")
                content = msg["content"]
                if ": " in content:
                    parts = content.split(": ", 1)
                    if len(parts) == 2 and not parts[0].startswith("{"):
                        content = parts[1]
                st.markdown(
                    f"""
                <div class="msg-concierge">
                    <div class="concierge-avatar">C</div>
                    <div>
                        <div class="bubble">{content}{timestamp_str}</div>
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

                # Memory update card
                if msg.get("memory_update"):
                    mu = msg["memory_update"]
                    st.markdown(
                        f"""
                    <div class="memory-update-card">
                        <div class="memory-update-title">Memory Added in {mu.get("save_ms", 0):.0f}ms</div>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )

                # Retrieved memories - outer st.expander, inner HTML
                # <details> per record (Streamlit disallows nested
                # st.expander).
                _render_memory_records(msg.get("memory_records") or [])

        # ── Process pending prompt (from button or chat input) ──
        pending = st.session_state.pending_prompt
        if pending and (
            st.session_state.get("is_session_readonly")
            or st.session_state.agentmem_session is None
        ):
            # Drop any prompt that arrived while the active session is
            # read-only or absent. The user must click New Chat to send
            # messages; we never silently create a session on their
            # behalf.
            st.session_state.pending_prompt = None
            pending = None
        if pending:
            st.session_state.chat_messages.append({"role": "user", "content": pending})
            st.session_state.pending_prompt = None

            # Render the user message immediately
            st.markdown(
                f"""
            <div class="msg-guest">
                <div class="bubble">{pending}</div>
            </div>
            """,
                unsafe_allow_html=True,
            )

            # ── Live status pipeline ──
            status_placeholder = st.empty()
            status_log = []

            def render_status(lines_done: list, active_line: str | None = None):
                html = '<div class="status-pipeline">'
                for line in lines_done:
                    html += f"""
                    <div class="status-line done">
                        <div class="status-dot done"></div>
                        {line}
                    </div>"""
                if active_line:
                    html += f"""
                    <div class="status-line active">
                        <div class="status-dot active"></div>
                        {active_line}
                    </div>"""
                html += "</div>"
                status_placeholder.markdown(html, unsafe_allow_html=True)

            try:
                total_start = time.time()

                # The concierge graph owns retrieval + synthesis + write.
                # The UI used to fan out a duplicate get_memory call here
                # purely for status display - we now read those numbers
                # back from graph state instead.
                session = st.session_state.agentmem_session

                render_status([], "Concierge is preparing your response…")
                llm_start = time.time()

                # ── agentc: open root span for this turn ──────────────────
                root_span = None
                try:
                    catalog = get_catalog()
                    if catalog is not None:
                        from agentc_core.activity import GlobalSpan
                        from agentc_core.version import VersionDescriptor
                        from agentc_core.activity.models.content import UserContent

                        root_span = GlobalSpan(
                            config=catalog,
                            version=VersionDescriptor(
                                timestamp=datetime.datetime.now(datetime.timezone.utc),
                                is_dirty=True,
                            ),
                            name="hotel-concierge",
                            kwargs={
                                "agentmem_session_id": str(
                                    getattr(session, "session_id", "unknown")
                                ),
                                "persona": pkey,
                            },
                        )
                        root_span.enter()
                        root_span.log(UserContent(value=pending))
                except Exception as _exc:
                    import traceback

                    print(f"[agentc] span init failed — tracing disabled: {_exc}")
                    traceback.print_exc()
                    root_span = None

                graph = ConciergeGraph(
                    session=session,
                    with_memory_template=HOTEL_CONCIERGE_WITH_MEMORY_TEMPLATE,
                    no_memory_template=HOTEL_CONCIERGE_NO_MEMORY_TEMPLATE,
                )
                state = graph.run(query=pending, use_memory=True, span=root_span)

                # ── agentc: close root span ───────────────────────────────
                if root_span is not None:
                    try:
                        root_span.exit()
                    except Exception as _exc:
                        import traceback

                        print(f"[agentc] span exit failed: {_exc}")
                        traceback.print_exc()
                total_graph_ms = (time.time() - llm_start) * 1000
                reply = state.get(
                    "assistant_response",
                    "I apologise, I could not generate a response.",
                )

                retrieval_ms = state.get("retrieval_ms", 0.0) or 0.0
                memory_context = state.get("memory_context") or ""
                # Approximate block count from the formatted context;
                # exact count lives in toolkit internals but this is
                # close enough for the status pipeline.
                memory_blocks = sum(
                    1 for line in memory_context.splitlines() if line.startswith("- ")
                )

                status_log.append(
                    f"Memory search complete · {memory_blocks} blocks retrieved · {retrieval_ms:.0f}ms"
                )

                memory_write_ms = state.get("memory_write_ms", 0)
                llm_only_ms = total_graph_ms - memory_write_ms - retrieval_ms

                status_log.append(f"Response generated · {llm_only_ms:.0f}ms")

                total_ms = (time.time() - total_start) * 1000
                status_log.append(f"Total round-trip · {total_ms:.0f}ms")

                render_status(status_log)

                # Store the completed assistant message
                st.session_state.chat_messages.append(
                    {
                        "role": "assistant",
                        "content": reply,
                        "status_log": status_log,
                        "memory_update": {
                            "save_ms": memory_write_ms,
                        },
                        "memory_records": state.get("memory_records") or [],
                    }
                )

            except Exception as exc:
                status_log.append(f"Error: {exc}")
                render_status(status_log)
                st.session_state.chat_messages.append(
                    {
                        "role": "assistant",
                        "content": f"I apologise, something went wrong. Please try again.\n\n`{exc}`",
                        "status_log": status_log,
                        "memory_update": None,
                    }
                )
                st.code(traceback.format_exc())

            st.rerun()


# ─────────────────────────────────────────────
# Chat input — top-level so Streamlit anchors it to the bottom
# ─────────────────────────────────────────────

if st.session_state.authenticated and st.session_state.active_persona:
    _pkey = st.session_state.active_persona
    if _pkey in PERSONAS:
        _chat_display_name = PERSONAS[_pkey]["display_name"].split()[0]
    else:
        _u = st.session_state.agentmem_user
        _user_name = getattr(_u, "name", _pkey) if _u else _pkey
        _chat_display_name = _user_name.split()[0]

    _readonly = bool(st.session_state.get("is_session_readonly", False))
    _no_session = st.session_state.get("agentmem_session") is None

    if _readonly or _no_session:
        # Disable input when the active session is read-only OR no
        # session is loaded (e.g. right after End Session). The only way
        # to send messages is to start a New Chat.
        if _no_session and not _readonly:
            _placeholder = "Click New Chat to start a conversation."
        else:
            _placeholder = (
                "Viewing a previous session - start a New Chat to send messages."
            )
        st.chat_input(_placeholder, disabled=True)
    else:
        if _prompt := st.chat_input(f"Message your concierge, {_chat_display_name}..."):
            st.session_state.pending_prompt = _prompt
            st.rerun()

# ─────────────────────────────────────────────
# JS: align stBottom with the main (second) column
# ─────────────────────────────────────────────

st.markdown(
    """
<script>
(function alignChatInput() {
    function apply() {
        const cols = window.parent.document.querySelectorAll('[data-testid="stHorizontalBlock"] > [data-testid="stVerticalBlock"]');
        const bottom = window.parent.document.querySelector('[data-testid="stBottom"]');
        if (!bottom || cols.length < 2) return;
        const mainCol = cols[1];
        const rect = mainCol.getBoundingClientRect();
        const vw = window.parent.innerWidth;
        bottom.style.left = rect.left + 'px';
        bottom.style.right = (vw - rect.right) + 'px';
        bottom.style.position = 'fixed';
    }
    // Run immediately and after brief delays to catch layout settling
    apply();
    setTimeout(apply, 300);
    setTimeout(apply, 800);
    window.parent.addEventListener('resize', apply);
})();
</script>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────

st.markdown(
    """
<div style="text-align:center; padding:2rem 0 1rem;
            color:rgba(230,32,32,0.2); font-size:0.7rem;
            letter-spacing:0.2em; text-transform:uppercase;">
    Couchbase Agent Memory Hotel · Personal Concierge · Powered by Couchbase Agent Memory
</div>
""",
    unsafe_allow_html=True,
)
