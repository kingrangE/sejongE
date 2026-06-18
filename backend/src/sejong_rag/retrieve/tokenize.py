"""한국어 토크나이저 — BM25용.

kiwipiepy가 있으면 형태소(내용어) 기반, 없으면 폴백(영숫자 + 한글 문자 bigram).
폴백도 한글 부분 일치를 어느 정도 잡아 외부 의존성 없이 동작/테스트 가능.
"""

from __future__ import annotations

import re
from typing import Callable

_WORD_RE = re.compile(r"[a-z0-9]+")
_HANGUL_RE = re.compile(r"[가-힣]+")
# 내용어 형태소 POS (체언/용언/외국어/숫자)
_CONTENT_POS = ("NNG", "NNP", "NNB", "NR", "VV", "VA", "SL", "SH", "SN", "XR")


def simple_tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens = _WORD_RE.findall(text)
    for run in _HANGUL_RE.findall(text):
        if len(run) < 2:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))  # 문자 bigram
    return tokens


def _build_kiwi_tokenizer() -> Callable[[str], list[str]] | None:
    try:
        from kiwipiepy import Kiwi
    except Exception:
        return None
    kiwi = Kiwi()

    def tok(text: str) -> list[str]:
        out = []
        for token in kiwi.tokenize(text):
            if token.tag in _CONTENT_POS:
                out.append(token.form.lower())
        return out or simple_tokenize(text)

    return tok


def get_tokenizer() -> Callable[[str], list[str]]:
    return _build_kiwi_tokenizer() or simple_tokenize
