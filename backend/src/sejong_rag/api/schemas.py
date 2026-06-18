"""API 요청/응답 스키마."""

from __future__ import annotations

from pydantic import BaseModel, Field

from sejong_rag.models import ConversationProfile


class ChatTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    # 프로필·대화기록 모두 클라이언트(localStorage/메모리)가 보관·전송 → 백엔드 무상태.
    profile: ConversationProfile | None = None
    history: list[ChatTurn] = Field(default_factory=list)
