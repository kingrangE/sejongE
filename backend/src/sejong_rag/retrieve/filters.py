"""RetrievalFilter → Chroma `where` 절 변환 + 문서 메타데이터 투영.

하드 필터(시간/자격)는 랭킹 방식과 무관하게 항상 적용된다.
Chroma 메타데이터는 스칼라만 허용하므로 날짜는 epoch-day(int)로 저장한다.
"""

from __future__ import annotations

from sejong_rag.models import BaseDoc, BigyogwaProgram, CalendarEvent
from sejong_rag.retrieve.retriever import RetrievalFilter


def doc_to_metadata(doc: BaseDoc) -> dict:
    """벡터DB에 함께 저장할 스칼라 메타데이터."""
    meta: dict = {
        "doc_type": doc.doc_type.value,
        "source_url": doc.source_url,
        "source_site": doc.source_site,
        "modality": doc.modality.value,
    }
    if doc.original_ref:
        meta["original_ref"] = doc.original_ref
    if isinstance(doc, BigyogwaProgram):
        if doc.apply_start_epoch is not None:
            meta["apply_start_epoch"] = doc.apply_start_epoch
        if doc.apply_end_epoch is not None:
            meta["apply_end_epoch"] = doc.apply_end_epoch
        # 자격: 빈 리스트(=전체)는 표식 없이, 제한 있으면 CSV로
        if doc.eligibility_grade:
            meta["eligibility_grade_csv"] = ",".join(map(str, doc.eligibility_grade))
        if doc.eligibility_major:
            meta["eligibility_major_csv"] = ",".join(doc.eligibility_major)
    if isinstance(doc, CalendarEvent):
        if doc.start_epoch_day is not None:
            meta["start_epoch_day"] = doc.start_epoch_day
        if doc.end_epoch_day is not None:
            meta["end_epoch_day"] = doc.end_epoch_day
    return meta


def to_chroma_where(f: RetrievalFilter | None) -> dict | None:
    """RetrievalFilter → Chroma where dict. 조건 없으면 None."""
    if f is None:
        return None
    clauses: list[dict] = []

    if f.doc_type is not None:
        clauses.append({"doc_type": f.doc_type.value})

    # 비교과 "지금 신청 가능": as_of가 신청기간 내 (start<=as_of<=end)
    if f.only_open and f.as_of_epoch is not None:
        clauses.append({"apply_start_epoch": {"$lte": f.as_of_epoch}})
        clauses.append({"apply_end_epoch": {"$gte": f.as_of_epoch}})

    # 학사일정 날짜 범위 겹침: start<=date_lte AND end>=date_gte
    if f.date_lte is not None:
        clauses.append({"start_epoch_day": {"$lte": f.date_lte}})
    if f.date_gte is not None:
        clauses.append({"end_epoch_day": {"$gte": f.date_gte}})

    for k, v in f.extra_eq.items():
        clauses.append({k: v})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}
