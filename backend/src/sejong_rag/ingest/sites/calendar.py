"""학사일정 파서 — www.sejong.ac.kr/kor/academics/academic-calendar.do (공개 페이지).

로그인 포털 대신 공개 학사일정 페이지를 사용한다(정적 HTML).
구조: div.b-schedule-item > {div.b-schedule-date, div.b-schedule-content}
날짜는 "MM.DD ~ MM.DD" 또는 단일 "MM.DD", 연도는 selectedYear로 받는다.
"""

from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from sejong_rag.models import CalendarEvent
from sejong_rag.normalize.dedup import content_hash, stable_id
from sejong_rag.time_utils import epoch_day, semester_of

BASE_URL = "https://www.sejong.ac.kr"
PATH = "/kor/academics/academic-calendar.do"

_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})(?:\s*~\s*(\d{1,2})\.(\d{1,2}))?")

# 제목 키워드 → 분류
_CATEGORY_RULES = [
    ("수강", ("수강신청", "수강정정", "수강", "강의평가")),
    ("시험", ("시험", "고사")),
    ("등록", ("등록",)),
    ("방학", ("방학",)),
    ("학적", ("휴학", "복학", "휴·복학", "자퇴", "제적")),
    ("성적", ("성적",)),
    ("행사", ("입학식", "학위수여식", "개강", "종강", "축제", "행사", "오리엔테이션")),
]


def calendar_url(year: int) -> str:
    return f"{BASE_URL}{PATH}?mode=list&selectedYear={year}"


def _infer_category(title: str) -> str:
    for label, keywords in _CATEGORY_RULES:
        if any(k in title for k in keywords):
            return label
    return "기타"


def _parse_dates(text: str, year: int) -> tuple[date, date] | None:
    m = _DATE_RE.search(text)
    if not m:
        return None
    sm, sd = int(m.group(1)), int(m.group(2))
    start = date(year, sm, sd)
    if m.group(3):
        em, ed = int(m.group(3)), int(m.group(4))
        end_year = year + 1 if (em, ed) < (sm, sd) else year  # 연말연초 경계
        end = date(end_year, em, ed)
    else:
        end = start
    return start, end


def parse_calendar(html: str, year: int, crawled_at: str) -> list[CalendarEvent]:
    soup = BeautifulSoup(html, "lxml")
    url = calendar_url(year)
    events: list[CalendarEvent] = []
    seen: set[str] = set()
    for item in soup.select("div.b-schedule-item"):
        date_el = item.select_one("div.b-schedule-date")
        title_el = item.select_one("div.b-schedule-content")
        if not date_el or not title_el:
            continue
        title = title_el.get_text(" ", strip=True)
        parsed = _parse_dates(date_el.get_text(" ", strip=True), year)
        if not title or not parsed:
            continue
        start, end = parsed
        key = f"{start}-{end}-{title}"
        if key in seen:
            continue
        seen.add(key)

        category = _infer_category(title)
        embedding_text = (
            f"{title}\n{semester_of(start)} 학사일정\n"
            f"기간: {start} ~ {end}\n분류: {category}"
        )
        events.append(
            CalendarEvent(
                id=stable_id(url, key=key),
                source_url=url,
                source_site="calendar",
                crawled_at=crawled_at,
                content_hash=content_hash(f"{key}|{category}"),
                text=embedding_text,
                embedding_text=embedding_text,
                title=title,
                start_date=start,
                end_date=end,
                start_epoch_day=epoch_day(start),
                end_epoch_day=epoch_day(end),
                semester=semester_of(start),
                category=category,
            )
        )
    return events


def crawl(fetcher, crawled_at: str, year: int) -> list[CalendarEvent]:
    html = fetcher.fetch(calendar_url(year), site="calendar", cache_key=f"calendar_{year}")
    return parse_calendar(html, year, crawled_at)
