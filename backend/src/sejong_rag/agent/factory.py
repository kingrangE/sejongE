"""실제 의존성으로 Orchestrator를 조립한다(OpenAI + Chroma + Claude).

CLI와 평가 스크립트가 공유한다. 구성요소는 지연 초기화라 키 없이 import/생성은 되고,
실제 호출 시점에만 키가 필요하다.
"""

from __future__ import annotations

from sejong_rag.agent.llm import OpenAIChatClient
from sejong_rag.agent.orchestrator import Orchestrator
from sejong_rag.config import Settings, get_settings
from sejong_rag.index.embedder import OpenAIEmbedder
from sejong_rag.index.vectorstore import ChromaVectorStore
from sejong_rag.retrieve.filters import doc_to_metadata
from sejong_rag.retrieve.retriever import Retriever
from sejong_rag.retrieve.vector import VectorRetriever


def load_sparse_corpus(settings: Settings) -> list[dict]:
    """SQLite 활성 문서 → BM25 코퍼스(문서별 텍스트 + 메타데이터)."""
    from sejong_rag.index.store import DocumentStore
    from sejong_rag.models import BigyogwaProgram, CalendarEvent, LabDoc

    models = {"bigyogwa": BigyogwaProgram, "calendar": CalendarEvent, "labs": LabDoc}
    store = DocumentStore(settings.sqlite_path)
    try:
        corpus = []
        for site, model in models.items():
            for payload in store.active_payloads(site):
                doc = model(**payload)
                corpus.append({
                    "id": doc.id,
                    "text": doc.embedding_text,
                    "doc_type": doc.doc_type.value,
                    "source_url": doc.source_url,
                    "modality": doc.modality.value,
                    "metadata": doc_to_metadata(doc),
                })
        return corpus
    finally:
        store.close()


def build_retriever(settings: Settings, *, hybrid: bool = False) -> Retriever:
    dense = VectorRetriever(OpenAIEmbedder(settings), ChromaVectorStore(settings))
    if not hybrid:
        return dense
    # v2: dense + BM25(키위 선택) RRF 융합
    from sejong_rag.retrieve.bm25 import BM25Retriever
    from sejong_rag.retrieve.hybrid import HybridRetriever
    from sejong_rag.retrieve.tokenize import get_tokenizer

    sparse = BM25Retriever(load_sparse_corpus(settings), get_tokenizer())
    return HybridRetriever(dense, sparse)


def build_orchestrator(settings: Settings | None = None, *, hybrid: bool = False) -> Orchestrator:
    """기본 조립: 임베딩·생성 모두 OpenAI (Chroma 색인). hybrid=True면 v2 검색."""
    settings = settings or get_settings()
    return Orchestrator(build_retriever(settings, hybrid=hybrid), OpenAIChatClient(settings))
