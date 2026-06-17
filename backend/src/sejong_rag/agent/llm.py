"""LLM 래퍼. 기본은 OpenAI 챗 모델이며, 인터페이스로 추상화해 교체·테스트가 쉽다.

SDK는 지연 import → 키/패키지 없이도 모듈 로드 가능.
(Claude도 동일 인터페이스로 선택 사용 가능하나 기본 경로는 OpenAI.)
"""

from __future__ import annotations

from typing import Iterator, Protocol

from sejong_rag.config import Settings, get_settings


class LLMClient(Protocol):
    def generate(self, system: str, user: str) -> str: ...

    def stream(self, system: str, user: str) -> Iterator[str]: ...


class OpenAIChatClient:
    """OpenAI 챗 모델 기반 생성기(기본). 임베딩과 동일하게 OPENAI_API_KEY 사용."""

    def __init__(self, settings: Settings | None = None, *, max_tokens: int = 2048, temperature: float | None = None):
        # temperature 기본 None: gpt-5/o-시리즈 등은 커스텀 temperature를 거부하므로 보내지 않는다.
        self.settings = settings or get_settings()
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI  # 지연 import

            if not self.settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다 (.env 확인).")
            self._client = OpenAI(api_key=self.settings.openai_api_key)
        return self._client

    def generate(self, system: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        # 신형 모델은 max_completion_tokens를 쓰고 일부 파라미터를 제한한다.
        # 우선 호환 파라미터로 호출하고, 거부되면 최소 파라미터로 재시도.
        kwargs: dict = {"model": self.settings.llm_model, "messages": messages,
                        "max_completion_tokens": self.max_tokens}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except Exception:
            resp = self.client.chat.completions.create(model=self.settings.llm_model, messages=messages)
        return (resp.choices[0].message.content or "").strip()

    def stream(self, system: str, user: str) -> Iterator[str]:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs: dict = {"model": self.settings.llm_model, "messages": messages,
                        "max_completion_tokens": self.max_tokens, "stream": True}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        try:
            stream = self.client.chat.completions.create(**kwargs)
        except Exception:
            stream = self.client.chat.completions.create(
                model=self.settings.llm_model, messages=messages, stream=True
            )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            text = getattr(delta, "content", None)
            if text:
                yield text


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
