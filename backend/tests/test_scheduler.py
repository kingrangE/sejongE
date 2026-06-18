"""스케줄러 — 작업 등록·장애 격리(시작하지 않고 검증)."""

import pytest

pytest.importorskip("apscheduler")
from apscheduler.schedulers.background import BackgroundScheduler  # noqa: E402

from sejong_rag.ingest.scheduler import register_jobs, run_all_now, safe_ingest  # noqa: E402


def test_register_three_jobs():
    sched = BackgroundScheduler()
    register_jobs(sched, ingest_fn=lambda s: None)
    ids = {j.id for j in sched.get_jobs()}
    assert ids == {"crawl_bigyogwa", "crawl_calendar", "crawl_labs"}


def test_safe_ingest_success_and_failure():
    calls, dl = [], []
    safe_ingest("bigyogwa", lambda s: calls.append(s), lambda s, e: dl.append((s, e)))
    assert calls == ["bigyogwa"] and dl == []

    safe_ingest("labs", lambda s: (_ for _ in ()).throw(RuntimeError("x")), lambda s, e: dl.append((s, e)))
    assert dl and dl[0][0] == "labs"


def test_run_all_now_isolates_failures():
    done, dl = [], []

    def ingest(site):
        if site == "calendar":
            raise ValueError("fail")
        done.append(site)

    run_all_now(ingest_fn=ingest, dl_fn=lambda s, e: dl.append(s))
    assert set(done) == {"bigyogwa", "labs"}  # 한 사이트 실패가 나머지를 막지 않음
    assert dl == ["calendar"]
