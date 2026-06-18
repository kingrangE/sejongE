"""RetrievalFilter → Chroma where 변환 + 메타데이터 투영 검증."""

from datetime import date

from sejong_rag.models import BigyogwaProgram, DocType
from sejong_rag.retrieve.filters import doc_to_metadata, passes_filter, to_chroma_where
from sejong_rag.retrieve.retriever import RetrievalFilter
from sejong_rag.time_utils import epoch_day


def _program(grades=None):
    return BigyogwaProgram(
        id="x", source_url="https://do.sejong.ac.kr/ko/program/all/view/1",
        source_site="bigyogwa", crawled_at="t", content_hash="h", program_name="P",
        apply_start=date(2026, 6, 10), apply_end=date(2026, 6, 20),
        apply_start_epoch=epoch_day(date(2026, 6, 10)), apply_end_epoch=epoch_day(date(2026, 6, 20)),
        eligibility_grade=grades or [],
    )


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
    meta = doc_to_metadata(_program())
    assert meta["doc_type"] == "bigyogwa"
    assert meta["apply_start_epoch"] == epoch_day(date(2026, 6, 10))
    # 전체(빈 리스트) 자격은 'any' 플래그로 표시되고, 특정 학년 플래그는 없음
    assert meta.get("elig_grade_any") is True
    assert not any(k.startswith("elig_grade_") and k != "elig_grade_any" for k in meta)
    # 모든 값이 스칼라(Chroma 제약)
    assert all(isinstance(v, (str, int, float, bool)) for v in meta.values())


def test_metadata_projection_restricted_grade():
    meta = doc_to_metadata(_program(grades=[1, 2]))
    assert meta.get("elig_grade_1") is True
    assert meta.get("elig_grade_2") is True
    assert "elig_grade_any" not in meta  # 제한 있으면 any 없음
    assert "elig_grade_3" not in meta


def test_grade_filter_builds_or_clause():
    where = to_chroma_where(RetrievalFilter(doc_type=DocType.BIGYOGWA, grade=2))
    conds = where["$and"]
    assert {"doc_type": "bigyogwa"} in conds
    assert {"$or": [{"elig_grade_any": True}, {"elig_grade_2": True}]} in conds


def test_grade_filter_only_returns_or_directly():
    # grade만 있는 경우 $and로 감싸지 않고 $or 절을 바로 반환
    where = to_chroma_where(RetrievalFilter(grade=3))
    assert where == {"$or": [{"elig_grade_any": True}, {"elig_grade_3": True}]}


def test_passes_filter_grade():
    f = RetrievalFilter(grade=2)
    # 전체(any) 프로그램은 모든 학년 통과
    assert passes_filter(doc_to_metadata(_program()), f) is True
    # 1학년 한정 프로그램은 2학년 사용자에게 제외
    assert passes_filter(doc_to_metadata(_program(grades=[1])), f) is False
    # 2학년 포함 프로그램은 통과
    assert passes_filter(doc_to_metadata(_program(grades=[2, 3])), f) is True
    # 필터에 학년이 없으면 제한 없음
    assert passes_filter(doc_to_metadata(_program(grades=[1])), RetrievalFilter()) is True
