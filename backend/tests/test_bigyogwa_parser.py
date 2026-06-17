"""비교과 목록 파서 검증 — 저장된 실제 HTML 픽스처 사용."""

from datetime import date
from pathlib import Path

import pytest

from sejong_rag.ingest.sites.bigyogwa import parse_list

FIXTURE = Path(__file__).parent / "fixtures" / "bigyogwa_list.html"

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


def test_stable_id_deterministic():
    a = _parse()
    b = _parse()
    assert [p.id for p in a] == [p.id for p in b]
    assert len({p.id for p in a}) == 8  # 중복 없음
