"""사이트별 ETL 실행을 한 곳으로 모은 파이프라인 (CLI·스케줄러 공용).

crawl_site: 사이트별 크롤→파싱(도메인 문서 반환).
ingest_site: 크롤→정규화→멱등 적재(run_etl)까지 한 번에.
dead_letter: 영속 실패를 파일에 기록(운영 가시성).
"""

from __future__ import annotations

from sejong_rag.config import Settings, get_settings
from sejong_rag.index.build_index import EtlStats, run_etl
from sejong_rag.time_utils import now_kst

SITES = ["bigyogwa", "calendar", "labs"]


def crawl_site(site: str, fetcher, crawled_at: str, *, year: int | None = None, pages: int | None = None):
    from sejong_rag.ingest.sites import bigyogwa, calendar, labs

    if site == "bigyogwa":
        return bigyogwa.crawl(fetcher, crawled_at=crawled_at, max_pages=pages)
    if site == "calendar":
        return calendar.crawl(fetcher, crawled_at=crawled_at, year=year or now_kst().year)
    if site == "labs":
        return labs.crawl(fetcher, crawled_at=crawled_at)
    raise ValueError(f"지원하지 않는 site: {site}")


def ingest_site(site: str, *, settings: Settings | None = None, year: int | None = None, pages: int | None = None) -> EtlStats:
    """한 사이트를 크롤해 색인에 멱등 적재한다."""
    settings = settings or get_settings()
    settings.ensure_dirs()
    crawled_at = now_kst().isoformat()

    from sejong_rag.index.embedder import OpenAIEmbedder
    from sejong_rag.index.store import DocumentStore
    from sejong_rag.index.vectorstore import ChromaVectorStore
    from sejong_rag.ingest.http_fetcher import HttpFetcher

    with HttpFetcher(settings) as fetcher:
        docs = crawl_site(site, fetcher, crawled_at, year=year, pages=pages)

    store = DocumentStore(settings.sqlite_path)
    try:
        return run_etl(
            docs,
            store=store,
            embedder=OpenAIEmbedder(settings),
            vectorstore=ChromaVectorStore(settings),
            site=site,
            run_id=now_kst().strftime("run-%Y%m%d-%H%M%S"),
            started_at=crawled_at,
            finished_at=now_kst().isoformat(),
        )
    finally:
        store.close()


def dead_letter(site: str, error: str, settings: Settings | None = None) -> None:
    """영속 실패 기록(dead-letter). 한 사이트 실패가 다른 사이트를 막지 않게 운영."""
    settings = settings or get_settings()
    settings.ensure_dirs()
    path = settings.data_dir / "dead_letter.log"
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{now_kst().isoformat()}\t{site}\t{error}\n")
