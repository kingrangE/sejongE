"""Chroma 벡터 저장소 래퍼.

- 안정 `id` 기준 upsert/delete. 메타데이터에 modality·날짜(epoch-day)·자격 등을 함께 저장.
- chromadb는 지연 import → 패키지 없이도 모듈 로드 가능.
- Qdrant 등으로 교체 가능하도록 메서드를 최소·명시적으로 유지한다.
"""

from __future__ import annotations

from sejong_rag.config import Settings, get_settings
from sejong_rag.models import Candidate, DocType, Modality

_COLLECTION = "sejong_docs"


class ChromaVectorStore:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._client = None
        self._collection = None

    @property
    def collection(self):
        if self._collection is None:
            import chromadb  # 지연 import

            self.settings.ensure_dirs()
            self._client = chromadb.PersistentClient(path=str(self.settings.chroma_dir))
            self._collection = self._client.get_or_create_collection(
                name=_COLLECTION, metadata={"hnsw:space": "cosine"}
            )
        return self._collection

    # ----------------------------------------------------------------- #
    def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        if not ids:
            return
        self.collection.upsert(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )

    def delete(self, ids: list[str]) -> None:
        if ids:
            self.collection.delete(ids=ids)

    def query(
        self, embedding: list[float], where: dict | None = None, n_results: int = 8
    ) -> list[Candidate]:
        res = self.collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where=where or None,
            include=["documents", "metadatas", "distances"],
        )
        out: list[Candidate] = []
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for i, doc_id in enumerate(ids):
            meta = metas[i] or {}
            # cosine distance → similarity 점수
            score = 1.0 - float(dists[i]) if i < len(dists) else 0.0
            out.append(
                Candidate(
                    id=doc_id,
                    score=score,
                    doc_type=DocType(meta.get("doc_type", "bigyogwa")),
                    text=docs[i] if i < len(docs) else "",
                    source_url=meta.get("source_url", ""),
                    modality=Modality(meta.get("modality", "text")),
                    original_ref=meta.get("original_ref"),
                    metadata=meta,
                )
            )
        return out
