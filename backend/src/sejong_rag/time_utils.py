"""KST 기준 시간 처리 + 한국어 상대 날짜 표현 해석.

- 모든 시간 로직은 KST(Asia/Seoul)에 고정한다.
- 벡터DB 메타데이터 범위 필터를 위해 날짜를 epoch-day(1970-01-01 기준 일수) 정수로 저장한다.
- "오늘 / 이번 주 / 지금 신청 가능한" 같은 표현은 질의 시점(as_of)에 대해 해석한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
_EPOCH = date(1970, 1, 1)


# --------------------------------------------------------------------------- #
# 기본 시각
# --------------------------------------------------------------------------- #
def now_kst() -> datetime:
    return datetime.now(tz=KST)


def today_kst() -> date:
    return now_kst().date()


# --------------------------------------------------------------------------- #
# epoch-day 변환 (벡터DB 정수 범위 필터용)
# --------------------------------------------------------------------------- #
def epoch_day(d: date) -> int:
    """1970-01-01을 0으로 하는 일수."""
    return (d - _EPOCH).days


def date_from_epoch_day(n: int) -> date:
    return _EPOCH + timedelta(days=n)


# --------------------------------------------------------------------------- #
# 기간 경계
# --------------------------------------------------------------------------- #
def week_bounds(d: date) -> tuple[date, date]:
    """월요일~일요일 (한국 통념)."""
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)


def month_bounds(d: date) -> tuple[date, date]:
    first = d.replace(day=1)
    if d.month == 12:
        nxt = first.replace(year=d.year + 1, month=1)
    else:
        nxt = first.replace(month=d.month + 1)
    return first, nxt - timedelta(days=1)


def semester_of(d: date) -> str:
    """한국 대학 학기 라벨. 1학기(3-6) / 여름(7-8) / 2학기(9-12) / 겨울(1-2)."""
    m = d.month
    if 3 <= m <= 6:
        return f"{d.year}-1"
    if 7 <= m <= 8:
        return f"{d.year}-여름"
    if 9 <= m <= 12:
        return f"{d.year}-2"
    return f"{d.year}-겨울"  # 1-2월


# --------------------------------------------------------------------------- #
# 날짜 범위 + 상대 표현 해석
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DateRange:
    start: date
    end: date

    @property
    def start_epoch_day(self) -> int:
        return epoch_day(self.start)

    @property
    def end_epoch_day(self) -> int:
        return epoch_day(self.end)

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end


# (정규식, 범위 생성 함수) — 더 구체적인 표현을 먼저 매칭
_RELATIVE_RULES: list[tuple[re.Pattern[str], object]] = [
    (re.compile(r"그저께|그제"), lambda t: DateRange(t - timedelta(days=2), t - timedelta(days=2))),
    (re.compile(r"모레"), lambda t: DateRange(t + timedelta(days=2), t + timedelta(days=2))),
    (re.compile(r"내일"), lambda t: DateRange(t + timedelta(days=1), t + timedelta(days=1))),
    (re.compile(r"어제"), lambda t: DateRange(t - timedelta(days=1), t - timedelta(days=1))),
    (re.compile(r"오늘|지금|현재|당장"), lambda t: DateRange(t, t)),
    (re.compile(r"다음\s*주|담주|차주"), lambda t: _shift_week(t, +1)),
    (re.compile(r"지난\s*주|저번\s*주"), lambda t: _shift_week(t, -1)),
    (re.compile(r"이번\s*주|금주"), lambda t: DateRange(*week_bounds(t))),
    (re.compile(r"다음\s*달|담달"), lambda t: _shift_month(t, +1)),
    (re.compile(r"지난\s*달|저번\s*달"), lambda t: _shift_month(t, -1)),
    (re.compile(r"이번\s*달|이달|금월"), lambda t: DateRange(*month_bounds(t))),
    (re.compile(r"올해|금년"), lambda t: DateRange(date(t.year, 1, 1), date(t.year, 12, 31))),
]


def _shift_week(t: date, weeks: int) -> DateRange:
    return DateRange(*week_bounds(t + timedelta(weeks=weeks)))


def _shift_month(t: date, months: int) -> DateRange:
    # 해당 달의 임의 날짜를 만든 뒤 month_bounds로 정규화
    y, m = t.year, t.month + months
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return DateRange(*month_bounds(date(y, m, 1)))


def resolve_relative(text: str, as_of: date | None = None) -> DateRange | None:
    """한국어 상대 날짜 표현을 DateRange로 해석한다. 없으면 None."""
    t = as_of or today_kst()
    for pattern, builder in _RELATIVE_RULES:
        if pattern.search(text):
            return builder(t)  # type: ignore[operator]
    return None
