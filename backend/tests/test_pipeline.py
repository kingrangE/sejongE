"""파이프라인 — dead-letter 기록 + 디스패치."""

import pytest

from sejong_rag.config import get_settings
from sejong_rag.ingest.pipeline import crawl_site, dead_letter


def test_dead_letter_appends(tmp_path):
    s = get_settings().model_copy(update={"data_dir": tmp_path})
    dead_letter("bigyogwa", "boom", s)
    dead_letter("labs", "kaboom", s)
    log = tmp_path / "dead_letter.log"
    text = log.read_text(encoding="utf-8")
    assert "bigyogwa" in text and "labs" in text
    assert len(text.strip().splitlines()) == 2


def test_crawl_site_unknown_raises():
    with pytest.raises(ValueError):
        crawl_site("unknown", fetcher=None, crawled_at="t")
