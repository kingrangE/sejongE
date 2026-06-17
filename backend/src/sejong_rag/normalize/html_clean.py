"""HTML 인코딩 감지·정규화·본문 텍스트 추출.

- 한국어 사이트는 EUC-KR/CP949가 섞여 있고 meta charset이 부정확할 수 있어
  바이트에서 직접 감지한다(charset-normalizer, 없으면 cp949/utf-8 폴백).
- Hangul NFC 정규화로 BM25/임베딩 일관성 확보.
"""

from __future__ import annotations

import unicodedata


def decode_bytes(raw: bytes, http_charset: str | None = None) -> str:
    """바이트 → 텍스트. 감지 우선, 실패 시 폴백."""
    try:
        from charset_normalizer import from_bytes

        best = from_bytes(raw).best()
        if best is not None:
            return normalize_text(str(best))
    except Exception:
        pass
    for enc in filter(None, [http_charset, "utf-8", "cp949", "euc-kr"]):
        try:
            return normalize_text(raw.decode(enc))
        except (UnicodeDecodeError, LookupError):
            continue
    return normalize_text(raw.decode("utf-8", "replace"))


def normalize_text(text: str) -> str:
    """NFC 정규화 + 제어/제로폭 문자 정리."""
    text = unicodedata.normalize("NFC", text)
    # 제로폭·NBSP 정리
    for ch in ("​", "‌", "‍", "﻿"):
        text = text.replace(ch, "")
    return text.replace("\xa0", " ")


def visible_text(html: str) -> str:
    """script/style 제거 후 보이는 텍스트만."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return normalize_text(soup.get_text(" ", strip=True))
