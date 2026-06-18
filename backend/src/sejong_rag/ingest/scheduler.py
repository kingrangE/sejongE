"""지속 운영 스케줄러 — 도메인별 주기 크롤(APScheduler).

주기(계획): 비교과 4시간(마감 빠름) · 학사일정 1일 · 연구실 1주.
각 작업은 실패해도 다른 작업을 막지 않으며 dead-letter에 기록한다(장애 격리).
ingest/dead-letter 함수는 주입식 → 스케줄 시작 없이 테스트 가능.
"""

from __future__ import annotations

from typing import Callable

from sejong_rag.ingest.pipeline import SITES, dead_letter, ingest_site
from sejong_rag.time_utils import KST

# (site, interval kwargs)
CADENCE: dict[str, dict] = {
    "bigyogwa": {"hours": 4},
    "calendar": {"days": 1},
    "labs": {"weeks": 1},
}


def safe_ingest(site: str, ingest_fn: Callable, dl_fn: Callable) -> None:
    try:
        ingest_fn(site)
    except Exception as e:  # 한 사이트 실패 격리
        dl_fn(site, repr(e))


def register_jobs(scheduler, ingest_fn: Callable | None = None, dl_fn: Callable | None = None):
    ingest_fn = ingest_fn or (lambda s: ingest_site(s))
    dl_fn = dl_fn or dead_letter
    for site, interval in CADENCE.items():
        scheduler.add_job(
            lambda s=site: safe_ingest(s, ingest_fn, dl_fn),
            "interval",
            id=f"crawl_{site}",
            replace_existing=True,
            **interval,
        )
    return scheduler


def run_all_now(ingest_fn: Callable | None = None, dl_fn: Callable | None = None) -> None:
    """모든 사이트를 한 번 즉시 적재(스케줄 시작 전 초기 1회용)."""
    ingest_fn = ingest_fn or (lambda s: ingest_site(s))
    dl_fn = dl_fn or dead_letter
    for site in SITES:
        safe_ingest(site, ingest_fn, dl_fn)


def build_scheduler():
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler(timezone=KST)
    register_jobs(scheduler)
    return scheduler
