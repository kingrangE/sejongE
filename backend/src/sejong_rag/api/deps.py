"""의존성 — orchestrator 싱글톤. 테스트는 dependency_overrides로 교체.

프로필은 클라이언트가 보관하므로(방법 A) 서버 세션 스토어는 두지 않는다(무상태).
"""

from __future__ import annotations

from functools import lru_cache

from sejong_rag.agent.orchestrator import Orchestrator


@lru_cache
def get_orchestrator() -> Orchestrator:
    # 지연 빌드: 실제 호출 시점에만 OpenAI/Chroma가 필요
    from sejong_rag.agent.factory import build_orchestrator

    return build_orchestrator()
