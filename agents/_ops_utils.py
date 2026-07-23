"""
Internal helpers for the ops-side LangGraph agents that don't belong
in the memory toolkit (which owns search/format/rewrite).

Lives outside the public surface (leading underscore) - import via the
package only when implementing a new ops agent.

Provides:

* :func:`safe_parse_json` - defensive JSON extractor; tolerates
  ```json fences and stray prose.
* :func:`get_or_create_role_user` - get-or-create a Couchbase Agent
  Memory user for a role namespace (``role_gm``, ``role_front_desk``,
  ``role_events``). Role users persist across staff turnover and are
  the write target for ops artifacts.
* :func:`write_artifact_to_role` - persist a structured artifact (dict)
  into a role's session as an annotated memory write.
"""

from __future__ import annotations

import json
import re
import time


def safe_parse_json(text: str) -> dict | None:
    """Extract the first JSON object from text, tolerating code fences.

    Handles ```json code fences and attempts regex fallback for
    incomplete JSON. Returns None if no valid JSON is found.

    Args:
        text: String potentially containing JSON, with optional fences.

    Returns:
        Parsed dict if valid JSON found, else None.
    """
    if not text:
        return None
    cleaned = text.strip()
    fenced = re.match(
        r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL | re.IGNORECASE
    )
    if fenced:
        cleaned = fenced.group(1).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
    return None


def get_or_create_role_user(client, role_id: str, role_name: str | None = None):
    """Fetch or create the Couchbase Agent Memory user representing a role.

    Role users are the write target for ops artifacts so institutional
    memory persists across staff turnover.

    Args:
        client: Couchbase Agent Memory client instance.
        role_id: Role identifier string, e.g. "role_gm".
        role_name: Human-readable name for the role, used on creation.

    Returns:
        The role user object, or None if both fetch and create fail.
    """
    try:
        return client.get_user(user_id=role_id)
    except Exception:
        pass  # user not found; fall through to create
    try:
        return client.create_user(user_id=role_id, name=role_name or role_id)
    except Exception as exc:
        print(f"warning: could not get or create role user '{role_id}' — {exc}")
        return None


def _ensure_role_session(role_user, session_id: str = "ops_log"):
    """Get or create a single shared session for a role user.

    Args:
        role_user: Couchbase Agent Memory user object for the role.
        session_id: Session identifier to get or create.

    Returns:
        The session object, or None if retrieval and creation both fail.
    """
    try:
        return role_user.get_session(session_id=session_id)
    except Exception:
        pass  # session not found; fall through to create
    try:
        if hasattr(role_user, "create_session"):
            return role_user.create_session(session_id=session_id)
    except Exception as exc:
        print(f"warning: could not get or create role session '{session_id}' — {exc}")
        return None
    return None


def write_artifact_to_role(
    client,
    role_id: str,
    role_name: str,
    artifact: dict,
    artifact_type: str,
    ref_user: str | None = None,
    session_id: str = "ops_log",
) -> bool:
    """Persist an artifact dict into the role's memory pool.

    The artifact is serialised to JSON and stored as a ChatMessage with
    user_content containing a short label and assistant_content containing
    the JSON payload. Annotations record the agent that wrote it and
    optionally the guest the artifact references.

    Args:
        client: Couchbase Agent Memory client instance.
        role_id: Role namespace identifier, e.g. "role_front_desk".
        role_name: Human-readable role name used when creating the user.
        artifact: Dict to persist.
        artifact_type: Label string for the artifact type.
        ref_user: Optional guest user ID the artifact references.
        session_id: Session to write into (default "ops_log").

    Returns:
        True if the write succeeded, False otherwise.
    """
    role_user = get_or_create_role_user(client, role_id, role_name)
    if not role_user:
        return False
    role_session = _ensure_role_session(role_user, session_id=session_id)
    if not role_session:
        return False

    try:
        payload = json.dumps(artifact, ensure_ascii=False)
    except Exception as exc:
        print(f"warning: artifact JSON serialisation failed, using str() — {exc}")
        payload = str(artifact)

    label = f"{artifact_type} | ref_user={ref_user or '-'} | ts={int(time.time())}"
    fact = f"{label}: {payload}"
    annotations = {
        "source": artifact_type,
        "ref_user": ref_user or "",
        "role": role_id,
    }
    try:
        role_session.add_memory(
            facts=[fact],
            annotations=annotations,
            async_processing=False,
        )
        return True
    except Exception as exc:
        print(f"warning: role memory write failed for '{role_id}' — {exc}")
        return False


def get_user_session(user, client=None, user_id: str | None = None):
    """Get any session for a user to use as the entry point for cross-session searches.

    Since all session objects can search across a user's entire session space
    via cross_session=True, this returns any available session to serve as
    the retrieval entry point.

    Prefers client.list_sessions(user_id=...) / client.get_session(...) because
    the SDK User object does not expose list_sessions / get_session directly.

    Args:
        user: Couchbase Agent Memory user object.
        client: Optional AgentMemoryClient instance (preferred code path).
        user_id: Guest user ID string required when client is provided.

    Returns:
        A session object for the user, or None if no sessions exist.
    """
    # list_users() returns agentmemory.models.User (Pydantic, no methods).
    # get_user() returns the live User object that has list_sessions/get_session.
    # Always resolve through the client when available.
    if client is not None and user_id:
        try:
            live_user = client.get_user(user_id=user_id)
            sessions_result = live_user.list_sessions()
            session_list = getattr(sessions_result, "sessions", None) or []
            if not session_list:
                return None
            first = session_list[-1]
            first_session_id = first if isinstance(first, str) else first.session_id
            return live_user.get_session(session_id=first_session_id)
        except Exception as exc:
            print(f"warning: could not retrieve user session via client — {exc}")
            return None

    # Fallback: user may already be the live object (e.g. passed from get_user())
    try:
        sessions_result = user.list_sessions()
        session_list = getattr(sessions_result, "sessions", None) or []
        if not session_list:
            return None
        first = session_list[-1]
        first_session_id = first if isinstance(first, str) else first.session_id
        return user.get_session(session_id=first_session_id)
    except Exception as exc:
        print(f"warning: could not retrieve user session — {exc}")
        return None
