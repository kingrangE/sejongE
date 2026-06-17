"""시스템 프롬프트 + 검색 컨텍스트 포매팅.

엔지니어링 원칙: 검색된 자료만 근거로 답하고(anti-hallucination), 출처를 번호로 인용,
한국어 존댓말, 자료가 없으면 모른다고 답한다.
"""

from __future__ import annotations

from sejong_rag.models import Candidate

SYSTEM_PROMPT = """당신은 세종대학교 학생을 돕는 정보 안내 챗봇입니다.

규칙:
1. 아래 제공된 '검색 자료'에 있는 내용만 근거로 답하세요. 자료에 없는 사실을 지어내지 마세요.
2. 근거가 된 자료는 문장 끝에 [번호] 형태로 인용하세요. 예: "신청 기간은 6월 18일까지입니다 [1]."
3. 자료에서 답을 찾을 수 없으면, 모른다고 솔직히 말하고 추측하지 마세요.
4. 한국어 존댓말로, 간결하고 명확하게 답하세요.
5. 날짜·신청기간·대상 등 구체 정보는 자료의 값을 그대로 정확히 전달하세요."""


def format_context(candidates: list[Candidate]) -> str:
    if not candidates:
        return "(검색된 자료가 없습니다.)"
    blocks = []
    for i, c in enumerate(candidates, 1):
        blocks.append(f"[{i}] (출처: {c.source_url})\n{c.text}")
    return "\n\n".join(blocks)


def build_user_message(query: str, candidates: list[Candidate]) -> str:
    return (
        f"검색 자료:\n{format_context(candidates)}\n\n"
        f"학생 질문: {query}\n\n"
        f"위 검색 자료만 근거로 답하고, 사용한 자료를 [번호]로 인용하세요."
    )
