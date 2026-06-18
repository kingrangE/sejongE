"""API 요청/응답 스키마."""

from __future__ import annotations

from pydantic import BaseModel, Field

from sejong_rag.models import ConversationProfile


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    # 프로필은 클라이언트(localStorage)가 보관·전송한다 → 백엔드 무상태.
    profile: ConversationProfile | None = None
