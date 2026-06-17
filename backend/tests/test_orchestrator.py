"""오케스트레이터 흐름 — 가짜 retriever/LLM으로 결정론 검증."""

from sejong_rag.agent.orchestrator import Orchestrator
from sejong_rag.models import Candidate, ConversationProfile, DocType, Intent
from sejong_rag.retrieve.retriever import RetrievalFilter, Retriever


class FakeRetriever(Retriever):
    def __init__(self, results):
        self.results = results
        self.last_filter = None

    def search(self, query, filters: RetrievalFilter | None = None, top_k: int = 8):
        self.last_filter = filters
        return self.results


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def generate(self, system, user):
        self.calls += 1
        return "신청 기간은 6월 18일까지입니다 [1]."


def _cand():
    return Candidate(
        id="1", score=0.9, doc_type=DocType.BIGYOGWA,
        text="AI 해커톤 / 신청 ~6/18", source_url="https://do.sejong.ac.kr/ko/program/all/view/1",
    )


def test_answer_path_uses_llm_and_returns_sources():
    orch = Orchestrator(FakeRetriever([_cand()]), FakeLLM())
    res = orch.run("지금 신청 가능한 비교과 알려줘")
    assert res.kind == "answer"
    assert res.intent is Intent.BIGYOGWA
    assert res.sources and res.sources[0].id == "1"
    assert "[1]" in res.text


def test_abstain_when_no_candidates():
    llm = FakeLLM()
    orch = Orchestrator(FakeRetriever([]), llm)
    res = orch.run("지금 신청 가능한 비교과 알려줘")
    assert res.kind == "abstain"
    assert llm.calls == 0  # 결과 없으면 LLM 호출 안 함(환각 방지)


def test_clarify_path_for_vague_lab():
    orch = Orchestrator(FakeRetriever([_cand()]), FakeLLM())
    res = orch.run("연구실 추천해줘")
    assert res.kind == "clarify"
    assert "interests" in res.profile.asked_fields


def test_smalltalk_no_search():
    llm = FakeLLM()
    orch = Orchestrator(FakeRetriever([_cand()]), llm)
    res = orch.run("안녕?")
    assert res.kind == "abstain"
    assert llm.calls == 0


def test_profile_extracted_from_query():
    orch = Orchestrator(FakeRetriever([_cand()]), FakeLLM())
    res = orch.run("컴공 3학년인데 지금 신청 가능한 비교과 알려줘")
    assert res.profile.grade == 3
    assert res.profile.major == "컴퓨터공학과"


def test_open_filter_passed_to_retriever():
    fr = FakeRetriever([_cand()])
    Orchestrator(fr, FakeLLM()).run("지금 신청 가능한 비교과")
    assert fr.last_filter.only_open is True
    assert fr.last_filter.as_of_epoch is not None
