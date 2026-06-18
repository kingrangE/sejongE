"""하이브리드 검색 — 토크나이저·BM25·필터 술어·RRF 융합."""

from datetime import date

from sejong_rag.models import Candidate, DocType
from sejong_rag.retrieve.bm25 import BM25Retriever
from sejong_rag.retrieve.filters import passes_filter
from sejong_rag.retrieve.hybrid import HybridRetriever
from sejong_rag.retrieve.retriever import RetrievalFilter, Retriever
from sejong_rag.retrieve.tokenize import simple_tokenize
from sejong_rag.time_utils import epoch_day


# --- passes_filter ---
def test_passes_filter_only_open():
    as_of = epoch_day(date(2026, 6, 18))
    meta = {"doc_type": "bigyogwa", "apply_start_epoch": epoch_day(date(2026, 6, 10)),
            "apply_end_epoch": epoch_day(date(2026, 6, 20))}
    f = RetrievalFilter(doc_type=DocType.BIGYOGWA, only_open=True, as_of_epoch=as_of)
    assert passes_filter(meta, f) is True
    meta_closed = {**meta, "apply_end_epoch": epoch_day(date(2026, 6, 15))}
    assert passes_filter(meta_closed, f) is False


def test_passes_filter_doc_type():
    assert passes_filter({"doc_type": "lab"}, RetrievalFilter(doc_type=DocType.LAB))
    assert not passes_filter({"doc_type": "calendar"}, RetrievalFilter(doc_type=DocType.LAB))


# --- tokenizer ---
def test_simple_tokenize_bigrams_and_words():
    toks = simple_tokenize("인공지능 AI Lab")
    assert "ai" in toks and "lab" in toks
    assert "인공" in toks and "공지" in toks  # 한글 bigram


# --- BM25 ---
def _corpus():
    return [
        {"id": "a", "text": "인공지능 자연어처리 연구실", "doc_type": "lab",
         "source_url": "u/a", "modality": "text", "metadata": {"doc_type": "lab"}},
        {"id": "b", "text": "로봇 제어 기계학습 연구실", "doc_type": "lab",
         "source_url": "u/b", "modality": "text", "metadata": {"doc_type": "lab"}},
        {"id": "c", "text": "도서관 스탬프 투어 비교과", "doc_type": "bigyogwa",
         "source_url": "u/c", "modality": "text", "metadata": {"doc_type": "bigyogwa"}},
    ]


def test_bm25_ranks_relevant_first():
    r = BM25Retriever(_corpus(), simple_tokenize)
    out = r.search("자연어처리 연구실", top_k=3)
    assert out and out[0].id == "a"


def test_bm25_filter_excludes():
    r = BM25Retriever(_corpus(), simple_tokenize)
    out = r.search("연구실", RetrievalFilter(doc_type=DocType.LAB), top_k=5)
    assert all(c.doc_type is DocType.LAB for c in out)
    assert "c" not in {c.id for c in out}


# --- RRF fusion ---
class _Fixed(Retriever):
    def __init__(self, ids):
        self._ids = ids

    def search(self, query, filters=None, top_k=8):
        return [Candidate(id=i, score=1.0, doc_type=DocType.LAB, text=i, source_url=f"u/{i}") for i in self._ids]


def test_hybrid_rrf_prefers_overlap():
    dense = _Fixed(["x", "y", "z"])
    sparse = _Fixed(["y", "w", "x"])
    out = HybridRetriever(dense, sparse).search("q", top_k=4)
    # x, y는 양쪽에 등장 → 상위
    assert set([out[0].id, out[1].id]) == {"x", "y"}
    ids = {c.id for c in out}
    assert "z" in ids and "w" in ids
