"""FastAPI /chat SSE 엔드포인트 — 무상태(프로필은 요청에 동봉). 가짜 orchestrator 주입."""

import json

import pytest
from fastapi.testclient import TestClient

from sejong_rag.agent.orchestrator import Orchestrator
from sejong_rag.api.deps import get_orchestrator
from sejong_rag.api.main import app
from sejong_rag.models import Candidate, DocType
from sejong_rag.retrieve.retriever import RetrievalFilter, Retriever


class FakeRetriever(Retriever):
    def __init__(self, results):
        self.results = results

    def search(self, query, filters: RetrievalFilter | None = None, top_k: int = 8):
        return self.results


class FakeLLM:
    def generate(self, system, user):
        return "답변입니다 [1]."

    def stream(self, system, user):
        yield "답변"
        yield "입니다 [1]."


def _cand():
    return Candidate(id="1", score=0.9, doc_type=DocType.BIGYOGWA, text="AI 해커톤",
                     source_url="https://do.sejong.ac.kr/ko/program/all/view/1")


def _client(results):
    orch = Orchestrator(FakeRetriever(results), FakeLLM())
    app.dependency_overrides[get_orchestrator] = lambda: orch
    return TestClient(app)


def _parse_sse(text: str):
    events = []
    for block in text.strip().split("\n\n"):
        ev, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        if ev:
            events.append((ev, data))
    return events


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_health():
    assert _client([]).get("/health").json() == {"status": "ok"}


def test_chat_answer_streams_sources_and_deltas():
    r = _client([_cand()]).post("/chat", json={"message": "지금 신청 가능한 비교과 알려줘"})
    assert r.status_code == 200
    names = [e for e, _ in _parse_sse(r.text)]
    assert "sources" in names and "delta" in names
    assert names[-1] == "done"
    deltas = "".join(d for e, d in _parse_sse(r.text) if e == "delta")
    assert "[1]" in deltas


def test_chat_clarify_for_vague_lab():
    names = [e for e, _ in _parse_sse(_client([_cand()]).post("/chat", json={"message": "연구실 추천해줘"}).text)]
    assert "clarify" in names
    assert "sources" not in names


def test_chat_smalltalk_abstains():
    events = _parse_sse(_client([_cand()]).post("/chat", json={"message": "안녕?"}).text)
    assert any(e == "abstain" for e, _ in events)


def test_profile_from_request_is_used_and_returned():
    # 클라이언트가 보낸 프로필이 응답 profile 이벤트에 유지됨(무상태)
    body = {"message": "지금 신청 가능한 비교과", "profile": {"grade": 2, "major": "컴퓨터공학과", "interests": [], "asked_fields": []}}
    events = _parse_sse(_client([_cand()]).post("/chat", json=body).text)
    prof = next(d for e, d in events if e == "profile")
    assert prof["grade"] == 2 and prof["major"] == "컴퓨터공학과"


def test_profile_extracted_from_message_merges():
    body = {"message": "저는 컴공 3학년이에요. 지금 신청 가능한 비교과 알려줘"}
    events = _parse_sse(_client([_cand()]).post("/chat", json=body).text)
    prof = next(d for e, d in events if e == "profile")
    assert prof["grade"] == 3 and prof["major"] == "컴퓨터공학과"


def test_no_profile_defaults_empty():
    events = _parse_sse(_client([_cand()]).post("/chat", json={"message": "안녕?"}).text)
    prof = next(d for e, d in events if e == "profile")
    assert prof["grade"] is None
