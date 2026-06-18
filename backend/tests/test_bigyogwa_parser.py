"""비교과 목록 파서 검증 — 저장된 실제 HTML 픽스처 사용."""

from datetime import date
from pathlib import Path

import pytest

from sejong_rag.ingest.sites.bigyogwa import (
    crawl,
    list_page_url,
    parse_detail,
    parse_eligibility,
    parse_list,
)

FIXTURE = Path(__file__).parent / "fixtures" / "bigyogwa_list.html"
DETAIL_FIXTURE = Path(__file__).parent / "fixtures" / "bigyogwa_detail_4253.html"

pytestmark = pytest.mark.skipif(not FIXTURE.exists(), reason="픽스처 없음")


def _parse():
    return parse_list(FIXTURE.read_text(encoding="utf-8"), crawled_at="2026-06-17T00:00:00+09:00")


def test_parses_unique_cards():
    progs = _parse()
    # 목록에 위젯 중복 노출이 있어 id 기준 8개 고유 프로그램으로 정리됨
    assert len(progs) == 8
    assert len({p.id for p in progs}) == 8  # 중복 없음


def test_first_program_fields():
    progs = _parse()
    p = progs[0]
    assert "AI" in p.program_name and "해커톤" in p.program_name
    assert p.organizer  # 운영기관 비어있지 않음
    assert p.apply_start == date(2026, 6, 10)
    assert p.apply_end == date(2026, 6, 18)
    assert p.event_start == date(2026, 6, 24)
    assert p.event_end == date(2026, 6, 25)
    assert p.apply_start_epoch is not None and p.apply_end_epoch is not None
    assert p.source_url.endswith("/view/4246")
    assert p.mileage == 200


def test_capacity_parsed():
    progs = _parse()
    # 최소 한 건은 모집현황(applied/capacity)이 파싱되어야
    assert any(p.applied_count is not None for p in progs)
    # 무제한 케이스는 capacity=None, applied 존재
    unlimited = [p for p in progs if p.applied_count is not None and p.capacity is None]
    assert unlimited  # "/무제한" 케이스 존재


@pytest.mark.skipif(not DETAIL_FIXTURE.exists(), reason="상세 픽스처 없음")
def test_parse_detail_description():
    desc = parse_detail(DETAIL_FIXTURE.read_text(encoding="utf-8"))
    assert len(desc) > 50
    assert "영상" in desc  # 실제 설명 본문이 추출됨


def test_stable_id_deterministic():
    a = _parse()
    b = _parse()
    assert [p.id for p in a] == [p.id for p in b]
    assert len({p.id for p in a}) == 8  # 중복 없음


# --------------------------------------------------------------------------- #
# 페이지네이션 — 경로 세그먼트(/list/all/1/{page}), 정적 fetch로 동작
# --------------------------------------------------------------------------- #
def test_list_page_url_is_path_based():
    assert list_page_url(2) == "https://do.sejong.ac.kr/ko/program/all/list/all/1/2"
    assert "?page=" not in list_page_url(2)  # 과거 잘못된 쿼리 방식이 아님


class _FakeFetcher:
    """page1만 카드 제공, 이후는 빈 목록 → 종료조건(2연속 빈 페이지) 검증용."""

    def __init__(self, list_html: str):
        self.list_html = list_html
        self.list_calls: list[str] = []

    def fetch(self, url: str, *, site: str, cache_key: str | None = None) -> str:
        if "/list/" in url:
            self.list_calls.append(url)
            return self.list_html if url.endswith("/1") else "<ul class='columns-5'></ul>"
        return ""  # 상세 없음(with_detail=False로 호출)


def test_crawl_paginates_until_empty():
    f = _FakeFetcher(FIXTURE.read_text(encoding="utf-8"))
    progs = crawl(f, crawled_at="2026-06-17T00:00:00+09:00", with_detail=False)
    assert len(progs) == 8  # page1의 8개 고유 프로그램
    # page1(신규) → page2(빈) → page3(빈, 2연속) 후 종료. 무한 요청하지 않음
    assert f.list_calls[0].endswith("/1")
    assert len(f.list_calls) <= 4


def test_crawl_respects_explicit_max_pages():
    f = _FakeFetcher(FIXTURE.read_text(encoding="utf-8"))
    crawl(f, crawled_at="2026-06-17T00:00:00+09:00", max_pages=1, with_detail=False)
    assert len(f.list_calls) == 1  # 정수 지정 시 정확히 N페이지만


# --------------------------------------------------------------------------- #
# 자격(학년/전공) 추출 — 확신 높은 패턴만, 불확실하면 전체(빈값)
# --------------------------------------------------------------------------- #
def test_eligibility_freshman_only():
    el = parse_eligibility("○ 참여 대상 • 세종대학교 신입생 (재학생, 대학원생 참여 불가) ○ 운영방식")
    assert el["grade"] == [1]


def test_eligibility_grade_and_major_from_fixture():
    desc = parse_detail(DETAIL_FIXTURE.read_text(encoding="utf-8"))
    el = parse_eligibility(desc)
    assert el["grade"] == [1]
    assert "자유전공학부" in el["major"]


def test_eligibility_any_grade_marker_means_all():
    el = parse_eligibility("참여 대상 : 전공 고민이 많은 재학, 휴학생 (학년무관) 상담 방법")
    assert el["grade"] == []  # '학년무관' → 전체


def test_eligibility_no_target_section_is_empty():
    el = parse_eligibility("이 프로그램은 유익합니다. 많은 신청 바랍니다.")
    assert el["grade"] == [] and el["major"] == [] and el["note"] == ""
