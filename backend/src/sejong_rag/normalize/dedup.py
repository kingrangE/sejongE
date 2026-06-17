"""안정 id 및 콘텐츠 해시 — 멱등 ETL과 변경 감지의 토대."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit, urlunsplit


def canonical_url(url: str) -> str:
    """프래그먼트·말미 슬래시 제거 등 URL 정규화(동일 자원 → 동일 키)."""
    parts = urlsplit(url.strip())
    path = re.sub(r"/+$", "", parts.path) or "/"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def stable_id(url: str, key: str | None = None) -> str:
    """정규 URL(+선택 키) 기반의 결정론적 id."""
    base = canonical_url(url)
    if key:
        base = f"{base}#{key}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def content_hash(text: str) -> str:
    """정규화 텍스트의 sha256 — 변경 여부 판정용."""
    normalized = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
