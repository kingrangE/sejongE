"""의존성 — orchestrator/세션 스토어 싱글톤. 테스트는 dependency_overrides로 교체."""

from __future__ import annotations

from functools import lru_cache

from sejong_rag.agent.orchestrator import Orchestrator
from sejong_rag.api.session import SessionStore


@lru_cache
def get_session_store() -> SessionStore:
    return SessionStore()


@lru_cache
def get_orchestrator() -> Orchestrator:
    # 지연 빌드: 실제 호출 시점에만 OpenAI/Chroma가 필요
    from sejong_rag.agent.factory import build_orchestrator

    return build_orchestrator()
