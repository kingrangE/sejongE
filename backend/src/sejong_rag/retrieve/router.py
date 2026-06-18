"""질의 라우팅 — 의도 분류 + 시간/자격 필터 추출.

결정론적(규칙 기반)으로 구현해 테스트·재현이 쉽고 비용이 없다(엔지니어링 원칙: 결정론).
의도별로 적절한 RetrievalFilter를 만든다. 시점 표현은 time_utils로 해석한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from sejong_rag.models import ConversationProfile, DocType, Intent
from sejong_rag.retrieve.retriever import RetrievalFilter
from sejong_rag.time_utils import epoch_day, resolve_relative, today_kst

# 의도별 키워드 (가장 구체적인 것부터)
_LAB_KW = ("연구실", "교수님", "교수", "연구", "랩실", "랩", "지도교수", "전공 공부")
_BIGYOGWA_KW = ("비교과", "프로그램", "신청", "특강", "멘토링", "공모전", "마일리지", "두드림", "부트캠프")
_CALENDAR_KW = ("일정", "언제", "행사", "시험", "수강신청", "방학", "개강", "등록", "성적", "휴일", "축제")

_OPEN_CUES = ("지금", "현재", "신청 가능", "신청가능", "접수중", "신청할 수 있", "오늘 기준")
_GRADE_CUE = re.compile(r"(\d)\s*학년")
_MY_CUE = ("내가", "제가", "나에게", "저에게", "내", "제")

# 인사/잡담/메타 — 검색 없이 안내로 응대
_GREETING = ("안녕", "반가", "하이", "ㅎㅇ", "고마", "감사", "잘가", "잘 가", "바이",
             "누구야", "누구니", "뭐야 너", "뭐할", "뭐 할", "도움말", "사용법", "테스트")

# 프로필 자체에 대한 질문 (예: "내 관심사가 뭐야?", "내 전공 알려줘", "프로필 보여줘")
_PROFILE_FIELDS = ("관심", "전공", "학년", "프로필", "내 정보", "내정보")
_PROFILE_POSSESSIVE = ("내", "제", "나", "저")
_PROFILE_ASK = ("뭐", "무엇", "알려", "보여", "확인", "뭔", "머")


def _is_profile_query(query: str) -> bool:
    q = query.replace(" ", "")
    if "프로필" in q:
        return True
    has_field = any(f.replace(" ", "") in q for f in _PROFILE_FIELDS)
    has_poss = any(p in q for p in _PROFILE_POSSESSIVE)
    asks = any(a in q for a in _PROFILE_ASK) or "?" in query
    return has_field and has_poss and asks


@dataclass
class Routed:
    intent: Intent
    filters: RetrievalFilter
    needs_open: bool
    as_of: date


def _is_greeting(query: str) -> bool:
    q = query.replace(" ", "")
    return any(g.replace(" ", "") in q for g in _GREETING)


def classify_intent(query: str) -> Intent:
    q = query.replace(" ", "")
    scores = {
        Intent.LAB: sum(k.replace(" ", "") in q for k in _LAB_KW),
        Intent.BIGYOGWA: sum(k.replace(" ", "") in q for k in _BIGYOGWA_KW),
        Intent.CALENDAR: sum(k.replace(" ", "") in q for k in _CALENDAR_KW),
    }
    best = max(scores, key=lambda k: scores[k])
    if scores[best] > 0:
        return best  # 도메인 키워드 우선(예: "내 전공 연구실 뭐있어"는 연구실 검색)
    if _is_profile_query(query):
        return Intent.PROFILE
    # 인사/잡담은 SMALLTALK, 그 외 내용 질문은 전 도메인 통합 검색
    return Intent.SMALLTALK if _is_greeting(query) else Intent.GENERAL


def route(query: str, profile: ConversationProfile | None = None, as_of: date | None = None) -> Routed:
    as_of = as_of or today_kst()
    profile = profile or ConversationProfile()
    intent = classify_intent(query)
    f = RetrievalFilter()
    needs_open = False

    if intent is Intent.BIGYOGWA:
        f.doc_type = DocType.BIGYOGWA
        if any(c in query for c in _OPEN_CUES):
            needs_open = True
            f.only_open = True
            f.as_of_epoch = epoch_day(as_of)
        # 자격 하드 필터: 학년은 메타데이터 플래그로 질의 시 필터링한다(filters.py).
        # 전공은 표기 흔들림이 커 v1에선 하드필터하지 않고 랭킹에 맡긴다.
        if profile.grade is not None:
            f.grade = profile.grade
        if profile.major:
            f.major = profile.major

    elif intent is Intent.CALENDAR:
        f.doc_type = DocType.CALENDAR
        rng = resolve_relative(query, as_of)
        if rng is not None:
            f.date_gte = rng.start_epoch_day
            f.date_lte = rng.end_epoch_day

    elif intent is Intent.LAB:
        f.doc_type = DocType.LAB
        if profile.major:
            f.major = profile.major

    return Routed(intent=intent, filters=f, needs_open=needs_open, as_of=as_of)
