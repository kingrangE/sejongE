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


def crawl(fetcher, crawled_at: str, max_pages: int = 1) -> list[BigyogwaProgram]:
    """목록 페이지를 정적으로 가져와 파싱. id 기준 중복 제거.

    주의: ?page= 페이지네이션은 JS 구동이라 정적 fetch는 첫 묶음만 반환한다.
    전체 수집은 playwright_fetcher 도입 후 max_pages를 늘려 사용.
    """
    by_id: dict[str, BigyogwaProgram] = {}
    for page in range(1, max_pages + 1):
        html = fetcher.fetch(list_page_url(page), site="bigyogwa", cache_key=f"list_p{page}")
        for prog in parse_list(html, crawled_at):
            by_id[prog.id] = prog
    return list(by_id.values())


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

        embedding_text = _embedding_text(title, organizer, ptype, apply_start, apply_end, event_start, event_end)
        chash = content_hash(
            "|".join(
                str(x)
                for x in [title, organizer, apply_start, apply_end, event_start, event_end, applied, capacity, mileage]
            )
        )

        programs.append(
            BigyogwaProgram(
                id=stable_id(detail_url),
                source_url=detail_url,
                source_site="bigyogwa",
                crawled_at=crawled_at,
                content_hash=chash,
                text=embedding_text,
                embedding_text=embedding_text,
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
        )
    return programs


def _embedding_text(title, organizer, ptype, a_s, a_e, e_s, e_e) -> str:
    lines = [title, f"운영기관: {organizer}"]
    if ptype:
        lines.append(f"참여형태: {ptype}")
    if a_s and a_e:
        lines.append(f"신청기간: {a_s} ~ {a_e}")
    if e_s and e_e:
        lines.append(f"운영기간: {e_s} ~ {e_e}")
    return "\n".join(lines)
