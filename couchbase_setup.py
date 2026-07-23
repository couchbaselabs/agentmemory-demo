"""
One-stop script for all Couchbase / Couchbase Agent Memory setup tasks:

  1. Couchbase Agent Memory client initialisation
  2. Universal LoCoMo-format data ingestion  (Shape A and Shape B JSON)
  3. Optional noise injection for retrieval-robustness demos
  4. CLI entry-point

Supported JSON shapes:
Shape A - Flat session list (elearning_demo.json style):
    Each list item is one session::

        [
          {
            "metadata": {"people": [...], "use_case": "...", ...},
            "conversation": {
              "speaker_a": "...", "speaker_b": "...",
              "session_N_date_time": "...",
              "session_N": [{"speaker": "...", "text": "..."}, ...]
            },
            "sample_id": "..."
          }, ...
        ]

Shape B - Grouped record list (locomo10.json style):
    Each list item groups ALL sessions for one conversation pair::

        [
          {
            "conversation": {
              "speaker_a": "...", "speaker_b": "...",
              "session_1": [...], "session_1_date_time": "...", ...
            },
            "qa": [...]
          }, ...
        ]

Shape is auto-detected; both are normalised to the same internal
representation before ingestion.

Usage:
::

    python couchbase_setup.py --data data/hotel_demo.json
    python couchbase_setup.py --data data/locomo10.json --max-sessions 20
    python couchbase_setup.py --data data/my_custom.json --noise --noise-count 300
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

from agentmemory import AgentMemoryClient, ChatMessage, ConflictError, NotFoundError
from dotenv import load_dotenv

load_dotenv()


# ──────────────────────────────────────────────────────────────────────────────
# Couchbase Agent Memory client
# ──────────────────────────────────────────────────────────────────────────────


def get_agentmem_client():
    """Construct and return an ``AgentMemClient`` Couchbase Agent Memory client using environment variables.

    Reads ``AGENTMEM_BASE_URL`` (default: ``http://localhost:8080``).

    Returns:
        A ready-to-use ``AgentMemClient`` instance.

    Raises:
        ImportError: If the ``agentmem`` package is not installed.
        Exception: If the client cannot be instantiated (e.g. connection refused).
    """
    base_url = os.getenv("AGENTMEM_BASE_URL", "http://localhost:8080")
    return AgentMemoryClient(base_url=base_url, timeout=60.0, verify=False)


# ──────────────────────────────────────────────────────────────────────────────
# Internal normalisation helpers
# ──────────────────────────────────────────────────────────────────────────────


def _session_keys(d: dict) -> list[str]:
    """Extract and sort ``session_N`` keys from a conversation dict.

    Args:
        d: A conversation dictionary that may contain keys like
            ``session_1``, ``session_2``, etc.

    Returns:
        Keys matching ``session_N``, sorted numerically by ``N``.
    """
    pat = re.compile(r"^session_(\d+)$")
    keys = [k for k in d if pat.match(k)]
    keys.sort(key=lambda k: int(pat.match(k).group(1)))
    return keys


def _build_messages(turns: list[dict], speaker_a: str, speaker_b: str) -> list:
    """Convert a LoCoMo turn list into a list of ``ChatMessage`` objects.

    ``speaker_a`` turns become ``user_content``; ``speaker_b`` turns become
    ``assistant_content``. Consecutive turns by the same speaker are merged.

    Args:
        turns: Raw turn list, each item ``{"speaker": str, "text": str}``.
        speaker_a: The primary speaker (maps to ``user_content``).
        speaker_b: The secondary speaker (maps to ``assistant_content``).

    Returns:
        Paired ``ChatMessage`` objects ready for ``session.add_memory()``.
        Empty list if no valid turns exist.
    """
    valid = [t for t in turns if isinstance(t, dict) and t.get("text", "").strip()]
    messages: list = []
    i = 0
    while i < len(valid):
        turn = valid[i]
        if turn["speaker"] == speaker_a:
            user_text = turn["text"].strip()
            assistant_text = ""
            for j in range(i + 1, len(valid)):
                if valid[j]["speaker"] == speaker_b:
                    assistant_text = valid[j]["text"].strip()
                    break
            if not assistant_text:
                # SDK requires non-empty assistant_content; skip orphan
                # speaker_a turns that have no following speaker_b reply.
                i += 1
                continue
            messages.append(
                ChatMessage(
                    user_content=f"{speaker_a}: {user_text}",
                    assistant_content=f"{speaker_b}: {assistant_text}",
                )
            )
        i += 1
    return messages


def _normalise_flat(records: list[dict]) -> list[dict]:
    """Normalise a Shape-A (flat session list) dataset into the internal format.

    Each record in ``records`` is expected to be one session with a
    ``conversation`` and optional ``metadata`` key.

    Args:
        records: Raw records from a Shape-A JSON file.

    Returns:
        Normalised session dicts, each with keys: ``speaker_a``,
        ``speaker_b``, ``session_key``, ``timestamp``, ``turns``,
        ``metadata``, ``sample_id``.
    """
    sessions: list[dict] = []
    for rec in records:
        conv = rec.get("conversation", {})
        meta = rec.get("metadata", {})
        speaker_a = conv.get("speaker_a", "Speaker A")
        speaker_b = conv.get("speaker_b", "Speaker B")
        for key in _session_keys(conv):
            sessions.append(
                {
                    "speaker_a": speaker_a,
                    "speaker_b": speaker_b,
                    "session_key": key,
                    "timestamp": conv.get(f"{key}_date_time", ""),
                    "turns": conv.get(key, []),
                    "metadata": meta,
                    "sample_id": rec.get("sample_id", ""),
                }
            )
    return sessions


def _normalise_grouped(records: list[dict]) -> list[dict]:
    """Normalise a Shape-B (grouped record list) dataset into the internal format.

    Each record in ``records`` groups all sessions for one conversation pair.

    Args:
        records: Raw records from a Shape-B JSON file (e.g. ``locomo10.json``).

    Returns:
        Normalised session dicts with the same schema as
        :func:`_normalise_flat`.
    """
    sessions: list[dict] = []
    for idx, rec in enumerate(records):
        conv = rec.get("conversation", {})
        speaker_a = conv.get("speaker_a", "Speaker A")
        speaker_b = conv.get("speaker_b", "Speaker B")
        sample_id = rec.get("sample_id", f"conv-{idx + 1}")
        for key in _session_keys(conv):
            sessions.append(
                {
                    "speaker_a": speaker_a,
                    "speaker_b": speaker_b,
                    "session_key": key,
                    "timestamp": conv.get(f"{key}_date_time", ""),
                    "turns": conv.get(key, []),
                    "metadata": {},
                    "sample_id": sample_id,
                }
            )
    return sessions


def _detect_and_normalise(data: list[dict]) -> list[dict]:
    """Auto-detect the JSON shape and delegate to the appropriate normaliser.

    Detection heuristic: if the first record has a ``"metadata"`` key, or
    its ``"conversation"`` contains exactly one session key, it is treated
    as Shape A (flat). Otherwise Shape B (grouped).

    Args:
        data: Parsed JSON content (top-level list).

    Returns:
        Normalised session dicts ready for ingestion. Empty list if
        ``data`` is empty.
    """
    if not data:
        return []
    first = data[0]
    conv = first.get("conversation", {})
    has_metadata = "metadata" in first
    session_count_in_first = len(_session_keys(conv))
    is_flat = has_metadata or session_count_in_first <= 1
    return _normalise_flat(data) if is_flat else _normalise_grouped(data)


# ──────────────────────────────────────────────────────────────────────────────
# Universal ingester
# ──────────────────────────────────────────────────────────────────────────────


class UniversalIngester:
    """Ingest any LoCoMo-format JSON dataset into Couchbase Agent Memory / Couchbase.

    One Couchbase Agent Memory ``user`` is created per unique ``speaker_a`` name.
    All of that speaker's records are scoped under that single user, with
    sessions numbered ``session_1``, ``session_2``, ... in source order.

    Ingestion is fully serial. Concurrent writes against the same user
    race on the server-side ``user.sessions`` update and silently drop
    sessions, so we process one session at a time.

    Args:
        client: An initialised Couchbase Agent Memory client (see :func:`get_agentmem_client`).
        quiet: Suppress per-session console output when ``True``.
    """

    def __init__(self, client, quiet: bool = False) -> None:
        self.client = client
        self.quiet = quiet
        self._user_cache: dict[str, object] = {}

    # ── Public ─────────────────────────────────────────────────────────────────

    def ingest_file(self, path: str | Path, max_sessions: int | None = None) -> dict:
        """Read a LoCoMo JSON file and ingest all sessions into Couchbase Agent Memory.

        Args:
            path: Filesystem path to the JSON dataset.
            max_sessions: Cap the number of sessions ingested (useful for
                test runs). ``None`` means no limit.

        Returns:
            Ingestion statistics with keys: ``"speakers"`` (int),
            ``"sessions_created"`` (int), ``"sessions_skipped"`` (int),
            ``"turns"`` (int), ``"duration_seconds"`` (float).

        Raises:
            FileNotFoundError: If ``path`` does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        start_time = time.perf_counter()

        data = json.loads(Path(path).read_text())
        if not isinstance(data, list):
            data = [data]
        sessions = _detect_and_normalise(data)
        if max_sessions is not None:
            sessions = sessions[:max_sessions]

        stats = self._ingest_sessions(sessions)

        end_time = time.perf_counter()
        stats["duration_seconds"] = end_time - start_time

        return stats

    # ── Internal ───────────────────────────────────────────────────────────────

    @staticmethod
    def _speaker_to_user_id(speaker: str) -> str:
        """Derive a stable user_id from a speaker's display name."""
        return re.sub(r"\s+", "_", speaker.lower().strip())

    def _reset_user(self, speaker: str):
        """Delete (if present) and recreate the user, mirroring locomo-add.py.

        Each run starts from a clean slate so partial state from a failed
        previous run cannot block re-ingestion.
        """
        user_id = self._speaker_to_user_id(speaker)
        try:
            self.client.get_user(user_id=user_id)
            self.client.delete_user(user_id=user_id)
            if not self.quiet:
                print(f"  ✓ Reset existing user: {speaker}")
        except NotFoundError:
            pass

        user = self.client.create_user(user_id=user_id, name=speaker)
        self._user_cache[speaker] = user
        if not self.quiet:
            print(f"  ✓ Created user: {speaker} (user_id={user_id})")
        return user

    def _ingest_sessions(self, sessions: list[dict]) -> dict:
        """Ingest normalised session dicts serially, grouped by speaker.

        Each unique ``speaker_a`` becomes one user, with all of that
        speaker's records mapped onto sequential ``session_N`` ids in
        source order.
        """
        stats = {
            "speakers": 0,
            "sessions_created": 0,
            "sessions_skipped": 0,
            "turns": 0,
        }

        # Group sessions by speaker_a, preserving source order.
        grouped: dict[str, list[dict]] = {}
        for s in sessions:
            grouped.setdefault(s["speaker_a"], []).append(s)
        stats["speakers"] = len(grouped)

        for speaker, speaker_sessions in grouped.items():
            user = self._reset_user(speaker)
            if not self.quiet:
                print(f"  Ingesting {len(speaker_sessions)} session(s) for {speaker} …")

            for idx, s in enumerate(speaker_sessions, start=1):
                speaker_b = s["speaker_b"]
                timestamp = s["timestamp"]
                turns = s["turns"]
                session_id = f"session_{idx}"

                if not isinstance(turns, list) or not turns:
                    if not self.quiet:
                        print(f"    → Skipped {session_id} (no turns)")
                    stats["sessions_skipped"] += 1
                    continue

                messages = _build_messages(turns, speaker, speaker_b)
                if not messages:
                    if not self.quiet:
                        print(f"    → Skipped {session_id} (no paired messages)")
                    stats["sessions_skipped"] += 1
                    continue

                annotations = {
                    "speaker_a": speaker,
                    "speaker_b": speaker_b,
                    "timestamp": timestamp,
                }

                try:
                    session = user.create_session(
                        session_id=session_id, annotations=annotations
                    )
                    if not self.quiet:
                        print(
                            f"    → Created session: {session_id} "
                            f"({len(messages)} message(s))"
                        )
                    session.add_memory(
                        messages=messages,
                        annotations=annotations,
                        async_processing=True,
                        context_required=True,
                    )
                    stats["sessions_created"] += 1
                    stats["turns"] += len(messages)
                except Exception as e:
                    print(
                        f"    [ERROR] {speaker} / {session_id}: {type(e).__name__}: {e}"
                    )
                    stats["sessions_skipped"] += 1

        return stats


# ──────────────────────────────────────────────────────────────────────────────
# Noise injection
# ──────────────────────────────────────────────────────────────────────────────

# Pool of synthetic hotel-guest facts used for robustness testing.
_NOISE_POOL: list[str] = [
    "Guest Alex Turner always books a king room on the 3rd floor facing the car park.",
    "Guest Maria Santos prefers twin beds with a garden view and extra pillows.",
    "Guest Raj Patel requested a connecting room for his team of 4 on every visit.",
    "Guest Fiona West always chooses the room closest to the elevator for easy access.",
    "Guest Tom Bradley books suites only when on a corporate account.",
    "Guest Yuki Tanaka prefers Japanese-style futons if available, otherwise a firm mattress.",
    "Guest Carlos Reyes always requests a room above the 10th floor with city views.",
    "Guest Priya Mehta prefers ground floor rooms due to a mobility aid.",
    "Guest Lisa Chen is vegan and requests plant-based breakfast options every morning.",
    "Guest Omar Hassan keeps halal and notifies the kitchen 48 hours in advance.",
    "Guest Sophie Dupont always orders the continental breakfast to her room at 7 AM.",
    "Guest Kwame Asante has a severe nut allergy flagged on every reservation.",
    "Guest Ingrid Berg prefers gluten-free menu items and Nordic cuisine.",
    "Guest David Kim orders room service sushi every night of his stay.",
    "Guest Paul Stone filed a noise complaint against room 412 during his March stay.",
    "Guest Rachel Green complained that the pool was too cold in February.",
    "Guest Ben Harris was unhappy with slow Wi-Fi in the conference room.",
    "Guest Nina Flores reported a broken air conditioning unit during her summer visit.",
    "Guest James Clark is a frequent returning guest and expects room upgrades.",
    "Guest Amy White books 3 nights every quarter for a business review meeting.",
    "Guest Daniel Park always uses last-minute deals from the app.",
    "Guest Sarah Johnson redeems loyalty points exclusively for spa credits.",
    "Guest Michael Brown books early-bird rates 6 months in advance.",
    "Guest Chloe Evans travels for medical conferences and needs a quiet workspace.",
    "Guest Hugo Martin visits for wine trade shows each November.",
    "Guest Mei Ling stays for tech hackathons and requires 24-hour room service.",
    "Guest Arjun Sharma stays every month for board meetings and prefers the same suite.",
    "Guest Elena Kovacs visits annually for a family reunion, booking 10 rooms.",
    "Guest Patrick O'Brien always requests late checkout at 2 PM on Sundays.",
    "Guest Nadia Osei prefers self-check-in via the kiosk and no housekeeping.",
    "Guest Liam Chen requests an early 10 AM check-in when travelling from Asia.",
    "Guest Fatima Al-Hassan arranges airport pick-up via the concierge every trip.",
    "Guest Viktor Petrov uses the business centre daily and needs a printer card.",
    "Guest Amara Diallo always books a poolside cabana for Sunday afternoons.",
    "Guest John Wu participates in the hotel's morning yoga sessions every visit.",
    "Guest Isabella Rossi requests fresh orchids in her room as a standing order.",
    "Guest Marcus Bell brings his dog and books the pet-friendly suite on floor 2.",
    "Guest Sandra Lee always leaves a 5-star review and mentions the breakfast buffet.",
    "Guest Kevin Thomas complained that the gym equipment was out of service in July.",
    "Guest Helen Park requests extra towels and a robe for two every time.",
    "Guest Mohammed Ali books the rooftop event space for client dinners quarterly.",
    "Guest Julia Roberts always requests a humidifier in winter.",
    "Guest Peter Wong prefers rooms with a bathtub rather than a shower.",
    "Guest Claudia Ferreira needs blackout curtains due to light sensitivity.",
    "Guest Dmitri Volkov requests a newspaper and espresso delivered at 6 AM.",
]


def inject_noise(session, count: int = 200, seed: int = 42) -> int:
    """Inject synthetic noise facts into a Couchbase Agent Memory session.

    Populates the session with semantically similar but irrelevant Q&A
    pairs to test hybrid-search retrieval robustness. Facts are drawn at
    random (with repetition) from :data:`_NOISE_POOL` and inserted in
    batches of 50.

    Args:
        session: The target Couchbase Agent Memory session that will receive the noise facts.
        count: Total number of noise facts to inject (default: ``200``).
        seed: Random seed for reproducibility (default: ``42``).

    Returns:
        The actual number of noise facts injected.
    """
    rng = random.Random(seed)
    facts: list[str] = []
    variations = ("", " (repeat visit)", " (confirmed)", " (verified)")
    while len(facts) < count:
        facts.append(rng.choice(_NOISE_POOL) + rng.choice(variations))

    batch_size = 50
    injected = 0
    for i in range(0, len(facts), batch_size):
        batch = facts[i : i + batch_size]
        messages = [
            ChatMessage(
                user_content="What are general guest preferences on file?",
                assistant_content=fact,
            )
            for fact in batch
        ]
        session.add_memory(
            messages=messages,
            annotations={"hotel-guest": "noise", "source": "robustness_test"},
            async_processing=False,
        )
        injected += len(batch)

    return injected


# ──────────────────────────────────────────────────────────────────────────────
# CLI entry-point
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:
    """Parse CLI arguments and orchestrate setup.

    Ingests data and optionally injects noise. This is the script
    entry-point. It is not intended to be called programmatically; use
    :class:`UniversalIngester` and :func:`inject_noise` directly instead.
    """
    parser = argparse.ArgumentParser(
        description="Couchbase Agent Memory / Couchbase Setup"
    )
    parser.add_argument(
        "--data", required=True, help="Path to LoCoMo-format JSON dataset"
    )
    parser.add_argument(
        "--max-sessions",
        type=int,
        default=None,
        help="Limit sessions ingested (useful for testing)",
    )
    parser.add_argument(
        "--noise",
        action="store_true",
        help="Inject noise facts for retrieval-robustness demo",
    )
    parser.add_argument(
        "--noise-count", type=int, default=200, help="Number of noise facts to inject"
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose output")
    args = parser.parse_args()

    print("\n=== Couchbase Agent Memory / Couchbase Setup ===\n")

    # ── Validate input ──────────────────────────────────────────────────────
    data_path = Path(args.data)
    if not data_path.exists():
        print(f"[ERROR] File not found: {data_path}")
        sys.exit(1)

    # ── Connect ─────────────────────────────────────────────────────────────
    client = get_agentmem_client()

    # ── Ingest ──────────────────────────────────────────────────────────────
    print(f"[1/2] Ingesting {data_path.name} …")
    ingester = UniversalIngester(client=client, quiet=args.quiet)
    stats = ingester.ingest_file(data_path, max_sessions=args.max_sessions)
    print(f"  → Speakers:                          {stats['speakers']}")
    print(f"  → Sessions created:                  {stats['sessions_created']}")
    print(f"  → Sessions skipped (already exist):  {stats['sessions_skipped']}")
    print(f"  → Turns ingested:                    {stats['turns']}")

    # Calculate total memories (turns) and duration
    total_memories = stats["turns"]
    duration = stats["duration_seconds"]
    print(f"\n✓ {total_memories} memories ingested in {duration:.2f} seconds")

    # ── Optional noise injection ─────────────────────────────────────────────
    if args.noise:
        print(f"\n[2/2] Injecting {args.noise_count} noise facts …")
        # Resolve the first speaker from the dataset to attach noise to.
        raw = json.loads(data_path.read_text())
        if not isinstance(raw, list):
            raw = [raw]
        sessions_meta = _detect_and_normalise(raw)
        if sessions_meta:
            first_speaker = sessions_meta[0]["speaker_a"]
            user_id = re.sub(r"\s+", "_", first_speaker.lower().strip())
            user = client.get_user(user_id=user_id)
            try:
                noise_session = user.create_session(
                    session_id="noise_session",
                    annotations={"source": "robustness_test"},
                )
            except ConflictError:
                noise_session = user.get_session(session_id="noise_session")

            injected = inject_noise(session=noise_session, count=args.noise_count)
            print(f"  → Injected {injected} noise facts.")
        else:
            print("  → No speakers found; noise injection skipped.")
    else:
        print("\n[2/2] Noise injection skipped (pass --noise to enable).")

    print("\n[DONE] Setup complete.\n")
    print("Run the Streamlit UI:")
    print("    streamlit run agentmem_hotel.py\n")


if __name__ == "__main__":
    main()
