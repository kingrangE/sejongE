"""VectorRetriever — 임베딩+필터 검색 (가짜 embedder/vectorstore)."""

from sejong_rag.models import Candidate, DocType
from sejong_rag.retrieve.retriever import RetrievalFilter
from sejong_rag.retrieve.vector import VectorRetriever


class FakeEmbedder:
    def embed(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]


class FakeVectorStore:
    def __init__(self):
        self.last_where = None
        self.last_n = None

    def upsert(self, *a, **k):
        pass

    def delete(self, *a, **k):
        pass

    def query(self, embedding, where, n_results):
        self.last_where = where
        self.last_n = n_results
        return [Candidate(id="1", score=0.8, doc_type=DocType.BIGYOGWA, text="t", source_url="u")]


def test_search_returns_candidates_and_passes_where():
    vs = FakeVectorStore()
    r = VectorRetriever(FakeEmbedder(), vs)
    out = r.search("질문", RetrievalFilter(doc_type=DocType.BIGYOGWA), top_k=5)
    assert out and out[0].id == "1"
    assert vs.last_where == {"doc_type": "bigyogwa"}
    assert vs.last_n == 5


def test_empty_query_returns_empty():
    r = VectorRetriever(FakeEmbedder(), FakeVectorStore())
    assert r.search("   ") == []
