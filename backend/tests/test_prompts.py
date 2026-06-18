"""프롬프트 구성 — 대화기록·프로필 주입."""

from sejong_rag.agent.prompts import build_user_message
from sejong_rag.models import Candidate, ConversationProfile, DocType


def _cands():
    return [Candidate(id="1", score=1.0, doc_type=DocType.LAB, text="내용", source_url="u")]


def test_history_block_included():
    hist = [
        {"role": "user", "content": "연구실 추천해줘"},
        {"role": "assistant", "content": "A 교수님을 추천드립니다"},
    ]
    msg = build_user_message("그거 더 자세히", _cands(), None, hist)
    assert "이전 대화" in msg
    assert "A 교수님을 추천드립니다" in msg


def test_profile_block_included():
    msg = build_user_message("질문", _cands(), ConversationProfile(grade=3, interests=["AI"]))
    assert "사용자 정보" in msg and "AI" in msg and "3" in msg


def test_no_history_no_block():
    msg = build_user_message("질문", _cands())
    assert "이전 대화" not in msg


def test_history_truncates_to_recent_turns():
    hist = [{"role": "user", "content": f"메시지{i}"} for i in range(20)]
    msg = build_user_message("q", _cands(), None, hist)
    assert "메시지19" in msg  # 최근 것 포함
    assert "메시지0" not in msg  # 오래된 것 제외(최근 6턴만)
