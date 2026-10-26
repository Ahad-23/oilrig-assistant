"""
Private User Session Memory Store.

Manages conversational state isolated strictly by user_id and session_id.
Ensures that discussed entities and conversational context from one user
are completely inaccessible to any other user.

Persistence: Dual-write to both in-memory cache (for low-latency reads within
the same process) and PostgreSQL `session_turns` table (for durability across
restarts and multi-worker deployments).

Cross-session lookup: When a user refers to "the wells we discussed yesterday"
in a new chat (new session_id), the store searches ALL sessions for that user,
not just the current one.
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

import asyncpg


def _safe_json_decode(val: Any, default: Any = None) -> Any:
    if val is None:
        return default
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return default
    return default


class SessionStore:
    """Hybrid in-memory + PostgreSQL store for user session conversational history."""

    _instance: Optional["SessionStore"] = None

    def __init__(self):
        # In-memory cache keyed by f"{user_id}:{session_id}"
        self._sessions: Dict[str, List[Dict[str, Any]]] = {}

    @classmethod
    def get_instance(cls) -> "SessionStore":
        if cls._instance is None:
            cls._instance = SessionStore()
        return cls._instance

    def _make_key(self, user_id: str, session_id: str) -> str:
        return f"{user_id}:{session_id}"

    # ------------------------------------------------------------------
    # Write path: in-memory + async PostgreSQL persist
    # ------------------------------------------------------------------

    def record_turn(
        self,
        user_id: str,
        session_id: str,
        user_query: str,
        narrative_response: str,
        discussed_assets: Optional[List[str]] = None,
        citations: Optional[List[Any]] = None,
        generative_ui: Optional[Dict[str, Any]] = None
    ) -> None:
        """Records a completed conversational turn in the in-memory cache."""
        key = self._make_key(user_id, session_id)
        if key not in self._sessions:
            self._sessions[key] = []

        self._sessions[key].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_query": user_query,
            "narrative_response": narrative_response,
            "discussed_assets": discussed_assets or [],
            "citations": citations or [],
            "generative_ui": generative_ui
        })

    async def record_turn_persistent(
        self,
        conn: asyncpg.Connection,
        user_id: str,
        session_id: str,
        user_query: str,
        narrative_response: str,
        discussed_assets: Optional[List[str]] = None,
        citations: Optional[List[Any]] = None,
        generative_ui: Optional[Dict[str, Any]] = None
    ) -> None:
        """Records a turn in both in-memory cache and PostgreSQL for durability."""
        # 1. In-memory write (fast path for same-process reads)
        self.record_turn(
            user_id=user_id,
            session_id=session_id,
            user_query=user_query,
            narrative_response=narrative_response,
            discussed_assets=discussed_assets,
            citations=citations,
            generative_ui=generative_ui
        )

        # 2. PostgreSQL persist (durable path)
        try:
            await conn.execute("""
                INSERT INTO session_turns (
                    user_id, session_id, user_query, narrative_response,
                    discussed_assets, citations, generative_ui
                ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb);
            """,
                user_id,
                session_id,
                user_query,
                narrative_response,
                discussed_assets or [],
                json.dumps(citations or [], default=str),
                json.dumps(generative_ui, default=str) if generative_ui else None
            )
        except Exception:
            # Non-critical: in-memory cache still works for this request
            pass

    # ------------------------------------------------------------------
    # Read path: in-memory first, PostgreSQL fallback
    # ------------------------------------------------------------------

    def get_discussed_assets(
        self,
        user_id: str,
        session_id: str,
        limit_turns: int = 5
    ) -> List[str]:
        """
        Retrieves assets mentioned in the user's prior conversation turns.

        First checks the current session_id. If empty, searches ALL sessions
        for this user_id (handles "new chat" follow-ups like Q11 Day 2).

        Returns an empty list if no earlier conversation exists for this user_id.
        """
        # Try current session first
        key = self._make_key(user_id, session_id)
        turns = self._sessions.get(key, [])
        if turns:
            return self._extract_assets_from_turns(turns, limit_turns)

        # Fall back: search ALL sessions for this user (cross-session lookup)
        return self._get_discussed_assets_all_sessions(user_id, limit_turns)

    def _get_discussed_assets_all_sessions(
        self,
        user_id: str,
        limit_turns: int = 5
    ) -> List[str]:
        """Searches all in-memory sessions for a user_id to find discussed assets."""
        prefix = f"{user_id}:"
        all_turns: List[Dict[str, Any]] = []
        for key, turns in self._sessions.items():
            if key.startswith(prefix):
                all_turns.extend(turns)

        if not all_turns:
            return []

        # Sort by timestamp descending and take most recent
        all_turns.sort(key=lambda t: t.get("timestamp", ""), reverse=True)
        return self._extract_assets_from_turns(all_turns, limit_turns)

    async def get_discussed_assets_persistent(
        self,
        conn: asyncpg.Connection,
        user_id: str,
        session_id: str,
        limit_turns: int = 5
    ) -> List[str]:
        """
        Retrieves discussed assets with PostgreSQL fallback.
        First tries in-memory (fast). If empty, queries PostgreSQL (durable).
        """
        # Try in-memory (includes cross-session lookup)
        assets = self.get_discussed_assets(user_id, session_id, limit_turns)
        if assets:
            return assets

        # PostgreSQL fallback: search all sessions for this user
        try:
            rows = await conn.fetch("""
                SELECT discussed_assets FROM session_turns
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2;
            """, user_id, limit_turns)

            all_assets: List[str] = []
            for row in rows:
                for asset in (row["discussed_assets"] or []):
                    if asset not in all_assets:
                        all_assets.append(asset)
            return all_assets
        except Exception:
            return []

    @staticmethod
    def _extract_assets_from_turns(
        turns: List[Dict[str, Any]],
        limit_turns: int
    ) -> List[str]:
        """Collects unique asset IDs from the most recent turns in reverse chronological order."""
        assets: List[str] = []
        sorted_turns = sorted(turns, key=lambda t: t.get("timestamp", ""), reverse=True)
        for turn in sorted_turns[:limit_turns]:
            for asset in turn.get("discussed_assets", []):
                if asset not in assets:
                    assets.append(asset)
        return assets

    def has_prior_conversation(self, user_id: str, session_id: str) -> bool:
        """Returns True if the user has an existing conversation in ANY session."""
        # Check current session
        key = self._make_key(user_id, session_id)
        if self._sessions.get(key):
            return True

        # Check all sessions for this user (cross-session)
        prefix = f"{user_id}:"
        return any(
            bool(turns) for key, turns in self._sessions.items()
            if key.startswith(prefix)
        )

    async def has_prior_conversation_persistent(
        self,
        conn: asyncpg.Connection,
        user_id: str,
        session_id: str
    ) -> bool:
        """Checks for prior conversations with PostgreSQL fallback."""
        if self.has_prior_conversation(user_id, session_id):
            return True

        try:
            count = await conn.fetchval("""
                SELECT COUNT(*) FROM session_turns WHERE user_id = $1;
            """, user_id)
            return count > 0
        except Exception:
            return False

    def get_recent_history(
        self,
        user_id: str,
        session_id: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Returns recent turns for the specified user and session."""
        key = self._make_key(user_id, session_id)
        turns = self._sessions.get(key, [])
        return turns[-limit:]

    async def get_recent_history_persistent(
        self,
        conn: asyncpg.Connection,
        user_id: str,
        session_id: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Returns recent turns with PostgreSQL fallback."""
        # Try in-memory first
        turns = self.get_recent_history(user_id, session_id, limit)
        if turns:
            return turns

        # PostgreSQL fallback
        try:
            rows = await conn.fetch("""
                SELECT user_query, narrative_response, created_at,
                       discussed_assets, citations, generative_ui
                FROM session_turns
                WHERE user_id = $1 AND session_id = $2
                ORDER BY created_at DESC
                LIMIT $3;
            """, user_id, session_id, limit)

            return [
                {
                    "user_query": r["user_query"],
                    "narrative_response": r["narrative_response"],
                    "timestamp": r["created_at"].isoformat() if r["created_at"] else "",
                    "discussed_assets": list(r["discussed_assets"] or []),
                    "citations": _safe_json_decode(r["citations"], default=[]),
                    "generative_ui": _safe_json_decode(r["generative_ui"], default=None)
                }
                for r in reversed(rows)  # Reverse to get chronological order
            ]
        except Exception:
            return []

    def clear_user_sessions(self, user_id: str) -> None:
        """Clears all in-memory session keys belonging to a user."""
        prefix = f"{user_id}:"
        keys_to_delete = [k for k in self._sessions if k.startswith(prefix)]
        for k in keys_to_delete:
            del self._sessions[k]

    def clear_session(self, user_id: str, session_id: str) -> None:
        """Clears a specific session."""
        key = self._make_key(user_id, session_id)
        if key in self._sessions:
            del self._sessions[key]
