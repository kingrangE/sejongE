"""대화 오케스트레이터 — 라우팅 → 되묻기 → 검색 → 근거 기반 생성.

흐름:
 1) 발화에서 프로필(학년/전공) 자동 추출
 2) 의도 분류 + 시간/자격 필터 생성
 3) 필요한데 모르면 1개 되묻기(같은 필드 재질문 안 함)
 4) 하드 필터를 건 벡터 검색
 5) 결과 없으면 환각 대신 '없음' 응답(abstention)
 6) 검색 자료만 근거로 LLM이 인용 포함 답변 생성

retriever/llm은 주입식 → 가짜 구현으로 결정론적 테스트 가능.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from sejong_rag.agent import prompts
from sejong_rag.agent.llm import LLMClient
from sejong_rag.agent.profile import extract_updates, needs_clarification
from sejong_rag.models import Candidate, ConversationProfile, Intent
from sejong_rag.retrieve.retriever import Retriever
from sejong_rag.retrieve.router import route


def profile_answer(query: str, profile: ConversationProfile) -> str:
    """프로필 질문에 저장된 값으로 직접 답한다(검색/LLM 불필요)."""
    q = query.replace(" ", "")
    interests = ", ".join(profile.interests) if profile.interests else None
    if "관심" in q:
        return (f"현재 설정된 관심사는 **{interests}** 입니다."
                if interests else "아직 관심사가 설정되어 있지 않아요. 우측 패널에서 입력하거나 알려주세요.")
    if "전공" in q:
        return (f"현재 전공은 **{profile.major}** 로 설정되어 있어요."
                if profile.major else "아직 전공이 설정되어 있지 않아요.")
    if "학년" in q:
        return (f"현재 **{profile.grade}학년** 으로 설정되어 있어요."
                if profile.grade else "아직 학년이 설정되어 있지 않아요.")
    lines = [
        f"학년: {profile.grade}학년" if profile.grade else "학년: 미설정",
        f"전공: {profile.major}" if profile.major else "전공: 미설정",
        f"관심사: {interests}" if interests else "관심사: 미설정",
    ]
    return "현재 설정된 프로필이에요.\n\n- " + "\n- ".join(lines)


# 직전 맥락을 가리키는 참조성 후속 질문 단서
_REFERENCE_CUES = (
    "그거", "그게", "그 중", "그중", "그것", "첫번째", "첫 번째", "두번째", "두 번째",
    "세번째", "세 번째", "방금", "아까", "위에서", "저거", "이거", "그 프로그램",
    "그 연구실", "그 교수", "그분", "거기", "다시",
)


def augment_query(
    query: str, profile: ConversationProfile, intent: Intent, history: list[dict] | None = None
) -> str:
    """검색 질의를 맥락으로 보강한다.

    - 참조성 후속 질문("첫 번째 거 신청기간?", 짧은 질문)이면 직전 사용자 질문을 앞에 붙여
      검색이 이전 대화 주제를 잇게 한다.
    - 관심사를 언급했거나 연구실 의도면 저장된 관심사를 더해 관심 분야를 향하게 한다.
    """
    aug = query
    if history:
        last_user = next((t.get("content") for t in reversed(history) if t.get("role") == "user"), None)
        if last_user and (len(query.strip()) < 16 or any(c in query for c in _REFERENCE_CUES)):
            aug = f"{last_user} {query}"
    if profile.interests and ("관심" in query or intent is Intent.LAB):
        aug = f"{aug} {' '.join(profile.interests)}"
    return aug


def serialize_source(c: Candidate) -> dict:
    """UI 출처 카드용 직렬화."""
    snippet = c.text.split("\n", 1)[0][:80] if c.text else ""
    return {
        "url": c.source_url,
        "doc_type": c.doc_type.value,
        "score": round(c.score, 3),
        "snippet": snippet,
        "original_ref": c.original_ref,
    }

_ABSTAIN = {
    Intent.BIGYOGWA: "조건에 맞는 비교과 프로그램을 찾지 못했습니다.",
    Intent.CALENDAR: "해당 기간의 학사일정을 찾지 못했습니다.",
    Intent.LAB: "조건에 맞는 연구실 정보를 찾지 못했습니다.",
    Intent.GENERAL: "관련 정보를 찾지 못했습니다. 비교과·학사일정·연구실에 대해 물어봐 주세요.",
    Intent.SMALLTALK: "안녕하세요! 학사일정·비교과·연구실에 대해 무엇이든 물어봐 주세요.",
}


@dataclass
class AnswerResult:
    kind: str  # "clarify" | "answer" | "abstain"
    text: str
    intent: Intent
    profile: ConversationProfile
    sources: list[Candidate] = field(default_factory=list)


class Orchestrator:
    def __init__(self, retriever: Retriever, llm: LLMClient, *, top_k: int = 8):
        self.retriever = retriever
        self.llm = llm
        self.top_k = top_k

    def run(
        self,
        query: str,
        profile: ConversationProfile | None = None,
        history: list[dict] | None = None,
    ) -> AnswerResult:
        profile = extract_updates(query, profile or ConversationProfile())
        routed = route(query, profile)

        # 프로필 질문은 저장된 값으로 직접 답(검색/LLM 불필요)
        if routed.intent is Intent.PROFILE:
            return AnswerResult("answer", profile_answer(query, profile), routed.intent, profile)

        # smalltalk은 검색 없이 안내
        if routed.intent is Intent.SMALLTALK:
            return AnswerResult("abstain", _ABSTAIN[Intent.SMALLTALK], routed.intent, profile)

        clar = needs_clarification(routed.intent, query, profile)
        if clar is not None:
            profile = profile.model_copy(update={"asked_fields": [*profile.asked_fields, clar.field]})
            return AnswerResult("clarify", clar.question, routed.intent, profile)

        search_query = augment_query(query, profile, routed.intent, history)
        candidates = self.retriever.search(search_query, routed.filters, top_k=self.top_k)
        if not candidates:
            return AnswerResult("abstain", _ABSTAIN[routed.intent], routed.intent, profile)

        answer = self.llm.generate(
            prompts.SYSTEM_PROMPT, prompts.build_user_message(query, candidates, profile, history)
        )
        return AnswerResult("answer", answer, routed.intent, profile, sources=candidates)

    def run_stream(
        self,
        query: str,
        profile: ConversationProfile | None = None,
        history: list[dict] | None = None,
    ) -> Iterator[tuple[str, object]]:
        """SSE용 스트리밍. (event, data) 튜플을 순서대로 방출한다.

        events: meta → (clarify|abstain|(sources, delta*)) → profile → done
        clarify/abstain은 LLM을 호출하지 않아 키 없이도 동작한다.
        """
        profile = extract_updates(query, profile or ConversationProfile())
        routed = route(query, profile)
        yield ("meta", {"intent": routed.intent.value})

        if routed.intent is Intent.PROFILE:
            yield ("delta", profile_answer(query, profile))
            yield ("profile", profile.model_dump())
            yield ("done", {})
            return

        if routed.intent is Intent.SMALLTALK:
            yield ("abstain", {"text": _ABSTAIN[Intent.SMALLTALK]})
            yield ("profile", profile.model_dump())
            yield ("done", {})
            return

        clar = needs_clarification(routed.intent, query, profile)
        if clar is not None:
            profile = profile.model_copy(update={"asked_fields": [*profile.asked_fields, clar.field]})
            yield ("clarify", {"text": clar.question, "field": clar.field})
            yield ("profile", profile.model_dump())
            yield ("done", {})
            return

        search_query = augment_query(query, profile, routed.intent, history)
        candidates = self.retriever.search(search_query, routed.filters, top_k=self.top_k)
        if not candidates:
            yield ("abstain", {"text": _ABSTAIN[routed.intent]})
            yield ("profile", profile.model_dump())
            yield ("done", {})
            return

        yield ("sources", [serialize_source(c) for c in candidates])
        for token in self.llm.stream(
            prompts.SYSTEM_PROMPT, prompts.build_user_message(query, candidates, profile, history)
        ):
            yield ("delta", token)
        yield ("profile", profile.model_dump())
        yield ("done", {})
