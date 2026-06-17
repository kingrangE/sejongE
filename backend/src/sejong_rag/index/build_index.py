"""ETL의 Transform→Load 오케스트레이션 (멱등).

- 문서별로 변경 분류(NEW/CHANGED/UNCHANGED) → **NEW/CHANGED만 임베딩**(비용 절감).
- SQLite(진실원천)와 벡터스토어를 함께 upsert.
- 소스에서 사라진 문서는 소프트 삭제 + 벡터 삭제.
- embedder/vectorstore는 주입식(프로토콜) → OpenAI/Chroma 없이 테스트 가능.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence

from sejong_rag.index.store import ChangeKind, DocumentStore
from sejong_rag.models import BaseDoc
from sejong_rag.retrieve.filters import doc_to_metadata


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class VectorStore(Protocol):
    def upsert(
        self, ids: list[str], embeddings: list[list[float]], documents: list[str], metadatas: list[dict]
    ) -> None: ...
    def delete(self, ids: list[str]) -> None: ...
    def query(self, embedding: list[float], where: dict | None, n_results: int) -> list: ...


@dataclass
class EtlStats:
    site: str
    fetched: int = 0
    new: int = 0
    changed: int = 0
    unchanged: int = 0
    deleted: int = 0
    embedded: int = 0
    errors: int = 0
    error_ids: list[str] = field(default_factory=list)


def run_etl(
    docs: Sequence[BaseDoc],
    *,
    store: DocumentStore,
    embedder: Embedder,
    vectorstore: VectorStore,
    site: str,
    run_id: str,
    started_at: str,
    finished_at: str | None = None,
) -> EtlStats:
    """Transform된 문서들을 멱등하게 적재한다."""
    stats = EtlStats(site=site, fetched=len(docs))
    seen: list[str] = []

    # 1) NEW/CHANGED만 모아 임베딩 (배치)
    to_embed: list[BaseDoc] = []
    for doc in docs:
        seen.append(doc.id)
        kind = store.classify(doc)
        if kind is ChangeKind.NEW:
            stats.new += 1
            to_embed.append(doc)
        elif kind is ChangeKind.CHANGED:
            stats.changed += 1
            to_embed.append(doc)
        else:
            stats.unchanged += 1

    if to_embed:
        try:
            vectors = embedder.embed([d.embedding_text for d in to_embed])
            vectorstore.upsert(
                ids=[d.id for d in to_embed],
                embeddings=vectors,
                documents=[d.embedding_text for d in to_embed],
                metadatas=[doc_to_metadata(d) for d in to_embed],
            )
            stats.embedded = len(to_embed)
        except Exception:
            stats.errors += 1
            raise

    # 2) SQLite 진실원천 upsert (UNCHANGED 포함 → is_active 보장)
    for doc in docs:
        store.upsert(doc)

    # 3) 소스에서 사라진 문서 소프트 삭제 + 벡터 제거
    stale = store.deactivate_missing(site, seen)
    if stale:
        vectorstore.delete(stale)
        stats.deleted = len(stale)

    store.record_run(
        run_id, site, started_at, finished_at,
        fetched=stats.fetched, new=stats.new, changed=stats.changed,
        deleted=stats.deleted, errors=stats.errors,
    )
    return stats
