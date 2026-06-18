"""명령행 인터페이스.

예:
  python -m sejong_rag.cli crawl --site bigyogwa
  python -m sejong_rag.cli crawl --site bigyogwa --pages 1 --dry-run
"""

from __future__ import annotations

import argparse
import sys

from sejong_rag.config import get_settings
from sejong_rag.time_utils import now_kst


def _run_id() -> str:
    return now_kst().strftime("run-%Y%m%d-%H%M%S")


def _crawl_docs(site: str, fetcher, crawled_at: str, args: argparse.Namespace):
    """사이트별 크롤→파싱(검수/덤프용). 파이프라인 디스패치 재사용."""
    from sejong_rag.ingest.pipeline import crawl_site

    return crawl_site(site, fetcher, crawled_at, year=args.year, pages=args.pages)


def _doc_line(d) -> str:
    if getattr(d, "program_name", None):
        return f"  - {d.id} | {d.program_name[:50]} | 신청 {d.apply_start}~{d.apply_end}"
    if getattr(d, "professor_name", None):
        return f"  - {d.id} | {d.professor_name} | {d.department} | {', '.join(d.research_areas[:3])}"
    return f"  - {d.id} | {d.title[:50]} | {d.start_date}~{d.end_date} | {d.category}"


def cmd_crawl(args: argparse.Namespace) -> int:
    from sejong_rag.ingest.pipeline import SITES, ingest_site

    settings = get_settings()
    settings.ensure_dirs()
    sites = SITES if args.site == "all" else [args.site]

    if args.dry_run:
        from sejong_rag.ingest.http_fetcher import HttpFetcher

        crawled_at = now_kst().isoformat()
        with HttpFetcher(settings) as fetcher:
            for site in sites:
                docs = _crawl_docs(site, fetcher, crawled_at, args)
                print(f"[crawl] 파싱된 문서: {len(docs)}건 (site={site})")
                for d in docs:
                    print(_doc_line(d))
        return 0

    for site in sites:
        stats = ingest_site(site, settings=settings, year=args.year, pages=args.pages)
        print(
            f"[crawl] {site} 적재 — new={stats.new} changed={stats.changed} "
            f"unchanged={stats.unchanged} deleted={stats.deleted} embedded={stats.embedded}"
        )
    return 0


def cmd_schedule(args: argparse.Namespace) -> int:
    """주기 크롤 스케줄러 시작(블로킹). --run-now로 시작 전 1회 즉시 적재."""
    from sejong_rag.ingest.scheduler import CADENCE, build_scheduler, run_all_now

    if args.run_now:
        print("[schedule] 초기 1회 적재 실행…")
        run_all_now()

    scheduler = build_scheduler()
    print(f"[schedule] 시작 — 주기: {CADENCE} (Ctrl+C로 종료)")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n[schedule] 종료")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    """수집 점검 리포트(Markdown) 생성. 실제 사이트와 대조용. API 키 불필요."""
    from sejong_rag.models import BigyogwaProgram, CalendarEvent, LabDoc
    from sejong_rag.report import (
        render_bigyogwa_markdown,
        render_calendar_markdown,
        render_labs_markdown,
    )

    settings = get_settings()
    settings.ensure_dirs()
    site = args.site
    model = {"bigyogwa": BigyogwaProgram, "calendar": CalendarEvent, "labs": LabDoc}[site]

    if args.from_store:
        from sejong_rag.index.store import DocumentStore

        store = DocumentStore(settings.sqlite_path)
        docs = [model(**p) for p in store.active_payloads(site)]
        store.close()
        source = "sqlite(active)"
    else:
        from sejong_rag.ingest.http_fetcher import HttpFetcher

        with HttpFetcher(settings) as fetcher:
            docs = _crawl_docs(site, fetcher, now_kst().isoformat(), args)
        source = "live parse"

    if site == "bigyogwa":
        md = render_bigyogwa_markdown(docs, source=source)
    elif site == "calendar":
        md = render_calendar_markdown(docs, source=source)
    else:
        md = render_labs_markdown(docs, source=source)
    out_path = args.out or str(settings.data_dir / f"inspect_{site}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[inspect] {len(docs)}건 → {out_path}")
    print("[inspect] 브라우저/에디터로 열어 실제 사이트와 대조하세요.")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    """단발 질의 → 라우팅·검색·근거 기반 답변. (OpenAI + Chroma 키 필요)"""
    from sejong_rag.agent.factory import build_orchestrator

    orch = build_orchestrator(hybrid=args.hybrid)
    res = orch.run(args.query)

    label = {"clarify": "되묻기", "answer": "답변", "abstain": "정보 없음"}.get(res.kind, res.kind)
    print(f"[의도] {res.intent.value}  [유형] {label}")
    print()
    print(res.text)
    if res.sources:
        print("\n[출처]")
        for i, c in enumerate(res.sources, 1):
            print(f"  [{i}] {c.source_url}")
    return 0


def main(argv: list[str] | None = None) -> int:
    # 콘솔 인코딩이 UTF-8이 아니어도(예: Windows cp949) 한글 출력이 깨지거나
    # 죽지 않도록 안전하게 설정.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass

    parser = argparse.ArgumentParser(prog="sejong-rag")
    sub = parser.add_subparsers(dest="command", required=True)

    p_crawl = sub.add_parser("crawl", help="사이트를 크롤링해 색인에 적재")
    p_crawl.add_argument("--site", required=True, choices=["bigyogwa", "calendar", "labs", "all"])
    p_crawl.add_argument("--pages", type=int, default=None,
                         help="비교과 수집 페이지 수(미지정=새 항목 없을 때까지 전체)")
    p_crawl.add_argument("--year", type=int, default=None, help="학사일정 연도(기본: 올해)")
    p_crawl.add_argument("--dry-run", action="store_true", help="적재 없이 파싱 결과만 출력(임베딩 호출 안 함)")
    p_crawl.set_defaults(func=cmd_crawl)

    p_insp = sub.add_parser("inspect", help="수집 점검 리포트(Markdown) 생성 — 사이트와 대조용")
    p_insp.add_argument("--site", required=True, choices=["bigyogwa", "calendar", "labs"])
    p_insp.add_argument("--pages", type=int, default=1)
    p_insp.add_argument("--year", type=int, default=None, help="학사일정 연도(기본: 올해)")
    p_insp.add_argument("--from-store", action="store_true", help="크롤 대신 SQLite 활성 문서에서 생성")
    p_insp.add_argument("--out", help="출력 경로 (기본: data/inspect_<site>.md)")
    p_insp.set_defaults(func=cmd_inspect)

    p_ask = sub.add_parser("ask", help="질문하기 (라우팅·검색·근거 기반 답변; API 키 필요)")
    p_ask.add_argument("--query", required=True, help="질문 문장")
    p_ask.add_argument("--hybrid", action="store_true", help="v2 하이브리드 검색(BM25+RRF) 사용")
    p_ask.set_defaults(func=cmd_ask)

    p_sched = sub.add_parser("schedule", help="주기 크롤 스케줄러 시작(지속 운영)")
    p_sched.add_argument("--run-now", action="store_true", help="시작 전 전체 1회 즉시 적재")
    p_sched.set_defaults(func=cmd_schedule)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
