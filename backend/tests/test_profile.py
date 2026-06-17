"""프로필 추출 + 되묻기 게이트."""

from sejong_rag.agent.profile import extract_updates, needs_clarification
from sejong_rag.models import ConversationProfile, Intent


def test_extract_grade_and_major():
    p = extract_updates("저는 컴공 3학년이에요", ConversationProfile())
    assert p.grade == 3
    assert p.major == "컴퓨터공학과"


def test_extract_keeps_existing_when_absent():
    p = extract_updates("연구실 추천해줘", ConversationProfile(grade=2))
    assert p.grade == 2  # 새 정보 없으면 유지


def test_lab_vague_query_asks_interest():
    clar = needs_clarification(Intent.LAB, "연구실 추천해줘", ConversationProfile())
    assert clar is not None and clar.field == "interests"


def test_lab_query_with_topic_no_clarify():
    clar = needs_clarification(Intent.LAB, "자연어처리 연구실 추천해줘", ConversationProfile())
    assert clar is None


def test_lab_no_reask_if_already_asked():
    p = ConversationProfile(asked_fields=["interests"])
    assert needs_clarification(Intent.LAB, "연구실 추천해줘", p) is None


def test_bigyogwa_my_grade_cue_asks_grade():
    clar = needs_clarification(Intent.BIGYOGWA, "내 학년이 신청할 수 있는 비교과", ConversationProfile())
    assert clar is not None and clar.field == "grade"


def test_bigyogwa_my_grade_known_no_clarify():
    clar = needs_clarification(Intent.BIGYOGWA, "내 학년이 신청 가능한 비교과", ConversationProfile(grade=3))
    assert clar is None
