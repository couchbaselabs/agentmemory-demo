"""
FastAPI backend for the Next.js Hotel UI.

Wraps all Python agents and Couchbase Agent Memory SDK operations
as REST + SSE endpoints consumed by hotel_ui/.

Run:
    uvicorn hotel_server:app --host 0.0.0.0 --port 8501 --reload

Requires the same .env as agentmem_hotel.py / agentmem_hotel_ops.py.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

import uvicorn
from agentmemory import AgentMemoryClient
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agents._ops_utils import get_or_create_role_user
from agents.briefing_agent import BriefingGraph
from agents.call_note_agent import CALL_NOTE_CATEGORIES, CallNoteGraph
from agents.concierge_agent import ConciergeGraph
from agents.digest_agent import DigestGraph
from agents.flag_agent import FlagGraph
from agents.group_event_brief_agent import GroupEventBriefGraph
from agents.profile_overview_agent import ProfileOverviewGraph
from agents.safety_scan_agent import SafetyScanGraph
from prompts import (
    HOTEL_CONCIERGE_NO_MEMORY_TEMPLATE,
    HOTEL_CONCIERGE_WITH_MEMORY_TEMPLATE,
)

load_dotenv()

# ---------------------------------------------------------------------------
# App & CORS
# ---------------------------------------------------------------------------

app = FastAPI(title="Hotel Agent Memory Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8502", "http://127.0.0.1:8502"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Shared client (lazy-init on first request)
# ---------------------------------------------------------------------------

_client: AgentMemoryClient | None = None
_concierge_graphs: dict[str, ConciergeGraph] = {}
_executor = ThreadPoolExecutor(max_workers=10)

# In-memory caches (mimics Streamlit session_state for ops)
_safety_scan_cache: list[dict] | None = None
_safety_scan_ts: str | None = None
_digest_cache: dict | None = None
_digest_ts: str | None = None


def get_client() -> AgentMemoryClient:
    global _client
    if _client is None:
        base_url = os.getenv("AGENTMEM_BASE_URL", "http://localhost:8080")
        _client = AgentMemoryClient(base_url=base_url, timeout=30.0, verify=False)
    return _client


# ---------------------------------------------------------------------------
# Personas (mirrored from agentmem_hotel.py)
# ---------------------------------------------------------------------------

PERSONAS = {
    "alice_chen": {
        "user_id": "alice_chen",
        "display_name": "Alice",
        "full_name": "Alice",
        "type": "Corporate Traveler",
        "stays": "6 stays · Business",
        "desc": "Frequent business traveler. Dense history, high stakes.",
        "initials": "AC",
        "password": "123",
    },
    "bob_morrison": {
        "user_id": "bob_morrison",
        "display_name": "Bob",
        "full_name": "Bob",
        "type": "Occasion Traveler",
        "stays": "3 stays · Personal",
        "desc": "Anniversary stays, emotionally significant trips.",
        "initials": "BO",
        "password": "123",
    },
    "charlie_wu": {
        "user_id": "charlie_wu",
        "display_name": "Charlie",
        "full_name": "Charlie",
        "type": "Group Organizer",
        "stays": "4 events · Groups",
        "desc": "Books for 30–50 people. Doesn't stay himself.",
        "initials": "CM",
        "password": "123",
    },
}

ROLES = {
    "role_gm": {
        "name": "General Manager",
        "tagline": "Property-wide oversight",
        "password": "ops",
        "default_view": "dashboard",
        "allowed_views": [
            "dashboard",
            "log-call",
            "pre-arrival",
            "allergy",
            "group-brief",
            "digest",
            "role-memory",
            "how-it-works",
        ],
        "can_read_role_memory": [
            "role_gm",
            "role_front_desk",
            "role_events",
            "role_facilities",
        ],
    },
    "role_front_desk": {
        "name": "Front Desk",
        "tagline": "Arrivals · Check-in · Service Recovery",
        "password": "ops",
        "default_view": "pre-arrival",
        "allowed_views": [
            "dashboard",
            "log-call",
            "pre-arrival",
            "allergy",
            "role-memory",
            "how-it-works",
        ],
        "can_read_role_memory": ["role_front_desk"],
    },
    "role_events": {
        "name": "Events Coordinator",
        "tagline": "Group bookings · Facilities pre-briefs",
        "password": "ops",
        "default_view": "group-brief",
        "allowed_views": [
            "dashboard",
            "log-call",
            "group-brief",
            "role-memory",
            "how-it-works",
        ],
        "can_read_role_memory": ["role_events"],
    },
    "role_facilities": {
        "name": "Facilities",
        "tagline": "AV · Accessibility · Maintenance",
        "password": "ops",
        "default_view": "group-brief",
        "allowed_views": [
            "dashboard",
            "log-call",
            "group-brief",
            "role-memory",
            "how-it-works",
        ],
        "can_read_role_memory": ["role_facilities"],
    },
}

MEMORY_TTL_PRESETS = {
    "1 day": 86400,
    "3 days": 259200,
    "1 week": 604800,
}

# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------


def _sse(event_type: str, data: Any) -> str:
    payload = json.dumps({"type": event_type, "data": data})
    return f"data: {payload}\n\n"


async def _run_in_executor(fn, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, lambda: fn(*args, **kwargs))


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    user_id: str
    password: str
    memory_mode: str = "persistent"
    memory_ttl_seconds: int = 0
    memory_ttl_label: str = "Forever"


class CreateUserRequest(BaseModel):
    name: str
    user_id: str | None = None
    password: str | None = None


class CreateSessionRequest(BaseModel):
    memory_mode: str = "persistent"
    memory_ttl_seconds: int = 0


class ChatRequest(BaseModel):
    user_id: str
    session_id: str
    message: str
    memory_mode: str = "persistent"
    memory_ttl_seconds: int = 0
    speaker_name: str | None = None


class OpsLoginRequest(BaseModel):
    role_id: str
    password: str


class BriefingRequest(BaseModel):
    guest_id: str
    arrival_time: str


class CallNoteRequest(BaseModel):
    guest_id: str
    raw_note: str
    staff_category: str
    logged_by_role: str
    logged_by_role_name: str


class FlagRequest(BaseModel):
    guest_id: str
    trigger_type: str
    trigger_payload: str


class GroupBriefRequest(BaseModel):
    organiser_id: str
    event_date: str
    attendee_count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session_preview(session) -> str:
    """Exact port of Streamlit's _fetch_session_preview — unwraps resp.memory_blocks."""
    try:
        resp = session.list_memories(limit=10, offset=0, order_by="ingested_at")
        # SDK wraps response: resp.memory_blocks is the actual list
        blocks = getattr(resp, "memory_blocks", None)
        if blocks is None:
            blocks = resp if isinstance(resp, (list, tuple)) else []

        messages = []
        for block in blocks:
            msg = getattr(block, "message", None)
            if msg and getattr(msg, "user_content", None):
                annotations = getattr(block, "annotations", None) or {}
                ts = (
                    (
                        annotations.get("timestamp")
                        if isinstance(annotations, dict)
                        else None
                    )
                    or getattr(block, "ingested_at", "")
                    or ""
                )
                messages.append((ts, msg.user_content))

        if not messages:
            return "No messages yet"

        messages.sort(key=lambda x: x[0] or "")
        cleaned = []
        for content in [m[1] for m in messages[:3]]:
            if ": " in content:
                parts = content.split(": ", 1)
                if len(parts) == 2 and not parts[0].startswith("{"):
                    content = parts[1]
            content = content.strip().replace("\n", " ")
            cleaned.append(content[:35] + ("…" if len(content) > 35 else ""))

        summary = " | ".join(cleaned)
        return summary[:120] + ("…" if len(summary) > 120 else "")
    except Exception as exc:
        print(f"warning: session preview failed — {exc}")
        return "No messages yet"


def _unwrap_users(result) -> list:
    """Unwrap list_users() response — handles object, dict, or bare list."""
    if hasattr(result, "users"):
        return result.users
    if isinstance(result, dict) and "users" in result:
        return result["users"]
    if isinstance(result, (list, tuple)):
        return list(result)
    return []


def _unwrap_sessions(result) -> list:
    """Unwrap list_sessions() response — handles object, dict, str list, or bare list."""
    if hasattr(result, "sessions"):
        return result.sessions
    if isinstance(result, dict) and "sessions" in result:
        return result["sessions"]
    if isinstance(result, (list, tuple)):
        return list(result)
    return []


def _user_id(u) -> str:
    """Extract user_id from a user object — SDK uses .id, not .user_id."""
    return (
        getattr(u, "id", None)
        or getattr(u, "user_id", None)
        or (u.get("id") if isinstance(u, dict) else None)
        or (u.get("user_id") if isinstance(u, dict) else None)
        or str(u)
    )


def _session_id(s) -> str:
    """Extract session_id from a session entry — may be a plain string or object."""
    if isinstance(s, str):
        return s
    if isinstance(s, tuple):
        return s[0] if s else ""
    return (
        getattr(s, "session_id", None)
        or getattr(s, "id", None)
        or (s.get("id") if isinstance(s, dict) else None)
        or str(s)
    )


def _get_user_safe(user_id: str):
    client = get_client()
    try:
        return client.get_user(user_id=user_id)
    except Exception:
        return None


def _serialize_memory_blocks(blocks) -> list[dict]:
    out = []
    for b in blocks:
        item: dict = {"block_id": getattr(b, "block_id", "")}
        if hasattr(b, "fact") and b.fact:
            item["kind"] = "fact"
            item["text"] = b.fact
        elif hasattr(b, "summary") and b.summary:
            item["kind"] = "summary"
            item["text"] = b.summary
        elif hasattr(b, "message") and b.message:
            item["kind"] = "chat"
            item["user_content"] = getattr(b.message, "user_content", "") or ""
            item["assistant_content"] = (
                getattr(b.message, "assistant_content", "") or ""
            )
        else:
            item["kind"] = "unknown"
            item["text"] = str(b)
        item["ingested_at"] = getattr(b, "ingested_at", "")
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@app.post("/auth/login")
async def login(req: LoginRequest):
    # Check predefined personas first
    if req.user_id in PERSONAS:
        persona = PERSONAS[req.user_id]
        if persona["password"] != req.password:
            raise HTTPException(status_code=401, detail="Invalid password")
        user = _get_user_safe(req.user_id)
        if user is None:
            raise HTTPException(
                status_code=404, detail=f"User {req.user_id} not found in memory store"
            )
        return {"success": True, "user_id": req.user_id, "persona": persona}
    # Dynamic users: password is always "123"
    if req.password != "123":
        raise HTTPException(status_code=401, detail="Invalid password")
    user = _get_user_safe(req.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {req.user_id} not found")
    return {"success": True, "user_id": req.user_id, "persona": None}


@app.post("/auth/ops-login")
async def ops_login(req: OpsLoginRequest):
    role = ROLES.get(req.role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Unknown role")
    if role["password"] != req.password:
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"success": True, "role_id": req.role_id, "role": role}


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@app.get("/users")
async def list_users():
    client = get_client()
    try:
        raw = _unwrap_users(client.list_users())
        result = []
        for u in raw:
            uid = _user_id(u)
            if not uid or uid.startswith("role_"):
                continue
            name = (
                getattr(u, "name", None)
                or (u.get("name") if isinstance(u, dict) else None)
                or uid
            )
            persona = PERSONAS.get(uid)
            result.append(
                {
                    "user_id": uid,
                    "name": name,
                    "type": persona["type"] if persona else "Guest",
                    "initials": persona["initials"]
                    if persona
                    else (name[:2].upper() if name else "?"),
                    "desc": persona["desc"] if persona else "",
                    "stays": persona["stays"] if persona else "",
                }
            )
        return {"users": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/users")
async def create_user(req: CreateUserRequest):
    client = get_client()
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if req.user_id and req.user_id.strip():
        user_id = req.user_id.strip()
    else:
        user_id = name.lower().replace(" ", "_").replace("-", "_")
        user_id = "".join(c for c in user_id if c.isalnum() or c == "_")
    t0 = time.perf_counter()
    try:
        client.create_user(user_id=user_id, name=name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    return {
        "user_id": user_id,
        "name": name,
        "created_ms": elapsed_ms,
        "password": "123",
    }


@app.delete("/users/{user_id}")
async def delete_user(user_id: str):
    user = _get_user_safe(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        user.delete()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, "user_id": user_id}


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@app.get("/users/{user_id}/sessions")
async def list_sessions(user_id: str):
    user = _get_user_safe(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        raw = _unwrap_sessions(user.list_sessions())
        sessions = []
        for i, s in enumerate(raw):
            sid = _session_id(s)
            if not sid:
                continue
            try:
                sess = user.get_session(session_id=sid)
                preview = await _run_in_executor(_session_preview, sess)
                sessions.append(
                    {
                        "session_id": sid,
                        "number": i + 1,
                        "preview": preview,
                        "label": f"Session {i + 1} - {preview}",
                    }
                )
            except Exception:
                sessions.append(
                    {
                        "session_id": sid,
                        "number": i + 1,
                        "preview": "(error loading)",
                        "label": f"Session {i + 1}",
                    }
                )
        return {"sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/users/{user_id}/sessions")
async def create_session(user_id: str, req: CreateSessionRequest):
    user = _get_user_safe(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        raw = _unwrap_sessions(user.list_sessions())
        nums = []
        for s in raw:
            sid = _session_id(s)
            parts = sid.rsplit("_", 1)
            if len(parts) == 2 and parts[1].isdigit():
                nums.append(int(parts[1]))
        next_num = (max(nums) + 1) if nums else 1
        new_sid = f"session_{next_num}"
        ttl = (
            req.memory_ttl_seconds
            if req.memory_ttl_seconds and req.memory_ttl_seconds > 0
            else None
        )
        user.create_session(session_id=new_sid, memory_blocks_ttl=ttl)
        return {"session_id": new_sid, "number": next_num}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sessions/{session_id}/end")
async def end_session(session_id: str, user_id: str):
    user = _get_user_safe(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        sess = user.get_session(session_id=session_id)
        sess.end()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/{user_id}/sessions/{session_id}/messages")
async def get_session_messages(user_id: str, session_id: str):
    # Port of Streamlit's load_session_history — paginates, filters by
    # block.message, sorts by timestamp, returns role/content/timestamp pairs.
    user = _get_user_safe(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        sess = user.get_session(session_id=session_id)

        all_blocks = []
        offset = 0
        page_size = 200
        while True:
            resp = sess.list_memories(
                limit=page_size, offset=offset, order_by="ingested_at"
            )
            page = getattr(resp, "memory_blocks", None)
            if page is None:
                page = resp if isinstance(resp, (list, tuple)) else []
            all_blocks.extend(page)
            total = getattr(resp, "total", None)
            if len(page) < page_size or (
                total is not None and len(all_blocks) >= total
            ):
                break
            offset += page_size

        # Filter: only blocks with a chat message containing actual content
        all_messages = []
        for block in all_blocks:
            msg = getattr(block, "message", None)
            if msg is None:
                continue
            user_content = getattr(msg, "user_content", None) or ""
            assistant_content = getattr(msg, "assistant_content", None) or ""
            if not user_content and not assistant_content:
                continue
            annotations = getattr(block, "annotations", None) or {}
            ts = (
                (
                    annotations.get("timestamp")
                    if isinstance(annotations, dict)
                    else None
                )
                or getattr(block, "ingested_at", "")
                or ""
            )
            all_messages.append(
                {
                    "timestamp": ts,
                    "user_content": user_content,
                    "assistant_content": assistant_content,
                }
            )

        # Sort chronologically oldest-first
        all_messages.sort(key=lambda m: m.get("timestamp") or "")

        # Convert to role/content pairs (same shape Streamlit uses for chat_messages)
        chat_history = []
        for m in all_messages:
            if m["user_content"]:
                chat_history.append(
                    {
                        "role": "user",
                        "content": m["user_content"],
                        "timestamp": m["timestamp"],
                    }
                )
            if m["assistant_content"]:
                chat_history.append(
                    {
                        "role": "assistant",
                        "content": m["assistant_content"],
                        "timestamp": m["timestamp"],
                    }
                )

        return {"messages": chat_history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Profile Overview
# ---------------------------------------------------------------------------


@app.get("/users/{user_id}/profile")
async def get_profile(user_id: str):
    user = _get_user_safe(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    persona = PERSONAS.get(user_id, {})
    guest_name = persona.get("full_name", user_id)
    try:
        client = get_client()
        result = await _run_in_executor(
            lambda: ProfileOverviewGraph().run(
                agentmem_user=user,
                client=client,
                guest_id=user_id,
                guest_name=guest_name,
            )
        )
        profile = result.get("profile", {})
        return {
            "profile": profile,
            "retrieval_ms": result.get("retrieval_ms", 0),
            "synthesis_ms": result.get("synthesis_ms", 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Chat (SSE stream)
# ---------------------------------------------------------------------------


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    async def generate():
        user = _get_user_safe(req.user_id)
        if user is None:
            yield _sse("error", {"message": f"User {req.user_id} not found"})
            return

        try:
            sess = user.get_session(session_id=req.session_id)
        except Exception as e:
            yield _sse("error", {"message": f"Session not found: {e}"})
            return

        graph_key = f"{req.user_id}:{req.session_id}"
        if graph_key not in _concierge_graphs:
            _concierge_graphs[graph_key] = ConciergeGraph(
                session=sess,
                with_memory_template=HOTEL_CONCIERGE_WITH_MEMORY_TEMPLATE,
                no_memory_template=HOTEL_CONCIERGE_NO_MEMORY_TEMPLATE,
            )
        graph = _concierge_graphs[graph_key]

        use_memory = req.memory_mode != "anonymous"

        # Emit all pipeline steps as "pending" immediately so the UI
        # can show the full pipeline structure while the graph runs.
        pending_steps = [
            {"step": "Query rewriter", "state": "running", "detail": ""},
            {"step": "Memory search", "state": "pending", "detail": ""},
            {"step": "LLM response", "state": "pending", "detail": ""},
        ]
        if use_memory:
            pending_steps.append(
                {"step": "Memory write", "state": "pending", "detail": ""}
            )
        yield _sse("status_complete", {"steps": pending_steps, "total_ms": None})

        t_start = time.perf_counter()
        try:
            result = await _run_in_executor(
                lambda: graph.run(
                    query=req.message,
                    use_memory=use_memory,
                    speaker_name=req.speaker_name,
                )
            )
        except Exception as e:
            yield _sse("error", {"message": str(e)})
            return

        total_ms = round((time.perf_counter() - t_start) * 1000)
        retrieval_ms = result.get("retrieval_ms", 0) or 0
        write_ms = result.get("memory_write_ms", 0) or 0
        response = result.get("assistant_response", "")
        memory_records = result.get("memory_records", []) or []
        memory_context = result.get("memory_context", "") or ""
        refined_queries = result.get("refined_queries", []) or []
        block_count = len(memory_records) or sum(
            1 for line in memory_context.splitlines() if line.startswith("- ")
        )

        llm_ms = max(0, total_ms - round(retrieval_ms) - round(write_ms))

        done_steps = [
            {
                "step": "Query rewriter",
                "state": "done",
                "detail": f"{len(refined_queries)} queries",
                "queries": refined_queries,
            },
            {
                "step": "Memory search",
                "state": "done",
                "detail": f"{block_count} blocks · {round(retrieval_ms)}ms",
            },
            {"step": "LLM response", "state": "done", "detail": f"{llm_ms}ms"},
        ]
        if use_memory and write_ms:
            done_steps.append(
                {
                    "step": "Memory write",
                    "state": "done",
                    "detail": f"{round(write_ms)}ms",
                }
            )

        yield _sse("status_complete", {"steps": done_steps, "total_ms": total_ms})
        yield _sse(
            "response", {"content": response, "timestamp": datetime.now().isoformat()}
        )

        if use_memory and write_ms:
            yield _sse("memory_update", {"save_ms": round(write_ms)})

        if memory_records:
            yield _sse("memory_records", {"records": memory_records})

        yield _sse("done", {})

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Ops: guests
# ---------------------------------------------------------------------------


@app.get("/ops/guests")
async def ops_guests():
    client = get_client()
    try:
        raw = _unwrap_users(client.list_users())
        result = []
        for u in raw:
            uid = _user_id(u)
            if not uid or uid.startswith("role_"):
                continue
            name = (
                getattr(u, "name", None)
                or (u.get("name") if isinstance(u, dict) else None)
                or uid
            )
            persona = PERSONAS.get(uid)
            result.append(
                {
                    "user_id": uid,
                    "name": name,
                    "type": persona["type"] if persona else "Guest",
                    "initials": persona["initials"]
                    if persona
                    else (name[:2].upper() if name else "?"),
                }
            )
        return {"guests": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Ops: safety scan
# ---------------------------------------------------------------------------


@app.get("/ops/safety-scan")
async def ops_safety_scan(force: bool = False):
    global _safety_scan_cache, _safety_scan_ts
    if not force and _safety_scan_cache is not None:
        return {
            "items": _safety_scan_cache,
            "scanned_at": _safety_scan_ts,
            "cached": True,
        }

    client = get_client()
    try:
        raw = _unwrap_users(client.list_users())
        guest_users = [
            (uid, u) for u in raw if not (uid := _user_id(u)).startswith("role_")
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    all_items: list[dict] = []
    for uid, u in guest_users:
        persona = PERSONAS.get(uid)
        name = persona["full_name"] if persona else getattr(u, "name", uid)
        try:
            result = await _run_in_executor(
                lambda _u=u, _uid=uid, _n=name, _c=client: SafetyScanGraph().run(
                    agentmem_user=_u,
                    client=_c,
                    guest_id=_uid,
                    guest_name=_n,
                )
            )
            items = result.get("safety_items", [])
            for item in items:
                item["guest_id"] = uid
                item["guest_name"] = name
            all_items.extend(items)
        except Exception:
            pass

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    all_items.sort(key=lambda x: severity_order.get(x.get("severity", "low"), 3))
    _safety_scan_cache = all_items
    _safety_scan_ts = datetime.now().isoformat()
    return {"items": all_items, "scanned_at": _safety_scan_ts, "cached": False}


# ---------------------------------------------------------------------------
# Ops: briefing (SSE)
# ---------------------------------------------------------------------------


@app.post("/ops/briefing/stream")
async def ops_briefing_stream(req: BriefingRequest):
    async def generate():
        client = get_client()
        user = _get_user_safe(req.guest_id)
        persona = PERSONAS.get(req.guest_id, {})
        guest_name = persona.get("full_name", req.guest_id)
        if user is None:
            yield _sse("error", {"message": f"Guest {req.guest_id} not found"})
            return

        yield _sse("status", {"step": "Memory retrieval", "state": "running"})
        try:
            result = await _run_in_executor(
                lambda: BriefingGraph().run(
                    client=client,
                    agentmem_user=user,
                    guest_id=req.guest_id,
                    guest_name=guest_name,
                    arrival_time=req.arrival_time,
                )
            )
            yield _sse(
                "status_complete",
                {
                    "steps": [
                        {
                            "step": "Memory retrieval",
                            "state": "done",
                            "detail": f"{round(result.get('retrieval_ms', 0))}ms",
                        },
                        {
                            "step": "LLM synthesis",
                            "state": "done",
                            "detail": f"{round(result.get('synthesis_ms', 0))}ms",
                        },
                    ],
                    "total_ms": round(
                        result.get("retrieval_ms", 0) + result.get("synthesis_ms", 0)
                    ),
                },
            )
            yield _sse(
                "response",
                {
                    "briefing": result.get("briefing", {}),
                    "retrieval_ms": result.get("retrieval_ms", 0),
                    "synthesis_ms": result.get("synthesis_ms", 0),
                    "write_ok": result.get("write_ok", False),
                },
            )
        except Exception as e:
            yield _sse("error", {"message": str(e)})
            return
        yield _sse("done", {})

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Ops: call note (SSE)
# ---------------------------------------------------------------------------


@app.post("/ops/call-note/stream")
async def ops_call_note_stream(req: CallNoteRequest, role_id: str = "role_front_desk"):
    async def generate():
        client = get_client()
        user = _get_user_safe(req.guest_id)
        persona = PERSONAS.get(req.guest_id, {})
        guest_name = persona.get("full_name", req.guest_id)
        if user is None:
            yield _sse("error", {"message": f"Guest {req.guest_id} not found"})
            return

        yield _sse("status", {"step": "Classifying note", "state": "running"})
        try:
            session_list = user.list_sessions()
            first_sessions = getattr(session_list, "sessions", None) or []
            if first_sessions:
                sess = user.get_session(session_id=first_sessions[0].session_id)
            else:
                sess = None
        except Exception as e:
            print(f"  [call-note] session lookup failed: {e}")
            sess = None

        try:
            result = await _run_in_executor(
                lambda: CallNoteGraph().run(
                    client=client,
                    agentmem_session=sess,
                    agentmem_user=user,
                    guest_id=req.guest_id,
                    guest_name=guest_name,
                    raw_note=req.raw_note,
                    staff_category=req.staff_category,
                    logged_by_role=req.logged_by_role,
                    logged_by_role_name=req.logged_by_role_name,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
                )
            )
            yield _sse(
                "status_complete",
                {
                    "steps": [
                        {
                            "step": "Classifying note",
                            "state": "done",
                            "detail": f"{round(result.get('classify_ms', 0))}ms",
                        },
                        {
                            "step": "Memory dedup search",
                            "state": "done",
                            "detail": f"{round(result.get('retrieval_ms', 0))}ms",
                        },
                        {
                            "step": "Memory write",
                            "state": "done",
                            "detail": f"{round(result.get('write_ms', 0))}ms",
                        },
                    ],
                    "total_ms": round(
                        sum(
                            result.get(k, 0)
                            for k in ("classify_ms", "retrieval_ms", "write_ms")
                        )
                    ),
                },
            )
            yield _sse(
                "response",
                {
                    "write_ok": result.get("write_ok", False),
                    "classified_category": result.get(
                        "classified_category", req.staff_category
                    ),
                    "canonical_fact": result.get("canonical_fact", ""),
                    "classify_ms": result.get("classify_ms", 0),
                    "retrieval_ms": result.get("retrieval_ms", 0),
                    "write_ms": result.get("write_ms", 0),
                },
            )
        except Exception as e:
            yield _sse("error", {"message": str(e)})
            return
        yield _sse("done", {})

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/ops/call-note-categories")
async def call_note_categories():
    return {"categories": CALL_NOTE_CATEGORIES}


# ---------------------------------------------------------------------------
# Ops: flag (SSE)
# ---------------------------------------------------------------------------


@app.post("/ops/flag/stream")
async def ops_flag_stream(req: FlagRequest):
    async def generate():
        client = get_client()
        user = _get_user_safe(req.guest_id)
        persona = PERSONAS.get(req.guest_id, {})
        guest_name = persona.get("full_name", req.guest_id)
        if user is None:
            yield _sse("error", {"message": f"Guest {req.guest_id} not found"})
            return

        yield _sse("status", {"step": "Memory retrieval", "state": "running"})
        try:
            result = await _run_in_executor(
                lambda: FlagGraph().run(
                    client=client,
                    agentmem_user=user,
                    guest_id=req.guest_id,
                    guest_name=guest_name,
                    trigger_type=req.trigger_type,
                    trigger_payload=req.trigger_payload,
                )
            )
            yield _sse(
                "status_complete",
                {
                    "steps": [
                        {
                            "step": "Memory retrieval",
                            "state": "done",
                            "detail": f"{round(result.get('retrieval_ms', 0))}ms",
                        },
                        {
                            "step": "LLM flag analysis",
                            "state": "done",
                            "detail": f"{round(result.get('synthesis_ms', 0))}ms",
                        },
                    ],
                    "total_ms": round(
                        result.get("retrieval_ms", 0) + result.get("synthesis_ms", 0)
                    ),
                },
            )
            yield _sse(
                "response",
                {
                    "flag": result.get("flag", {}),
                    "write_ok": result.get("write_ok", False),
                    "retrieval_ms": result.get("retrieval_ms", 0),
                    "synthesis_ms": result.get("synthesis_ms", 0),
                },
            )
        except Exception as e:
            yield _sse("error", {"message": str(e)})
            return
        yield _sse("done", {})

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Ops: digest
# ---------------------------------------------------------------------------


@app.get("/ops/digest")
async def ops_digest(force: bool = False):
    global _digest_cache, _digest_ts
    if not force and _digest_cache is not None:
        return {"digest": _digest_cache, "generated_at": _digest_ts, "cached": True}

    client = get_client()
    try:
        raw = _unwrap_users(client.list_users())
        user_list = [
            (uid, u) for u in raw if not (uid := _user_id(u)).startswith("role_")
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    period = datetime.now().strftime("%B %Y")
    try:
        result = await _run_in_executor(
            lambda: DigestGraph().run(
                client=client,
                user_list=user_list,
                period=period,
            )
        )
        _digest_cache = result.get("digest", {})
        _digest_ts = datetime.now().isoformat()
        return {
            "digest": _digest_cache,
            "generated_at": _digest_ts,
            "cached": False,
            "retrieval_ms": result.get("retrieval_ms", 0),
            "synthesis_ms": result.get("synthesis_ms", 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Ops: group brief (SSE)
# ---------------------------------------------------------------------------


@app.post("/ops/group-brief/stream")
async def ops_group_brief_stream(req: GroupBriefRequest):
    async def generate():
        client = get_client()
        user = _get_user_safe(req.organiser_id)
        persona = PERSONAS.get(req.organiser_id, {})
        organiser_name = persona.get("full_name", req.organiser_id)
        if user is None:
            yield _sse("error", {"message": f"Organiser {req.organiser_id} not found"})
            return

        yield _sse("status", {"step": "Memory retrieval", "state": "running"})
        try:
            result = await _run_in_executor(
                lambda: GroupEventBriefGraph().run(
                    client=client,
                    agentmem_user=user,
                    organiser_id=req.organiser_id,
                    organiser_name=organiser_name,
                    event_date=req.event_date,
                    attendee_count=req.attendee_count,
                )
            )
            yield _sse(
                "status_complete",
                {
                    "steps": [
                        {
                            "step": "Memory retrieval",
                            "state": "done",
                            "detail": f"{round(result.get('retrieval_ms', 0))}ms",
                        },
                        {
                            "step": "LLM synthesis",
                            "state": "done",
                            "detail": f"{round(result.get('synthesis_ms', 0))}ms",
                        },
                    ],
                    "total_ms": round(
                        result.get("retrieval_ms", 0) + result.get("synthesis_ms", 0)
                    ),
                },
            )
            yield _sse(
                "response",
                {
                    "brief": result.get("brief", {}),
                    "write_ok": result.get("write_ok", False),
                    "retrieval_ms": result.get("retrieval_ms", 0),
                    "synthesis_ms": result.get("synthesis_ms", 0),
                },
            )
        except Exception as e:
            yield _sse("error", {"message": str(e)})
            return
        yield _sse("done", {})

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Ops: role memory
# ---------------------------------------------------------------------------


@app.get("/ops/role-memory/{role_id}")
async def ops_role_memory(role_id: str):
    client = get_client()
    from agents.config import k_for

    try:
        role_user = get_or_create_role_user(client, role_id)
        if role_user is None:
            return {"blocks": [], "role_id": role_id}
        session_list = role_user.list_sessions()
        all_blocks = []
        for session in session_list.sessions:
            try:
                sess = role_user.get_session(session_id=session.session_id)
                resp = sess.list_memories(
                    limit=k_for("role_memory"), order_by="ingested_at"
                )
                raw = (
                    getattr(resp, "memory_blocks", None)
                    or getattr(resp, "blocks", None)
                    or []
                )
                all_blocks.extend(_serialize_memory_blocks(raw))
            except Exception as e:
                print(f"  [role-memory] session {session.session_id} failed: {e}")
                pass
        return {"blocks": all_blocks, "role_id": role_id, "count": len(all_blocks)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------


@app.get("/meta/roles")
async def meta_roles():
    return {"roles": ROLES}


@app.get("/meta/personas")
async def meta_personas():
    return {"personas": PERSONAS}


@app.get("/meta/memory-presets")
async def meta_memory_presets():
    return {"presets": MEMORY_TTL_PRESETS}


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("hotel_server:app", host="0.0.0.0", port=8501, reload=True)
