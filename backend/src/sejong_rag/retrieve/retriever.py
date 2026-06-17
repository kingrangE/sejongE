"""검색 추상 인터페이스.

v1 VectorRetriever와 v2 HybridRetriever가 이 인터페이스를 구현하여 drop-in 교체된다.
라우터/orchestrator는 구체 구현이 아니라 Retriever에만 의존한다.
하드 필터(RetrievalFilter)는 랭킹 방식과 직교하며 두 구현 모두 적용한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from sejong_rag.models import Candidate, DocType


class RetrievalFilter(BaseModel):
    """메타데이터 하드 필터. None인 필드는 제약 없음."""

    doc_type: DocType | None = None
    # 날짜 범위 겹침(epoch-day). 예: 학사일정 "이번 주"
    date_gte: int | None = None
    date_lte: int | None = None
    # 비교과 신청 가능: as_of가 신청기간 안에 들어오는지
    as_of_epoch: int | None = None
    only_open: bool = False
    # 자격
    grade: int | None = None
    major: str | None = None
    # 기타 동등 일치
    extra_eq: dict[str, str | int] = Field(default_factory=dict)


class Retriever(ABC):
    @abstractmethod
    def search(
        self, query: str, filters: RetrievalFilter | None = None, top_k: int = 8
    ) -> list[Candidate]:
        """질의와 하드 필터로 후보를 검색해 점수순으로 반환한다."""
        raise NotImplementedError
