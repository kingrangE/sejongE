"""라우터: 의도 분류 + 시간/자격 필터 추출."""

from datetime import date

from sejong_rag.models import ConversationProfile, DocType, Intent
from sejong_rag.retrieve.router import classify_intent, route
from sejong_rag.time_utils import epoch_day

AS_OF = date(2026, 6, 18)


def test_classify_intent():
    assert classify_intent("지금 신청 가능한 비교과 알려줘") is Intent.BIGYOGWA
    assert classify_intent("이번 주 학사일정 뭐 있어?") is Intent.CALENDAR
    assert classify_intent("자연어처리 연구실 추천해줘") is Intent.LAB
    assert classify_intent("안녕?") is Intent.SMALLTALK


def test_route_bigyogwa_open_now():
    r = route("지금 신청 가능한 비교과", as_of=AS_OF)
    assert r.intent is Intent.BIGYOGWA
    assert r.filters.doc_type is DocType.BIGYOGWA
    assert r.needs_open is True
    assert r.filters.only_open is True
    assert r.filters.as_of_epoch == epoch_day(AS_OF)


def test_route_bigyogwa_without_open_cue():
    r = route("비교과 프로그램 뭐 있어?", as_of=AS_OF)
    assert r.intent is Intent.BIGYOGWA
    assert r.filters.only_open is False
    assert r.filters.as_of_epoch is None


def test_route_calendar_this_week():
    r = route("이번 주 시험 일정 있어?", as_of=AS_OF)
    assert r.intent is Intent.CALENDAR
    assert r.filters.doc_type is DocType.CALENDAR
    assert r.filters.date_gte == epoch_day(date(2026, 6, 15))
    assert r.filters.date_lte == epoch_day(date(2026, 6, 21))


def test_route_lab_uses_profile_major():
    r = route("연구실 추천", profile=ConversationProfile(major="컴퓨터공학과"), as_of=AS_OF)
    assert r.intent is Intent.LAB
    assert r.filters.major == "컴퓨터공학과"
