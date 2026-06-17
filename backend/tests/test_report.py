"""점검 리포트 렌더러 검증 (네트워크 불필요)."""

from datetime import date

from sejong_rag.models import BigyogwaProgram
from sejong_rag.report import render_bigyogwa_markdown
from sejong_rag.time_utils import epoch_day


def _prog(**kw) -> BigyogwaProgram:
    base = dict(
        id="x", source_url="https://do.sejong.ac.kr/ko/program/all/view/1",
        source_site="bigyogwa", crawled_at="t", content_hash="h",
        program_name="테스트 프로그램", organizer="학술정보원",
    )
    base.update(kw)
    return BigyogwaProgram(**base)


def test_report_has_summary_and_links():
    progs = [_prog(apply_start=date(2026, 6, 10), apply_end=date(2026, 6, 20),
                   apply_start_epoch=epoch_day(date(2026, 6, 10)),
                   apply_end_epoch=epoch_day(date(2026, 6, 20)),
                   applied_count=10, capacity=100, mileage=50)]
    md = render_bigyogwa_markdown(progs, source="test")
    assert "비교과 수집 점검 리포트" in md
    assert "테스트 프로그램" in md
    assert "https://do.sejong.ac.kr/ko/program/all/view/1" in md
    assert "10/100" in md
    assert "+50" in md


def test_pipe_in_name_escaped():
    md = render_bigyogwa_markdown([_prog(program_name="A|B")], source="test")
    # 표가 깨지지 않도록 파이프 치환
    assert "A丨B" in md


def test_unlimited_capacity():
    md = render_bigyogwa_markdown([_prog(applied_count=5, capacity=None)], source="test")
    assert "5/무제한" in md
