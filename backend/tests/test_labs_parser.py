"""연구실/교수 파서 — 실제 API JSON + 학과 페이지 픽스처."""

import json
from pathlib import Path

import pytest

from sejong_rag.ingest.sites.labs import extract_api_params, parse_professors

FX = Path(__file__).parent / "fixtures"
JSON_FX = FX / "professor_cse.json"
HTML_FX = FX / "dept_cse.html"

pytestmark = pytest.mark.skipif(not JSON_FX.exists(), reason="픽스처 없음")


def _items():
    return json.loads(JSON_FX.read_text(encoding="utf-8"))["items"]


def test_parse_professors_basic():
    docs = parse_professors(_items(), source_url="https://www.sejong.ac.kr/kor/college/computer-science-and-engineering.do", crawled_at="t")
    assert len(docs) >= 20
    d = docs[0]
    assert d.professor_name
    assert d.college == "인공지능융합대학"
    assert d.source_site == "labs"


def test_research_areas_split():
    docs = parse_professors(_items(), source_url="u", crawled_at="t")
    # 적어도 한 교수는 연구분야가 콤마로 분리되어 리스트화
    assert any(len(d.research_areas) >= 2 for d in docs)
    # 연구분야가 임베딩 텍스트에 포함
    assert any("연구분야:" in d.embedding_text for d in docs)


def test_homepage_captured_when_present():
    docs = parse_professors(_items(), source_url="u", crawled_at="t")
    # homepage가 있는 교수가 있으면 homepage_url에 반영
    items = _items()
    if any((it.get("homepage1") or it.get("homepage2") or "").strip() for it in items):
        assert any(d.homepage_url for d in docs)


def test_ids_unique_deterministic():
    a = parse_professors(_items(), source_url="u", crawled_at="t")
    b = parse_professors(_items(), source_url="u", crawled_at="t")
    assert [d.id for d in a] == [d.id for d in b]
    assert len({d.id for d in a}) == len(a)


@pytest.mark.skipif(not HTML_FX.exists(), reason="학과 HTML 픽스처 없음")
def test_extract_api_params():
    params = extract_api_params(HTML_FX.read_text(encoding="utf-8"))
    assert params is not None
    assert params["deptNo"]  # 학과 번호 추출
    assert params["siteId"] == "kor"
