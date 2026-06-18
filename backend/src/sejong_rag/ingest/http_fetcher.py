"""정적 HTTP fetcher — httpx 기반.

- 식별 User-Agent, 정중한 지연(jitter), 원본 바이트 캐시(data/raw/{site}).
- 인코딩 감지는 normalize.html_clean.decode_bytes에 위임.
- JS 렌더링이 필요한 사이트는 playwright_fetcher(별도)를 사용.
"""

from __future__ import annotations

import time

import httpx

from sejong_rag.config import Settings, get_settings
from sejong_rag.normalize.html_clean import decode_bytes


class HttpFetcher:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._client = httpx.Client(
            headers={"User-Agent": self.settings.crawl_user_agent},
            timeout=20.0,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpFetcher":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def fetch(self, url: str, *, site: str, cache_key: str | None = None) -> str:
        """URL을 가져와 디코드된 텍스트 반환. 원본 바이트는 data/raw에 캐시."""
        resp = self._client.get(url)
        resp.raise_for_status()
        raw = resp.content
        self._cache_raw(site, cache_key or _safe_name(url), raw)
        # 정중한 지연
        time.sleep(self.settings.crawl_min_delay_sec)
        return decode_bytes(raw, resp.headers.get("content-type"))

    def post(self, url: str, data: dict, *, site: str, referer: str | None = None) -> str:
        """폼 POST(예: 학과 교수 목록 API). 정중한 지연 후 텍스트 반환."""
        headers = {"X-Requested-With": "XMLHttpRequest"}
        if referer:
            headers["Referer"] = referer
        resp = self._client.post(url, data=data, headers=headers)
        resp.raise_for_status()
        time.sleep(self.settings.crawl_min_delay_sec)
        return decode_bytes(resp.content, resp.headers.get("content-type"))

    def _cache_raw(self, site: str, name: str, raw: bytes) -> None:
        d = self.settings.raw_dir / site
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.html").write_bytes(raw)


def _safe_name(url: str) -> str:
    import re

    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", url)[-100:]
