"""VectorRetriever (v1) — OpenAI dense 임베딩 단독 검색.

Retriever 인터페이스 구현. 랭킹은 임베딩 유사도, 하드 필터(시간/자격)는
to_chroma_where로 변환해 항상 적용한다. 부족하면 동일 인터페이스의
HybridRetriever(v2)로 교체한다.
embedder/vectorstore는 주입식 → 외부 의존성 없이 테스트 가능.
"""

from __future__ import annotations

from sejong_rag.index.build_index import Embedder, VectorStore
from sejong_rag.models import Candidate
from sejong_rag.retrieve.filters import to_chroma_where
from sejong_rag.retrieve.retriever import RetrievalFilter, Retriever


class VectorRetriever(Retriever):
    def __init__(self, embedder: Embedder, vectorstore: VectorStore):
        self.embedder = embedder
        self.vectorstore = vectorstore

    def search(
        self, query: str, filters: RetrievalFilter | None = None, top_k: int = 8
    ) -> list[Candidate]:
        if not query.strip():
            return []
        embedding = self.embedder.embed([query])[0]
        where = to_chroma_where(filters)
        return self.vectorstore.query(embedding, where=where, n_results=top_k)
