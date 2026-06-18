"""학사일정 파서 검증 — 저장된 실제 HTML 픽스처."""

from pathlib import Path

import pytest

from sejong_rag.ingest.sites.calendar import parse_calendar
from sejong_rag.time_utils import epoch_day

FIXTURE = Path(__file__).parent / "fixtures" / "calendar_2026.html"
pytestmark = pytest.mark.skipif(not FIXTURE.exists(), reason="픽스처 없음")


def _parse():
    return parse_calendar(FIXTURE.read_text(encoding="utf-8"), 2026, "2026-06-18T00:00:00+09:00")


def test_parses_events():
    evs = _parse()
    assert len(evs) >= 30  # 한 해 학사일정 다수


def test_date_range_and_single():
    evs = _parse()
    # 범위형
    sugang = next(e for e in evs if "수강신청" in e.title)
    assert sugang.start_date < sugang.end_date
    assert sugang.start_epoch_day == epoch_day(sugang.start_date)
    assert sugang.category == "수강"
    # 단일일자
    single = next(e for e in evs if e.start_date == e.end_date)
    assert single.start_epoch_day == single.end_epoch_day


def test_semester_and_category_filled():
    evs = _parse()
    assert all(e.semester for e in evs)
    assert any(e.category == "시험" for e in evs)
    assert any(e.category == "등록" for e in evs)


def test_ids_unique_and_deterministic():
    a = _parse()
    b = _parse()
    assert [e.id for e in a] == [e.id for e in b]
    assert len({e.id for e in a}) == len(a)


def test_all_year_2026():
    evs = _parse()
    assert all(e.start_date.year == 2026 for e in evs)
