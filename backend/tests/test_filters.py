"""RetrievalFilter → Chroma where 변환 + 메타데이터 투영 검증."""

from datetime import date

from sejong_rag.models import BigyogwaProgram, DocType
from sejong_rag.retrieve.filters import doc_to_metadata, to_chroma_where
from sejong_rag.retrieve.retriever import RetrievalFilter
from sejong_rag.time_utils import epoch_day


def test_none_filter():
    assert to_chroma_where(None) is None
    assert to_chroma_where(RetrievalFilter()) is None


def test_doc_type_only():
    where = to_chroma_where(RetrievalFilter(doc_type=DocType.BIGYOGWA))
    assert where == {"doc_type": "bigyogwa"}


def test_only_open_builds_apply_window():
    as_of = epoch_day(date(2026, 6, 17))
    where = to_chroma_where(RetrievalFilter(doc_type=DocType.BIGYOGWA, only_open=True, as_of_epoch=as_of))
    assert "$and" in where
    conds = where["$and"]
    assert {"doc_type": "bigyogwa"} in conds
    assert {"apply_start_epoch": {"$lte": as_of}} in conds
    assert {"apply_end_epoch": {"$gte": as_of}} in conds


def test_calendar_date_overlap():
    lo, hi = epoch_day(date(2026, 6, 15)), epoch_day(date(2026, 6, 21))
    where = to_chroma_where(RetrievalFilter(date_gte=lo, date_lte=hi))
    conds = where["$and"]
    assert {"start_epoch_day": {"$lte": hi}} in conds
    assert {"end_epoch_day": {"$gte": lo}} in conds


def test_metadata_projection_bigyogwa():
    p = BigyogwaProgram(
        id="x", source_url="https://do.sejong.ac.kr/ko/program/all/view/1",
        source_site="bigyogwa", crawled_at="t", content_hash="h",
        program_name="P", apply_start=date(2026, 6, 10), apply_end=date(2026, 6, 20),
        apply_start_epoch=epoch_day(date(2026, 6, 10)), apply_end_epoch=epoch_day(date(2026, 6, 20)),
    )
    meta = doc_to_metadata(p)
    assert meta["doc_type"] == "bigyogwa"
    assert meta["apply_start_epoch"] == epoch_day(date(2026, 6, 10))
    # 전체(빈 리스트) 자격은 메타데이터에 표식 없음
    assert "eligibility_grade_csv" not in meta
    # 모든 값이 스칼라(Chroma 제약)
    assert all(isinstance(v, (str, int, float, bool)) for v in meta.values())
