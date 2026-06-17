"""time_utils: KST·epoch-day·상대 날짜 해석 검증 (외부 의존성 없음)."""

from datetime import date

from sejong_rag.time_utils import (
    DateRange,
    date_from_epoch_day,
    epoch_day,
    month_bounds,
    resolve_relative,
    semester_of,
    week_bounds,
)

AS_OF = date(2026, 6, 17)  # 수요일


def test_epoch_day_roundtrip():
    assert epoch_day(date(1970, 1, 1)) == 0
    d = date(2026, 6, 17)
    assert date_from_epoch_day(epoch_day(d)) == d


def test_week_bounds_monday_to_sunday():
    mon, sun = week_bounds(AS_OF)
    assert mon == date(2026, 6, 15)  # 월
    assert sun == date(2026, 6, 21)  # 일


def test_month_bounds():
    first, last = month_bounds(AS_OF)
    assert first == date(2026, 6, 1)
    assert last == date(2026, 6, 30)


def test_semester_label():
    assert semester_of(date(2026, 6, 17)) == "2026-1"
    assert semester_of(date(2026, 7, 10)) == "2026-여름"
    assert semester_of(date(2026, 10, 1)) == "2026-2"
    assert semester_of(date(2026, 1, 20)) == "2026-겨울"


def test_resolve_today():
    r = resolve_relative("지금 신청 가능한 비교과 알려줘", AS_OF)
    assert r == DateRange(AS_OF, AS_OF)


def test_resolve_this_week():
    r = resolve_relative("이번 주 시험 일정 있어?", AS_OF)
    assert r == DateRange(date(2026, 6, 15), date(2026, 6, 21))


def test_resolve_next_week():
    r = resolve_relative("다음 주에 뭐 있어?", AS_OF)
    assert r == DateRange(date(2026, 6, 22), date(2026, 6, 28))


def test_resolve_next_month():
    r = resolve_relative("다음 달 행사", AS_OF)
    assert r == DateRange(date(2026, 7, 1), date(2026, 7, 31))


def test_resolve_none_when_no_expression():
    assert resolve_relative("인공지능 연구실 추천해줘", AS_OF) is None


def test_specific_beats_generic():
    # "다음 주"가 "이번 주"보다 먼저 매칭되어야 함
    r = resolve_relative("다음 주 일정", AS_OF)
    assert r.start == date(2026, 6, 22)
