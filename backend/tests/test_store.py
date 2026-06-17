"""DocumentStore: 변경 분류(NEW/CHANGED/UNCHANGED)·소프트 삭제·멱등성 (sqlite stdlib)."""

from sejong_rag.index.store import ChangeKind, DocumentStore
from sejong_rag.models import BigyogwaProgram


def _doc(doc_id: str, content_hash: str, name: str = "프로그램") -> BigyogwaProgram:
    return BigyogwaProgram(
        id=doc_id,
        source_url=f"https://example.com/{doc_id}",
        source_site="bigyogwa",
        crawled_at="2026-06-17T00:00:00+09:00",
        content_hash=content_hash,
        program_name=name,
    )


def test_new_then_unchanged_then_changed(tmp_path):
    store = DocumentStore(tmp_path / "t.sqlite")

    assert store.upsert(_doc("a", "h1")).kind is ChangeKind.NEW
    # 동일 해시 재실행 → UNCHANGED (멱등)
    assert store.upsert(_doc("a", "h1")).kind is ChangeKind.UNCHANGED
    # 해시 변경 → CHANGED
    assert store.upsert(_doc("a", "h2", name="수정됨")).kind is ChangeKind.CHANGED

    payload = store.get_payload("a")
    assert payload["program_name"] == "수정됨"
    store.close()


def test_idempotent_full_run(tmp_path):
    store = DocumentStore(tmp_path / "t.sqlite")
    docs = [_doc("a", "h1"), _doc("b", "h1"), _doc("c", "h1")]

    first = [store.upsert(d).kind for d in docs]
    assert all(k is ChangeKind.NEW for k in first)

    # 두 번째 실행: 전부 UNCHANGED (재임베딩 0의 근거)
    second = [store.upsert(d).kind for d in docs]
    assert all(k is ChangeKind.UNCHANGED for k in second)
    assert store.count_active("bigyogwa") == 3
    store.close()


def test_soft_delete_missing(tmp_path):
    store = DocumentStore(tmp_path / "t.sqlite")
    for i in ("a", "b", "c"):
        store.upsert(_doc(i, "h1"))

    # 이번 크롤에서 a, b만 보임 → c 비활성화
    stale = store.deactivate_missing("bigyogwa", seen_ids=["a", "b"])
    assert stale == ["c"]
    assert store.count_active("bigyogwa") == 2

    # c가 다시 나타나면 재활성화
    store.upsert(_doc("c", "h1"))
    assert store.count_active("bigyogwa") == 3
    store.close()
