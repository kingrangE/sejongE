"""LLM 래퍼. Claude를 기본으로 하되 인터페이스로 추상화(교체·테스트 용이).

anthropic SDK는 지연 import → 키/패키지 없이도 모듈 로드 가능.
"""

from __future__ import annotations

from typing import Protocol

from sejong_rag.config import Settings, get_settings


class LLMClient(Protocol):
    def generate(self, system: str, user: str) -> str: ...


class ClaudeClient:
    def __init__(self, settings: Settings | None = None, *, max_tokens: int = 1024):
        self.settings = settings or get_settings()
        self.max_tokens = max_tokens
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from anthropic import Anthropic  # 지연 import

            if not self.settings.anthropic_api_key:
                raise RuntimeError("ANTHROPIC_API_KEY가 설정되지 않았습니다 (.env 확인).")
            self._client = Anthropic(api_key=self.settings.anthropic_api_key)
        return self._client

    def generate(self, system: str, user: str) -> str:
        resp = self.client.messages.create(
            model=self.settings.llm_model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return "\n".join(parts).strip()
