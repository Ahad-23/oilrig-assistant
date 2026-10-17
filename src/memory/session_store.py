"""
Private User Session Memory Store.

Manages conversational state isolated strictly by user_id and session_id.
Ensures that discussed entities and conversational context from one user
are completely inaccessible to any other user.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone


class SessionStore:
    """In-memory thread-safe store for user session conversational history and entity tracking."""

    _instance: Optional["SessionStore"] = None

    def __init__(self):
        # Keyed by f"{user_id}:{session_id}"
        self._sessions: Dict[str, List[Dict[str, Any]]] = {}

    @classmethod
    def get_instance(cls) -> "SessionStore":
        if cls._instance is None:
            cls._instance = SessionStore()
        return cls._instance

    def _make_key(self, user_id: str, session_id: str) -> str:
        return f"{user_id}:{session_id}"

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
        """Records a completed conversational turn partitioned by user_id and session_id."""
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

    def get_discussed_assets(
        self,
        user_id: str,
        session_id: str,
        limit_turns: int = 5
    ) -> List[str]:
        """
        Retrieves assets mentioned in the user's prior conversation turns within the session.
        Returns an empty list if no earlier conversation exists for this user_id.
        """
        key = self._make_key(user_id, session_id)
        turns = self._sessions.get(key, [])
        if not turns:
            return []

        # Collect unique assets in reverse chronological order
        assets: List[str] = []
        for turn in reversed(turns[-limit_turns:]):
            for asset in turn.get("discussed_assets", []):
                if asset not in assets:
                    assets.append(asset)
        return assets

    def has_prior_conversation(self, user_id: str, session_id: str) -> bool:
        """Returns True if the user has an existing conversation thread."""
        key = self._make_key(user_id, session_id)
        return bool(self._sessions.get(key))

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

    def clear_user_sessions(self, user_id: str) -> None:
        """Clears all session keys belonging to a user."""
        prefix = f"{user_id}:"
        keys_to_delete = [k for k in self._sessions if k.startswith(prefix)]
        for k in keys_to_delete:
            del self._sessions[k]
