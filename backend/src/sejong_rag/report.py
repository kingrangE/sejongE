"""수집 점검 리포트 — 파싱/적재된 문서를 사람이 검수할 수 있게 Markdown으로 렌더.

API 키 없이 동작(파싱 결과 또는 SQLite 활성 문서 기반). 실제 사이트와 대조해
"잘 수집되는지"를 눈으로 확인하는 용도.
"""

from __future__ import annotations

from sejong_rag.models import BigyogwaProgram, CalendarEvent, LabDoc, ProgramStatus, compute_status
from sejong_rag.time_utils import epoch_day, today_kst

_STATUS_KO = {
    ProgramStatus.OPEN: "🟢 접수중",
    ProgramStatus.UPCOMING: "🔵 접수예정",
    ProgramStatus.CLOSED: "⚪ 마감",
}


def _status_label(p: BigyogwaProgram, as_of_epoch: int) -> str:
    if p.apply_start_epoch is None and p.apply_end_epoch is None:
        return "—"
    return _STATUS_KO[compute_status(p.apply_start_epoch, p.apply_end_epoch, as_of_epoch)]


def _fmt_range(a, b) -> str:
    if a and b:
        return f"{a} ~ {b}"
    return "—"


def _fmt_recruit(p: BigyogwaProgram) -> str:
    if p.applied_count is None:
        return "—"
    cap = "무제한" if p.capacity is None else str(p.capacity)
    return f"{p.applied_count}/{cap}"


def render_bigyogwa_markdown(programs: list[BigyogwaProgram], source: str = "parse") -> str:
    today = today_kst()
    as_of = epoch_day(today)
    lines: list[str] = []
    lines.append("# 비교과 수집 점검 리포트")
    lines.append("")
    lines.append(f"- 소스: `{source}`")
    lines.append(f"- 기준일(as_of): **{today}** — 상태 계산 기준")
    lines.append(f"- 수집 건수: **{len(programs)}건**")
    lines.append("")
    open_n = sum(1 for p in programs if _status_label(p, as_of).startswith("🟢"))
    lines.append(f"- 현재 접수중: **{open_n}건**")
    lines.append("")
    lines.append("## 요약 표")
    lines.append("")
    lines.append("| # | 프로그램명 | 운영기관 | 신청기간 | 상태 | 모집현황 | 마일리지 | 원본 |")
    lines.append("|--:|---|---|---|---|---|--:|---|")
    for i, p in enumerate(programs, 1):
        name = (p.program_name or "—").replace("|", "丨")
        org = (p.organizer or "—").replace("|", "丨")
        lines.append(
            f"| {i} | {name} | {org} | {_fmt_range(p.apply_start, p.apply_end)} | "
            f"{_status_label(p, as_of)} | {_fmt_recruit(p)} | "
            f"{f'+{p.mileage}' if p.mileage else '—'} | [열기]({p.source_url}) |"
        )
    lines.append("")
    lines.append("## 상세 (임베딩 텍스트 — 검색에 실제 쓰이는 내용)")
    lines.append("")
    for i, p in enumerate(programs, 1):
        lines.append(f"### {i}. {p.program_name or '(제목 없음)'}")
        lines.append(f"- 원본: {p.source_url}")
        lines.append(f"- 운영기간: {_fmt_range(p.event_start, p.event_end)}")
        if p.eligibility_note:
            lines.append(f"- 비고: {p.eligibility_note}")
        lines.append("")
        lines.append("```")
        lines.append(p.embedding_text)
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def render_calendar_markdown(events: list[CalendarEvent], source: str = "parse") -> str:
    today = today_kst()
    evs = sorted(events, key=lambda e: (e.start_epoch_day or 0))
    lines: list[str] = []
    lines.append("# 학사일정 수집 점검 리포트")
    lines.append("")
    lines.append(f"- 소스: `{source}`")
    lines.append(f"- 기준일: **{today}**")
    lines.append(f"- 수집 건수: **{len(evs)}건**")
    lines.append("")
    lines.append("| # | 기간 | 일정 | 분류 | 학기 |")
    lines.append("|--:|---|---|---|---|")
    for i, e in enumerate(evs, 1):
        period = f"{e.start_date}" if e.start_date == e.end_date else f"{e.start_date} ~ {e.end_date}"
        title = (e.title or "—").replace("|", "丨")
        lines.append(f"| {i} | {period} | {title} | {e.category} | {e.semester} |")
    return "\n".join(lines)


def render_labs_markdown(labs: list[LabDoc], source: str = "parse") -> str:
    by_dept: dict[str, list[LabDoc]] = {}
    for d in labs:
        by_dept.setdefault(d.department or "(학과미상)", []).append(d)
    lines: list[str] = []
    lines.append("# 연구실/교수 수집 점검 리포트")
    lines.append("")
    lines.append(f"- 소스: `{source}`")
    lines.append(f"- 단과대: {labs[0].college if labs else '—'}")
    lines.append(f"- 학과 수: **{len(by_dept)}**, 교수 수: **{len(labs)}**")
    lines.append("")
    lines.append("| # | 교수 | 학과 | 연구분야 | 연구실 홈 |")
    lines.append("|--:|---|---|---|---|")
    i = 0
    for dept, members in by_dept.items():
        for d in members:
            i += 1
            areas = ", ".join(d.research_areas[:4]).replace("|", "丨") or "—"
            home = f"[링크]({d.homepage_url})" if d.homepage_url else "—"
            lines.append(f"| {i} | {d.professor_name} | {dept} | {areas} | {home} |")
    return "\n".join(lines)
