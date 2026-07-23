"""Lazy-initialised agentc Catalog singleton for hotel activity tracing."""

from __future__ import annotations

import os

_catalog = None
_init_attempted = False


def get_catalog():
    """Return the shared agentc Catalog, or None if env vars are missing or init fails."""
    global _catalog, _init_attempted
    if _init_attempted:
        return _catalog

    _init_attempted = True

    conn_string = os.getenv("AGENT_CATALOG_CONN_STRING")
    if not conn_string:
        print("[agentc] AGENT_CATALOG_CONN_STRING not set — tracing disabled")
        return None

    cert_path = os.getenv("AGENT_CATALOG_CONN_ROOT_CERTIFICATE")
    if cert_path and not os.path.isabs(cert_path):
        # Resolve relative cert path from the directory containing this file,
        # then fall back to cwd (where streamlit was launched).
        here = os.path.dirname(os.path.abspath(__file__))
        candidate = os.path.join(os.path.dirname(here), cert_path)
        if os.path.exists(candidate):
            cert_path = candidate
        else:
            cwd_candidate = os.path.join(os.getcwd(), cert_path)
            if os.path.exists(cwd_candidate):
                cert_path = cwd_candidate
        print(f"[agentc] resolved cert path: {cert_path}")

    try:
        import agentc

        _catalog = agentc.Catalog(
            conn_string=conn_string,
            username=os.getenv("AGENT_CATALOG_USERNAME"),
            password=os.getenv("AGENT_CATALOG_PASSWORD"),
            bucket=os.getenv("AGENT_CATALOG_BUCKET"),
            conn_root_certificate=cert_path,
        )
        print("[agentc] catalog initialised")
        return _catalog
    except Exception as exc:
        print(f"[agentc] catalog init failed — tracing disabled: {exc}")
        import traceback

        traceback.print_exc()
        return None
