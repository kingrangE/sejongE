"""ETL 멱등성/변경감지/소프트삭제 — 가짜 embedder·vectorstore + 실제 SQLite·파서."""

from pathlib import Path

import pytest

from sejong_rag.index.build_index import run_etl
from sejong_rag.index.store import DocumentStore
from sejong_rag.ingest.sites.bigyogwa import parse_list

FIXTURE = Path(__file__).parent / "fixtures" / "bigyogwa_list.html"
pytestmark = pytest.mark.skipif(not FIXTURE.exists(), reason="픽스처 없음")


class FakeEmbedder:
    def __init__(self):
        self.calls = 0
        self.total = 0

    def embed(self, texts):
        self.calls += 1
        self.total += len(texts)
        return [[float(len(t)), 1.0, 0.0] for t in texts]


class FakeVectorStore:
    def __init__(self):
        self.store = {}
        self.deleted = []

    def upsert(self, ids, embeddings, documents, metadatas):
        for i, e, d, m in zip(ids, embeddings, documents, metadatas):
            self.store[i] = (e, d, m)

    def delete(self, ids):
        for i in ids:
            self.deleted.append(i)
            self.store.pop(i, None)


def _docs():
    return parse_list(FIXTURE.read_text(encoding="utf-8"), crawled_at="2026-06-17T00:00:00+09:00")


def _run(docs, store, emb, vs, run_id):
    return run_etl(docs, store=store, embedder=emb, vectorstore=vs, site="bigyogwa",
                   run_id=run_id, started_at="2026-06-17T00:00:00+09:00")


def test_first_run_embeds_all(tmp_path):
    store, emb, vs = DocumentStore(tmp_path / "t.sqlite"), FakeEmbedder(), FakeVectorStore()
    docs = _docs()
    stats = _run(docs, store, emb, vs, "r1")
    assert stats.new == len(docs)
    assert stats.embedded == len(docs)
    assert len(vs.store) == len(docs)
    store.close()


def test_second_run_is_idempotent(tmp_path):
    store, emb, vs = DocumentStore(tmp_path / "t.sqlite"), FakeEmbedder(), FakeVectorStore()
    docs = _docs()
    _run(docs, store, emb, vs, "r1")
    emb_before = emb.total
    stats = _run(_docs(), store, emb, vs, "r2")
    # 두 번째 실행: 전부 UNCHANGED → 재임베딩 0
    assert stats.unchanged == len(docs)
    assert stats.embedded == 0
    assert emb.total == emb_before
    store.close()


def test_changed_doc_reembeds_only_one(tmp_path):
    store, emb, vs = DocumentStore(tmp_path / "t.sqlite"), FakeEmbedder(), FakeVectorStore()
    docs = _docs()
    _run(docs, store, emb, vs, "r1")

    docs2 = _docs()
    docs2[0].content_hash = "DELIBERATELY_CHANGED"
    stats = _run(docs2, store, emb, vs, "r2")
    assert stats.changed == 1
    assert stats.embedded == 1
    store.close()


def test_missing_doc_soft_deleted(tmp_path):
    store, emb, vs = DocumentStore(tmp_path / "t.sqlite"), FakeEmbedder(), FakeVectorStore()
    docs = _docs()
    _run(docs, store, emb, vs, "r1")

    dropped = docs[0].id
    stats = _run(docs[1:], store, emb, vs, "r2")  # 첫 문서 사라짐
    assert stats.deleted == 1
    assert dropped in vs.deleted
    assert store.count_active("bigyogwa") == len(docs) - 1
    store.close()
