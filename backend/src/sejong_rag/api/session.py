"""세션 한정 대화 상태 — 로그인 없이 session_id로 프로필 보관(메모리, MVP).

프로세스 메모리에만 둔다(DB 없음). 다중 프로세스/영속이 필요해지면 Redis 등으로 교체.
"""

from __future__ import annotations

import uuid

from sejong_rag.models import ConversationProfile


class SessionStore:
    def __init__(self) -> None:
        self._profiles: dict[str, ConversationProfile] = {}

    def get_or_create(self, session_id: str | None) -> tuple[str, ConversationProfile]:
        if session_id and session_id in self._profiles:
            return session_id, self._profiles[session_id]
        new_id = session_id or uuid.uuid4().hex
        profile = ConversationProfile()
        self._profiles[new_id] = profile
        return new_id, profile

    def set(self, session_id: str, profile: ConversationProfile) -> None:
        self._profiles[session_id] = profile
