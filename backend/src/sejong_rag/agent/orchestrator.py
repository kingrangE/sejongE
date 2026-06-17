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
    Intent.SMALLTALK: "죄송합니다. 학사일정·비교과·연구실 관련 질문을 도와드릴 수 있어요.",
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

    def run(self, query: str, profile: ConversationProfile | None = None) -> AnswerResult:
        profile = extract_updates(query, profile or ConversationProfile())
        routed = route(query, profile)

        # smalltalk은 검색 없이 안내
        if routed.intent is Intent.SMALLTALK:
            return AnswerResult("abstain", _ABSTAIN[Intent.SMALLTALK], routed.intent, profile)

        clar = needs_clarification(routed.intent, query, profile)
        if clar is not None:
            profile = profile.model_copy(update={"asked_fields": [*profile.asked_fields, clar.field]})
            return AnswerResult("clarify", clar.question, routed.intent, profile)

        candidates = self.retriever.search(query, routed.filters, top_k=self.top_k)
        if not candidates:
            return AnswerResult("abstain", _ABSTAIN[routed.intent], routed.intent, profile)

        answer = self.llm.generate(
            prompts.SYSTEM_PROMPT, prompts.build_user_message(query, candidates)
        )
        return AnswerResult("answer", answer, routed.intent, profile, sources=candidates)

    def run_stream(
        self, query: str, profile: ConversationProfile | None = None
    ) -> Iterator[tuple[str, object]]:
        """SSE용 스트리밍. (event, data) 튜플을 순서대로 방출한다.

        events: meta → (clarify|abstain|(sources, delta*)) → profile → done
        clarify/abstain은 LLM을 호출하지 않아 키 없이도 동작한다.
        """
        profile = extract_updates(query, profile or ConversationProfile())
        routed = route(query, profile)
        yield ("meta", {"intent": routed.intent.value})

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

        candidates = self.retriever.search(query, routed.filters, top_k=self.top_k)
        if not candidates:
            yield ("abstain", {"text": _ABSTAIN[routed.intent]})
            yield ("profile", profile.model_dump())
            yield ("done", {})
            return

        yield ("sources", [serialize_source(c) for c in candidates])
        for token in self.llm.stream(
            prompts.SYSTEM_PROMPT, prompts.build_user_message(query, candidates)
        ):
            yield ("delta", token)
        yield ("profile", profile.model_dump())
        yield ("done", {})
