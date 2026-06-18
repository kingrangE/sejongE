"""비교과(두드림) 파서 — do.sejong.ac.kr/ko/program.

목록 페이지(`ul.columns-5 > li` 카드)에서 구조화 필드(제목·운영기관·신청/운영기간·
모집현황·마일리지)를 추출하고, 상세 본문(`div.description`)에서 설명과 참여 대상(학년/전공)을
보강한다. 페이지네이션은 쿼리(?page=)가 아니라 경로 세그먼트(/list/all/1/{page})로 동작하며,
정적 httpx로 모든 페이지가 받힌다(실측). 자격(학년/전공)은 본문의 '참여 대상' 자연어 섹션에
있어, 확신이 높은 패턴만 보수적으로 추출하고 불확실하면 비워(=전체) 둔다.
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
# 전체 목록 엔드포인트. 페이지네이션은 경로 세그먼트(/list/all/1/{page})이며,
# 정적 httpx로 모든 페이지가 받힌다(실측 — 과거 '?page='는 잘못된 패턴이었다).
LIST_BASE = "/ko/program/all/list/all/1"

# 범위를 벗어난 페이지는 사이트가 마지막 페이지를 반복 반환하므로,
# 새 프로그램이 없는 페이지가 연속 2회면 수집을 종료한다.
_EMPTY_STREAK_STOP = 2
_HARD_PAGE_CAP = 100  # 사이트 오작동 대비 안전 상한(무제한 수집 시)

_DATE = r"(\d{4})\.(\d{2})\.(\d{2})"
_APPLY_RE = re.compile(r"신청:\s*" + _DATE + r"\([^)]*\)\s*~\s*" + _DATE + r"\([^)]*\)")
_EVENT_RE = re.compile(r"운영:\s*" + _DATE + r"\([^)]*\)\s*~\s*" + _DATE + r"\([^)]*\)")
_CAP_RE = re.compile(r"(\d+)\s*/\s*(무제한|\d+)")
_MILEAGE_RE = re.compile(r"\bm\s+(\d{1,4})\b")
_ID_RE = re.compile(r"/view/(\d+)")


def list_page_url(page: int = 1) -> str:
    return f"{BASE_URL}{LIST_BASE}/{page}"


def _to_date(y: str, m: str, d: str) -> date:
    return date(int(y), int(m), int(d))


def crawl(fetcher, crawled_at: str, max_pages: int | None = None, with_detail: bool = True) -> list[BigyogwaProgram]:
    """목록 전체를 페이지네이션으로 수집하고, 각 상세의 설명·자격까지 보강한다.

    max_pages=None이면 새 항목이 없을 때까지(종료조건) 끝까지 수집하고,
    정수를 주면 정확히 그 페이지 수만 수집한다(검수·테스트용).
    페이지네이션은 경로 세그먼트(/list/all/1/{page})이며 정적 fetch로 동작한다.
    멱등 ETL이라 재실행 시 변경분만 다시 임베딩된다.
    """
    by_id: dict[str, BigyogwaProgram] = {}
    empty_streak = 0
    page = 1
    cap = max_pages if max_pages is not None else _HARD_PAGE_CAP
    while page <= cap:
        html = fetcher.fetch(list_page_url(page), site="bigyogwa", cache_key=f"list_p{page}")
        page_progs = parse_list(html, crawled_at)
        new_ids = [p for p in page_progs if p.id not in by_id]
        for p in page_progs:
            by_id.setdefault(p.id, p)
        if max_pages is None:  # 종료조건은 무제한 수집일 때만 (정수 지정 시 정확히 N페이지)
            if not new_ids:
                empty_streak += 1
                if empty_streak >= _EMPTY_STREAK_STOP:
                    break
            else:
                empty_streak = 0
        page += 1
    programs = list(by_id.values())

    if with_detail:
        for p in programs:
            try:
                dhtml = fetcher.fetch(p.source_url, site="bigyogwa", cache_key=f"view_{p.id}")
                desc = parse_detail(dhtml)
                if desc:
                    p.description = desc
                    _apply_eligibility(p, desc)  # 참여 대상 → 학년/전공
                    _finalize(p)  # 설명·자격 반영해 embedding_text·content_hash 갱신
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


# 참여 대상 섹션 마커(가장 흔한 순) 및 학년/전공 추출 패턴
_TARGET_MARKERS = (
    "참여 대상", "참여대상", "참가 대상", "참가대상", "모집대상", "모집 대상",
    "신청자격", "신청 자격", "지원자격", "지원 자격", "대상자",
)
# 대상 섹션의 끝(다음 항목)으로 볼 구분 표현
_SECTION_END = re.compile(r"[○◆▶]|※|운영방식|운영 방식|참여기간|참가기간|신청기간|신청방법|진행|시상|문의")
_GRADE_RANGE = re.compile(r"([1-4])\s*[~\-]\s*([1-4])\s*학년")
_GRADE_NUM = re.compile(r"([1-4])\s*학년")
_ANY_GRADE = ("학년무관", "학년 무관", "전 학년", "전학년", "모든 학년")
# 전공/학부/학과/계열로 끝나는 토큰만 전공 후보로 본다(일반어는 제외)
_MAJOR_TOKEN = re.compile(r"[가-힣A-Za-z]+(?:전공|학부|학과|계열)")
_MAJOR_STOPWORDS = {"학부", "대학원", "전공", "학부생", "대학원생"}


def _target_segment(description: str) -> str:
    """설명 본문에서 '참여 대상' 류 섹션의 텍스트만 잘라낸다. 없으면 ''."""
    if not description:
        return ""
    flat = re.sub(r"\s+", " ", description)
    for marker in _TARGET_MARKERS:
        i = flat.find(marker)
        if i < 0:
            continue
        seg = flat[i + len(marker): i + len(marker) + 120]
        end = _SECTION_END.search(seg)
        if end:
            seg = seg[: end.start()]
        return seg.strip(" :·-··")
    return ""


def parse_eligibility(description: str) -> dict:
    """'참여 대상' 섹션에서 학년/전공을 보수적으로 추출한다.

    자연어라 확신이 낮으면 비워(=전체) 둔다 — 환각보다 '전체'가 안전하다.
    반환: {"grade": list[int], "major": list[str], "note": str}.
    """
    seg = _target_segment(description)
    if not seg:
        return {"grade": [], "major": [], "note": ""}

    grades: list[int] = []
    if any(k in seg for k in _ANY_GRADE):
        grades = []  # 명시적 전체
    elif "신입생" in seg:
        grades = [1]
    else:
        rng = _GRADE_RANGE.search(seg)
        if rng:
            a, b = int(rng.group(1)), int(rng.group(2))
            grades = list(range(min(a, b), max(a, b) + 1))
        else:
            grades = sorted({int(m.group(1)) for m in _GRADE_NUM.finditer(seg)})

    majors: list[str] = []
    for m in _MAJOR_TOKEN.finditer(seg):
        tok = m.group(0)
        if tok in _MAJOR_STOPWORDS or tok in majors:
            continue
        majors.append(tok)

    return {"grade": grades, "major": majors, "note": seg[:120]}


def _apply_eligibility(p: BigyogwaProgram, description: str) -> None:
    """추출한 자격을 프로그램에 반영(불확실하면 기존값 유지)."""
    el = parse_eligibility(description)
    p.eligibility_grade = el["grade"]
    p.eligibility_major = el["major"]
    if el["note"]:
        note = f"대상: {el['note']}"
        p.eligibility_note = f"{p.eligibility_note} | {note}" if p.eligibility_note else note


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
                p.eligibility_grade, p.eligibility_major,
            ]
        )
    )


def _finalize(p: BigyogwaProgram) -> BigyogwaProgram:
    """현재 필드(설명 포함)로 embedding_text·text·content_hash를 확정."""
    p.embedding_text = _embedding_text(p)
    p.text = p.embedding_text
    p.content_hash = _content_hash(p)
    return p
