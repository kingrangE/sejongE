"""긴 텍스트 청킹. 문단 경계를 우선 존중하고, 길면 문자 한도로 분할."""

from __future__ import annotations

import re

DEFAULT_MAX_CHARS = 1200
DEFAULT_OVERLAP = 150


def chunk_text(
    text: str, max_chars: int = DEFAULT_MAX_CHARS, overlap: int = DEFAULT_OVERLAP
) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    # 문단 단위로 모으되 한도를 넘기면 끊는다
    paras = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 1 <= max_chars:
            buf = f"{buf}\n{p}".strip()
        else:
            if buf:
                chunks.append(buf)
            if len(p) <= max_chars:
                buf = p
            else:
                chunks.extend(_split_hard(p, max_chars, overlap))
                buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def _split_hard(text: str, max_chars: int, overlap: int) -> list[str]:
    out = []
    start = 0
    step = max(1, max_chars - overlap)
    while start < len(text):
        out.append(text[start : start + max_chars])
        start += step
    return out
