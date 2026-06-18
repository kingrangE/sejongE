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
        # 자격(학년): Chroma where로 필터 가능하도록 불리언 플래그로 투영한다.
        #  - 제한 없음(빈 리스트 = 전체) → elig_grade_any=True
        #  - 특정 학년만 허용            → elig_grade_{N}=True (N ∈ 1..4)
        # CSV로 저장하면 Chroma 메타 필터에서 부분일치를 못 하므로 플래그로 둔다.
        # 질의 시 "전체이거나 내 학년 허용"을 $or로 표현한다(to_chroma_where 참고).
        if doc.eligibility_grade:
            for g in doc.eligibility_grade:
                meta[f"elig_grade_{g}"] = True
        else:
            meta["elig_grade_any"] = True
        # 전공: 표기 흔들림(예: '자유전공학부' vs '자유전공학부생')이 커서 v1은
        # 하드필터하지 않고 정보용으로만 적재한다(랭킹에 맡김 — 오탐 배제 방지).
        if doc.eligibility_major:
            meta["eligibility_major_csv"] = ",".join(doc.eligibility_major)
    if isinstance(doc, CalendarEvent):
        if doc.start_epoch_day is not None:
            meta["start_epoch_day"] = doc.start_epoch_day
        if doc.end_epoch_day is not None:
            meta["end_epoch_day"] = doc.end_epoch_day
    return meta


def passes_filter(meta: dict, f: RetrievalFilter | None) -> bool:
    """to_chroma_where와 동일한 하드 필터를 파이썬에서 평가(BM25 후보 필터링용)."""
    if f is None:
        return True
    if f.doc_type is not None and meta.get("doc_type") != f.doc_type.value:
        return False
    if f.only_open and f.as_of_epoch is not None:
        s, e = meta.get("apply_start_epoch"), meta.get("apply_end_epoch")
        if s is None or e is None or not (s <= f.as_of_epoch <= e):
            return False
    if f.grade is not None:
        # 전체(any)이거나 사용자의 학년을 명시적으로 허용하는 문서만 통과
        if not (meta.get("elig_grade_any") or meta.get(f"elig_grade_{f.grade}")):
            return False
    if f.date_lte is not None:
        s = meta.get("start_epoch_day")
        if s is None or not (s <= f.date_lte):
            return False
    if f.date_gte is not None:
        e = meta.get("end_epoch_day")
        if e is None or not (e >= f.date_gte):
            return False
    for k, v in f.extra_eq.items():
        if meta.get(k) != v:
            return False
    return True


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

    # 비교과 자격(학년): 전체(any)이거나 사용자의 학년을 허용하는 프로그램만
    if f.grade is not None:
        clauses.append({"$or": [{"elig_grade_any": True}, {f"elig_grade_{f.grade}": True}]})

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
