"""핵심 데이터 스키마.

- ContentUnit: 콘텐츠 유형별 추출 결과(임베딩 직전 공통 형태).
- LabDoc / CalendarEvent / BigyogwaProgram: 도메인 문서.
- ConversationProfile: 로그인 없는 세션 한정 사용자 프로필.
- Candidate: 검색 결과 한 건.
모든 날짜성 필터 필드는 epoch-day(int)를 병행 저장한다(time_utils.epoch_day).
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# 열거형
# --------------------------------------------------------------------------- #
class Modality(str, Enum):
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"
    PDF = "pdf"


class DocType(str, Enum):
    LAB = "lab"
    CALENDAR = "calendar"
    BIGYOGWA = "bigyogwa"


class Intent(str, Enum):
    LAB = "lab"
    CALENDAR = "calendar"
    BIGYOGWA = "bigyogwa"
    CLARIFY = "clarify"
    SMALLTALK = "smalltalk"


class ProgramStatus(str, Enum):
    UPCOMING = "upcoming"  # 신청 시작 전
    OPEN = "open"  # 신청 가능
    CLOSED = "closed"  # 마감


def compute_status(apply_start_epoch: int | None, apply_end_epoch: int | None, as_of_epoch: int) -> ProgramStatus:
    """질의 시점(as_of) 기준으로 비교과 신청 상태를 재계산한다."""
    if apply_start_epoch is not None and as_of_epoch < apply_start_epoch:
        return ProgramStatus.UPCOMING
    if apply_end_epoch is not None and as_of_epoch > apply_end_epoch:
        return ProgramStatus.CLOSED
    return ProgramStatus.OPEN


# --------------------------------------------------------------------------- #
# 콘텐츠 추출 단위 (유형별 추출 → 공통 형태)
# --------------------------------------------------------------------------- #
class ContentUnit(BaseModel):
    """페이지 한 블록을 유형별로 추출한 결과. 임베딩 입력은 embedding_text."""

    modality: Modality
    embedding_text: str
    # 표/이미지에서 뽑아낸 구조 필드(도메인 파서가 스키마로 승격)
    structured_fields: dict[str, str] = Field(default_factory=dict)
    # 원본 참조: 이미지 URL, 마크다운 표 등 (출처 인용용)
    original_ref: str | None = None


# --------------------------------------------------------------------------- #
# 공통 문서 베이스
# --------------------------------------------------------------------------- #
class BaseDoc(BaseModel):
    id: str  # 정규 URL(+키) 기반 안정 해시
    doc_type: DocType
    source_url: str
    source_site: str
    crawled_at: str  # ISO8601 (KST)
    content_hash: str  # 정규화 텍스트 sha256 (변경 감지)
    is_active: bool = True  # 소스에서 사라지면 False (소프트 삭제)
    raw_text: str = ""
    text: str = ""  # 정규화된 본문
    lang: str = "ko"
    embedding_text: str = ""  # 임베딩에 실제 투입되는 텍스트
    modality: Modality = Modality.TEXT
    original_ref: str | None = None


class LabDoc(BaseDoc):
    doc_type: DocType = DocType.LAB
    lab_name: str = ""
    professor_name: str = ""
    department: str = ""
    college: str = ""
    research_areas: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    recruiting: bool | None = None
    homepage_url: str | None = None


class CalendarEvent(BaseDoc):
    doc_type: DocType = DocType.CALENDAR
    title: str = ""
    start_date: date | None = None
    end_date: date | None = None
    start_epoch_day: int | None = None
    end_epoch_day: int | None = None
    semester: str = ""
    category: str = ""  # 수강/시험/등록/방학/행사
    target_grade: list[int] = Field(default_factory=list)  # 빈 리스트 = 전체
    target_audience: str = "전체"  # 학부/대학원/전체


class BigyogwaProgram(BaseDoc):
    doc_type: DocType = DocType.BIGYOGWA
    program_name: str = ""
    organizer: str = ""
    category: str = ""  # 취업/어학/멘토링/특강/공모전
    apply_start: date | None = None
    apply_end: date | None = None
    apply_start_epoch: int | None = None
    apply_end_epoch: int | None = None
    event_start: date | None = None
    event_end: date | None = None
    capacity: int | None = None
    applied_count: int | None = None
    eligibility_grade: list[int] = Field(default_factory=list)  # 빈 리스트 = 전체
    eligibility_major: list[str] = Field(default_factory=list)  # 빈 리스트 = 전체
    eligibility_note: str = ""
    mileage: int | None = None
    apply_url: str | None = None


# --------------------------------------------------------------------------- #
# 대화 프로필 (세션 한정, 로그인 없음)
# --------------------------------------------------------------------------- #
class ConversationProfile(BaseModel):
    grade: int | None = None  # 학년
    major: str | None = None  # 전공
    interests: list[str] = Field(default_factory=list)
    asked_fields: list[str] = Field(default_factory=list)  # 되물은 필드(재질문 방지)

    def missing(self, required: list[str]) -> list[str]:
        out = []
        for f in required:
            if getattr(self, f, None) in (None, [], ""):
                out.append(f)
        return out


# --------------------------------------------------------------------------- #
# 검색 결과
# --------------------------------------------------------------------------- #
class Candidate(BaseModel):
    id: str
    score: float
    doc_type: DocType
    text: str
    source_url: str
    modality: Modality = Modality.TEXT
    original_ref: str | None = None
    metadata: dict = Field(default_factory=dict)
