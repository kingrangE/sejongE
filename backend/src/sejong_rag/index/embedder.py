"""OpenAI 임베딩 래퍼.

- 모델/차원은 설정에서 가져온다(text-embedding-3-large, 3072).
- openai 패키지는 지연 import → 키/패키지 없이도 모듈 로드 가능.
- 비용 절감: 호출은 ETL의 NEW/CHANGED 청크에 대해서만 일어나야 한다(상위 단계 책임).
"""

from __future__ import annotations

from sejong_rag.config import Settings, get_settings


class OpenAIEmbedder:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI  # 지연 import

            if not self.settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다 (.env 확인).")
            self._client = OpenAI(api_key=self.settings.openai_api_key)
        return self._client

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = self.client.embeddings.create(
            model=self.settings.embedding_model,
            input=texts,
            dimensions=self.settings.embedding_dim,
        )
        return [d.embedding for d in resp.data]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]
