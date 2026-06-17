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
from sejong_rag.retrieve.vector import VectorRetriever


def build_orchestrator(settings: Settings | None = None) -> Orchestrator:
    """기본 조립: 임베딩·생성 모두 OpenAI (Chroma 색인)."""
    settings = settings or get_settings()
    retriever = VectorRetriever(OpenAIEmbedder(settings), ChromaVectorStore(settings))
    return Orchestrator(retriever, OpenAIChatClient(settings))
