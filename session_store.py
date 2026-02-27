from __future__ import annotations

from typing import Dict

from .models import UserSession


class SessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[int, UserSession] = {}

    def get(self, user_id: int) -> UserSession:
        if user_id not in self._sessions:
            self._sessions[user_id] = UserSession(user_id=user_id)
        return self._sessions[user_id]

    def reset(self, user_id: int) -> UserSession:
        self._sessions[user_id] = UserSession(user_id=user_id)
        return self._sessions[user_id]


session_store = SessionStore()

