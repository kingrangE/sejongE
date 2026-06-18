"""HybridRetriever (v2) — dense + BM25를 RRF로 융합.

Vector(v1)와 동일한 Retriever 인터페이스라 drop-in 교체된다. 하드 필터는 두 검색기 모두 적용.
RRF(Reciprocal Rank Fusion): 점수 스케일이 다른 두 랭킹을 정규화 없이 결합한다.
"""

from __future__ import annotations

from sejong_rag.models import Candidate
from sejong_rag.retrieve.retriever import RetrievalFilter, Retriever


class HybridRetriever(Retriever):
    def __init__(self, dense: Retriever, sparse: Retriever, *, rrf_k: int = 60, pool: int = 20):
        self.dense = dense
        self.sparse = sparse
        self.rrf_k = rrf_k
        self.pool = pool

    def search(self, query: str, filters: RetrievalFilter | None = None, top_k: int = 8) -> list[Candidate]:
        dense = self.dense.search(query, filters, top_k=self.pool)
        sparse = self.sparse.search(query, filters, top_k=self.pool)

        rrf: dict[str, float] = {}
        cand: dict[str, Candidate] = {}
        for ranking in (dense, sparse):
            for rank, c in enumerate(ranking):
                rrf[c.id] = rrf.get(c.id, 0.0) + 1.0 / (self.rrf_k + rank + 1)
                cand.setdefault(c.id, c)

        ordered = sorted(rrf, key=lambda i: rrf[i], reverse=True)[:top_k]
        out = []
        for i in ordered:
            c = cand[i].model_copy(update={"score": round(rrf[i], 6)})
            out.append(c)
        return out
