"""대화형 프로필 추출 + 되묻기(클라리피케이션) 게이트.

로그인이 없으므로 학년·전공·관심사를 대화에서 추출하거나, 필요한데 모르면 되묻는다.
- 자발 제공("컴공 3학년") 정보는 추출해 자동 반영(재질문 방지).
- 필요한데 없을 때만 1개 질문(과잉질문 방지). 같은 필드는 다시 묻지 않는다.
v1은 규칙 기반(결정론). LLM 기반 추출은 후속 고도화 대상.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sejong_rag.models import ConversationProfile, Intent

_GRADE_RE = re.compile(r"([1-4])\s*학년")

# AI융합대학(MVP) 중심 전공 별칭 → 표준 명칭
_MAJOR_ALIASES = {
    "컴공": "컴퓨터공학과",
    "컴퓨터공학": "컴퓨터공학과",
    "소융": "소프트웨어학과",
    "소프트웨어": "소프트웨어학과",
    "인공지능": "인공지능데이터사이언스학과",
    "ai데이터사이언스": "인공지능데이터사이언스학과",
    "정보보호": "정보보호학과",
    "지능정보": "지능정보융합학과",
    "전자공학": "AI융합전자공학과",
    "반도체": "반도체시스템공학과",
}

# LAB 질의에서 주제가 빠진 모호한 표현을 걸러내기 위한 불용어
_LAB_NOISE = (
    "연구실", "교수님", "교수", "연구", "랩실", "랩", "추천", "추천해줘", "해줘",
    "해주세요", "알려줘", "알려주세요", "뭐", "무엇", "어떤", "있어", "있을까",
    "있나", "갈", "수", "가고", "싶어", "싶은데", "좀", "해보고", "하고", "하는",
    "관련", "분야", "주제", "어디", "가면", "할", "지도",
)

_MY_GRADE_CUE = ("내 학년", "제 학년", "내가 신청", "제가 신청", "나에게 맞는", "저에게 맞는", "나한테", "저한테")


@dataclass
class Clarification:
    field: str
    question: str


def extract_updates(text: str, profile: ConversationProfile) -> ConversationProfile:
    """발화에서 학년/전공을 추출해 프로필에 병합한 새 객체 반환."""
    data = profile.model_dump()
    gm = _GRADE_RE.search(text)
    if gm:
        data["grade"] = int(gm.group(1))
    low = text.replace(" ", "").lower()
    for alias, canonical in _MAJOR_ALIASES.items():
        if alias.lower() in low:
            data["major"] = canonical
            break
    return ConversationProfile(**data)


def _lab_query_has_topic(query: str) -> bool:
    stripped = query
    for w in _LAB_NOISE:
        stripped = stripped.replace(w, "")
    stripped = re.sub(r"[^\w가-힣]", "", stripped)
    return len(stripped) >= 2


def needs_clarification(
    intent: Intent, query: str, profile: ConversationProfile
) -> Clarification | None:
    """되물어야 하면 Clarification 반환, 아니면 None. 이미 물은 필드는 건너뜀."""
    if intent is Intent.LAB:
        if not profile.interests and not _lab_query_has_topic(query):
            if "interests" not in profile.asked_fields:
                return Clarification(
                    field="interests",
                    question="어떤 분야나 주제에 관심이 있으신가요? (예: 인공지능, 로봇, 자연어처리, 보안)",
                )
    if intent is Intent.BIGYOGWA:
        if profile.grade is None and any(c in query for c in _MY_GRADE_CUE):
            if "grade" not in profile.asked_fields:
                return Clarification(field="grade", question="몇 학년이신가요?")
    return None
