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
    """사이트별 크롤→파싱. 도메인 문서 리스트 반환."""
    from sejong_rag.ingest.sites import bigyogwa, calendar, labs

    if site == "bigyogwa":
        return bigyogwa.crawl(fetcher, crawled_at=crawled_at, max_pages=args.pages)
    if site == "calendar":
        year = args.year or now_kst().year
        return calendar.crawl(fetcher, crawled_at=crawled_at, year=year)
    if site == "labs":
        return labs.crawl(fetcher, crawled_at=crawled_at)
    raise ValueError(f"지원하지 않는 site: {site}")


def _doc_line(d) -> str:
    if getattr(d, "program_name", None):
        return f"  - {d.id} | {d.program_name[:50]} | 신청 {d.apply_start}~{d.apply_end}"
    if getattr(d, "professor_name", None):
        return f"  - {d.id} | {d.professor_name} | {d.department} | {', '.join(d.research_areas[:3])}"
    return f"  - {d.id} | {d.title[:50]} | {d.start_date}~{d.end_date} | {d.category}"


def cmd_crawl(args: argparse.Namespace) -> int:
    from sejong_rag.ingest.http_fetcher import HttpFetcher

    settings = get_settings()
    settings.ensure_dirs()
    crawled_at = now_kst().isoformat()

    with HttpFetcher(settings) as fetcher:
        docs = _crawl_docs(args.site, fetcher, crawled_at, args)
    print(f"[crawl] 파싱된 문서: {len(docs)}건 (site={args.site})")

    if args.dry_run:
        for d in docs:
            print(_doc_line(d))
        return 0

    # 실제 적재: OpenAI 임베딩 + Chroma + SQLite
    from sejong_rag.index.build_index import run_etl
    from sejong_rag.index.embedder import OpenAIEmbedder
    from sejong_rag.index.store import DocumentStore
    from sejong_rag.index.vectorstore import ChromaVectorStore

    store = DocumentStore(settings.sqlite_path)
    stats = run_etl(
        docs,
        store=store,
        embedder=OpenAIEmbedder(settings),
        vectorstore=ChromaVectorStore(settings),
        site=args.site,
        run_id=_run_id(),
        started_at=crawled_at,
        finished_at=now_kst().isoformat(),
    )
    store.close()
    print(
        f"[crawl] 적재 완료 — new={stats.new} changed={stats.changed} "
        f"unchanged={stats.unchanged} deleted={stats.deleted} embedded={stats.embedded}"
    )
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
    """단발 질의 → 라우팅·검색·근거 기반 답변. (OpenAI+Chroma+Claude 키 필요)"""
    from sejong_rag.agent.factory import build_orchestrator

    orch = build_orchestrator()
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
    p_crawl.add_argument("--site", required=True, choices=["bigyogwa", "calendar", "labs"])
    p_crawl.add_argument("--pages", type=int, default=1)
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
    p_ask.set_defaults(func=cmd_ask)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
