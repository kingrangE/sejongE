"""비교과(두드림) 파서 — do.sejong.ac.kr/ko/program.

목록 페이지(`ul.columns-5 > li` 카드)에서 구조화 필드를 추출한다.
목록 DOM이 깨끗하고 필터링에 필요한 정보(제목·운영기관·신청/운영기간·모집현황·마일리지)를
모두 담고 있어 v1은 목록 기반으로 한다. 상세 본문/자격(학년·전공) 정밀 추출은
Playwright 기반 후속(현재 eligibility는 비움=전체)으로 둔다.
"""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sejong_rag.models import BigyogwaProgram
from sejong_rag.normalize.dedup import content_hash, stable_id
from sejong_rag.time_utils import epoch_day

BASE_URL = "https://do.sejong.ac.kr"
# 전체 목록 엔드포인트. 단, ?page= 페이지네이션은 JS(AJAX) 구동이라
# 정적 fetch는 첫 묶음만 반환한다 → 전체 수집은 Playwright fetcher 필요.
LIST_PATH = "/ko/program/all/list/all/1"

_DATE = r"(\d{4})\.(\d{2})\.(\d{2})"
_APPLY_RE = re.compile(r"신청:\s*" + _DATE + r"\([^)]*\)\s*~\s*" + _DATE + r"\([^)]*\)")
_EVENT_RE = re.compile(r"운영:\s*" + _DATE + r"\([^)]*\)\s*~\s*" + _DATE + r"\([^)]*\)")
_CAP_RE = re.compile(r"(\d+)\s*/\s*(무제한|\d+)")
_MILEAGE_RE = re.compile(r"\bm\s+(\d{1,4})\b")
_ID_RE = re.compile(r"/view/(\d+)")


def list_page_url(page: int = 1) -> str:
    return f"{BASE_URL}{LIST_PATH}?page={page}"


def _to_date(y: str, m: str, d: str) -> date:
    return date(int(y), int(m), int(d))


def crawl(fetcher, crawled_at: str, max_pages: int = 1, with_detail: bool = True) -> list[BigyogwaProgram]:
    """목록을 가져와 파싱하고, 각 프로그램 상세의 설명 본문까지 보강한다.

    주의: ?page= 페이지네이션은 JS 구동이라 정적 fetch는 첫 묶음만 반환한다.
    전체 수집은 playwright_fetcher 도입 후 max_pages를 늘려 사용.
    """
    by_id: dict[str, BigyogwaProgram] = {}
    for page in range(1, max_pages + 1):
        html = fetcher.fetch(list_page_url(page), site="bigyogwa", cache_key=f"list_p{page}")
        for prog in parse_list(html, crawled_at):
            by_id[prog.id] = prog
    programs = list(by_id.values())

    if with_detail:
        for p in programs:
            try:
                dhtml = fetcher.fetch(p.source_url, site="bigyogwa", cache_key=f"view_{p.id}")
                desc = parse_detail(dhtml)
                if desc:
                    p.description = desc
                    _finalize(p)  # 설명 반영해 embedding_text·content_hash 갱신
            except Exception:
                continue  # 상세 실패는 목록 정보로 진행(장애 격리)
    return programs


def parse_list(html: str, crawled_at: str, base_url: str = BASE_URL) -> list[BigyogwaProgram]:
    """목록 페이지 HTML → BigyogwaProgram 리스트."""
    soup = BeautifulSoup(html, "lxml")
    programs: list[BigyogwaProgram] = []
    seen: set[str] = set()  # 목록에 같은 프로그램이 위젯으로 중복 노출됨 → id 기준 제거
    for li in soup.select("ul.columns-5 > li"):
        a = li.select_one('a[href*="/program/all/view/"]')
        if not a:
            continue
        href = a.get("href", "")
        m = _ID_RE.search(href)
        if not m:
            continue
        pid = m.group(1)
        if pid in seen:
            continue
        seen.add(pid)
        detail_url = urljoin(base_url, f"/ko/program/all/view/{pid}")

        title_el = li.select_one("b.title")
        inst_el = li.select_one("span.institution")
        ptype_el = li.select_one("span.type")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        organizer = inst_el.get_text(" ", strip=True) if inst_el else ""
        ptype = ptype_el.get_text(" ", strip=True) if ptype_el else ""

        text = li.get_text(" ", strip=True)

        apply_start = apply_end = event_start = event_end = None
        am = _APPLY_RE.search(text)
        if am:
            apply_start = _to_date(*am.group(1, 2, 3))
            apply_end = _to_date(*am.group(4, 5, 6))
        em = _EVENT_RE.search(text)
        if em:
            event_start = _to_date(*em.group(1, 2, 3))
            event_end = _to_date(*em.group(4, 5, 6))

        applied = capacity = None
        cm = _CAP_RE.search(text)
        if cm:
            applied = int(cm.group(1))
            capacity = None if cm.group(2) == "무제한" else int(cm.group(2))

        mileage = None
        mm = _MILEAGE_RE.search(text)
        if mm:
            mileage = int(mm.group(1))

        prog = BigyogwaProgram(
            id=stable_id(detail_url),
            source_url=detail_url,
            source_site="bigyogwa",
            crawled_at=crawled_at,
            content_hash="",
            program_name=title,
            organizer=organizer,
            apply_start=apply_start,
            apply_end=apply_end,
            apply_start_epoch=epoch_day(apply_start) if apply_start else None,
            apply_end_epoch=epoch_day(apply_end) if apply_end else None,
            event_start=event_start,
            event_end=event_end,
            capacity=capacity,
            applied_count=applied,
            mileage=mileage,
            eligibility_note=f"참여형태: {ptype}" if ptype else "",
            apply_url=detail_url,
        )
        programs.append(_finalize(prog))
    return programs


def parse_detail(html: str) -> str:
    """상세 페이지에서 설명 본문(div.description) 추출. 정적 HTML에 존재."""
    soup = BeautifulSoup(html, "lxml")
    el = soup.select_one("div.description")
    if not el:
        return ""
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()


def _embedding_text(p: BigyogwaProgram) -> str:
    lines = [p.program_name, f"운영기관: {p.organizer}"]
    if p.eligibility_note:
        lines.append(p.eligibility_note)
    if p.apply_start and p.apply_end:
        lines.append(f"신청기간: {p.apply_start} ~ {p.apply_end}")
    if p.event_start and p.event_end:
        lines.append(f"운영기간: {p.event_start} ~ {p.event_end}")
    if p.mileage:
        lines.append(f"마일리지: {p.mileage}점")
    if p.description:
        lines.append("\n" + p.description)
    return "\n".join(lines)


def _content_hash(p: BigyogwaProgram) -> str:
    return content_hash(
        "|".join(
            str(x)
            for x in [
                p.program_name, p.organizer, p.apply_start, p.apply_end,
                p.event_start, p.event_end, p.applied_count, p.capacity, p.mileage, p.description,
            ]
        )
    )


def _finalize(p: BigyogwaProgram) -> BigyogwaProgram:
    """현재 필드(설명 포함)로 embedding_text·text·content_hash를 확정."""
    p.embedding_text = _embedding_text(p)
    p.text = p.embedding_text
    p.content_hash = _content_hash(p)
    return p
