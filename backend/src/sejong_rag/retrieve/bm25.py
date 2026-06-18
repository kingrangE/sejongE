"""BM25 희소 검색 (순수 파이썬 — 외부 의존성 없음).

BM25Okapi 점수식. 한국어 토큰화는 tokenize.get_tokenizer()(키위 선택)에 위임.
하드 필터는 passes_filter로 후보 단계에서 적용한다.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Callable

from sejong_rag.models import Candidate, DocType, Modality
from sejong_rag.retrieve.filters import passes_filter
from sejong_rag.retrieve.retriever import RetrievalFilter, Retriever


class BM25:
    def __init__(self, corpus_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = corpus_tokens
        self.N = len(corpus_tokens)
        self.doc_len = [len(d) for d in corpus_tokens]
        self.avgdl = (sum(self.doc_len) / self.N) if self.N else 0.0
        self.tf = [Counter(d) for d in corpus_tokens]
        df: Counter = Counter()
        for d in corpus_tokens:
            df.update(set(d))
        # BM25 idf (음수 방지를 위해 +1 평활화)
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    def scores(self, query_tokens: list[str]) -> list[float]:
        q = [t for t in query_tokens if t in self.idf]
        out = [0.0] * self.N
        for i in range(self.N):
            if not self.doc_len[i]:
                continue
            denom_norm = self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avgdl)
            s = 0.0
            tf_i = self.tf[i]
            for t in q:
                f = tf_i.get(t, 0)
                if f:
                    s += self.idf[t] * (f * (self.k1 + 1)) / (f + denom_norm)
            out[i] = s
        return out


class BM25Retriever(Retriever):
    def __init__(self, docs: list[dict], tokenizer: Callable[[str], list[str]]):
        """docs: {id, text, doc_type, source_url, modality, metadata} 리스트."""
        self.docs = docs
        self.tokenizer = tokenizer
        self.bm25 = BM25([tokenizer(d["text"]) for d in docs])

    def search(self, query: str, filters: RetrievalFilter | None = None, top_k: int = 8) -> list[Candidate]:
        if not query.strip() or not self.docs:
            return []
        scores = self.bm25.scores(self.tokenizer(query))
        order = sorted(range(len(self.docs)), key=lambda i: scores[i], reverse=True)
        out: list[Candidate] = []
        for i in order:
            if scores[i] <= 0:
                break
            d = self.docs[i]
            if not passes_filter(d["metadata"], filters):
                continue
            out.append(
                Candidate(
                    id=d["id"],
                    score=float(scores[i]),
                    doc_type=DocType(d["doc_type"]),
                    text=d["text"],
                    source_url=d["source_url"],
                    modality=Modality(d.get("modality", "text")),
                    metadata=d["metadata"],
                )
            )
            if len(out) >= top_k:
                break
        return out
