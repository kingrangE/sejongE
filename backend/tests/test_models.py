"""models: 상태 재계산·프로필 누락 필드·문서 스키마 검증."""

from sejong_rag.models import (
    BigyogwaProgram,
    ConversationProfile,
    DocType,
    ProgramStatus,
    compute_status,
)
from sejong_rag.time_utils import epoch_day
from datetime import date


def test_compute_status_upcoming_open_closed():
    start = epoch_day(date(2026, 6, 10))
    end = epoch_day(date(2026, 6, 20))
    assert compute_status(start, end, epoch_day(date(2026, 6, 5))) == ProgramStatus.UPCOMING
    assert compute_status(start, end, epoch_day(date(2026, 6, 15))) == ProgramStatus.OPEN
    assert compute_status(start, end, epoch_day(date(2026, 6, 25))) == ProgramStatus.CLOSED


def test_compute_status_open_boundaries_inclusive():
    start = epoch_day(date(2026, 6, 10))
    end = epoch_day(date(2026, 6, 20))
    assert compute_status(start, end, start) == ProgramStatus.OPEN
    assert compute_status(start, end, end) == ProgramStatus.OPEN


def test_profile_missing_fields():
    p = ConversationProfile(grade=3)
    assert p.missing(["grade", "major"]) == ["major"]
    assert p.missing(["grade"]) == []


def test_bigyogwa_defaults_doc_type():
    prog = BigyogwaProgram(
        id="abc",
        source_url="https://example.com/1",
        source_site="bigyogwa",
        crawled_at="2026-06-17T00:00:00+09:00",
        content_hash="hash",
        program_name="AI 부트캠프",
    )
    assert prog.doc_type == DocType.BIGYOGWA
    assert prog.eligibility_grade == []  # 빈 = 전체
