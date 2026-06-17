"""FastAPI /chat SSE 엔드포인트 — 가짜 orchestrator 주입(키 불필요)."""

import json

import pytest
from fastapi.testclient import TestClient

from sejong_rag.agent.orchestrator import Orchestrator
from sejong_rag.api.deps import get_orchestrator, get_session_store
from sejong_rag.api.main import app
from sejong_rag.api.session import SessionStore
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
    store = SessionStore()
    app.dependency_overrides[get_orchestrator] = lambda: orch
    app.dependency_overrides[get_session_store] = lambda: store
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
    events = _parse_sse(r.text)
    names = [e for e, _ in events]
    assert names[0] == "session"
    assert "sources" in names
    assert "delta" in names
    assert names[-1] == "done"
    # 스트리밍된 토큰을 합치면 답변이 됨
    text = "".join(d for e, d in [(e, d.get("text") if isinstance(d, dict) else d) for e, d in events] if e == "delta")
    # delta data는 문자열 토큰
    deltas = "".join(d for e, d in events if e == "delta")
    assert "[1]" in deltas


def test_chat_clarify_for_vague_lab():
    events = _parse_sse(_client([_cand()]).post("/chat", json={"message": "연구실 추천해줘"}).text)
    names = [e for e, _ in events]
    assert "clarify" in names
    assert "sources" not in names  # 되묻기 단계에선 검색 안 함


def test_chat_smalltalk_abstains():
    events = _parse_sse(_client([_cand()]).post("/chat", json={"message": "안녕?"}).text)
    assert any(e == "abstain" for e, _ in events)


def test_session_id_issued_and_reused():
    client = _client([_cand()])
    ev1 = _parse_sse(client.post("/chat", json={"message": "안녕?"}).text)
    sid = next(d["session_id"] for e, d in ev1 if e == "session")
    assert sid
    ev2 = _parse_sse(client.post("/chat", json={"message": "안녕?", "session_id": sid}).text)
    sid2 = next(d["session_id"] for e, d in ev2 if e == "session")
    assert sid2 == sid


def test_profile_persists_across_requests():
    client = _client([_cand()])
    ev1 = _parse_sse(client.post("/chat", json={"message": "저는 컴공 3학년이에요"}).text)
    sid = next(d["session_id"] for e, d in ev1 if e == "session")
    prof = next(d for e, d in ev1 if e == "profile")
    assert prof["grade"] == 3
    assert prof["major"] == "컴퓨터공학과"
