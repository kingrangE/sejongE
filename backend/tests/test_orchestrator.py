"""오케스트레이터 흐름 — 가짜 retriever/LLM으로 결정론 검증."""

from sejong_rag.agent.orchestrator import Orchestrator
from sejong_rag.models import Candidate, ConversationProfile, DocType, Intent
from sejong_rag.retrieve.retriever import RetrievalFilter, Retriever


class FakeRetriever(Retriever):
    def __init__(self, results):
        self.results = results
        self.last_filter = None
        self.last_query = None

    def search(self, query, filters: RetrievalFilter | None = None, top_k: int = 8):
        self.last_filter = filters
        self.last_query = query
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


def test_profile_question_answered_from_profile():
    llm = FakeLLM()
    fr = FakeRetriever([_cand()])
    orch = Orchestrator(fr, llm)
    res = orch.run("내 관심사가 뭐야?", ConversationProfile(interests=["인공지능", "로봇"]))
    assert res.kind == "answer"
    assert res.intent is Intent.PROFILE
    assert "인공지능" in res.text and "로봇" in res.text
    assert llm.calls == 0  # 검색/LLM 없이 프로필에서 직접 답
    assert fr.last_filter is None  # 검색기 호출 안 함


def test_profile_question_when_unset():
    res = Orchestrator(FakeRetriever([]), FakeLLM()).run("내 관심사가 뭐야?", ConversationProfile())
    assert res.kind == "answer" and res.intent is Intent.PROFILE
    assert "설정" in res.text  # "설정되어 있지 않아요" 안내


def test_interest_augments_search_query():
    fr = FakeRetriever([_cand()])
    orch = Orchestrator(fr, FakeLLM())
    orch.run("그 관심사를 기반으로 추천해줘", ConversationProfile(interests=["AI", "LLM", "C++"]))
    # 관심사 값이 실제 검색 질의에 보강됨
    assert "AI" in fr.last_query and "LLM" in fr.last_query and "C++" in fr.last_query


def test_lab_query_augmented_with_interests():
    fr = FakeRetriever([_cand()])
    Orchestrator(fr, FakeLLM()).run("연구실 추천해줘", ConversationProfile(interests=["로보틱스"]))
    assert "로보틱스" in fr.last_query


def test_no_interest_no_augment():
    fr = FakeRetriever([_cand()])
    Orchestrator(fr, FakeLLM()).run("이번 주 시험 일정", ConversationProfile(interests=["AI"]))
    # 캘린더 등 관심사와 무관한 질의는 보강하지 않음
    assert "AI" not in fr.last_query


def test_open_filter_passed_to_retriever():
    fr = FakeRetriever([_cand()])
    Orchestrator(fr, FakeLLM()).run("지금 신청 가능한 비교과")
    assert fr.last_filter.only_open is True
    assert fr.last_filter.as_of_epoch is not None
