"""SQLite 문서 저장소 — 진실 원천(source of truth).

- 문서를 `id` 기준으로 upsert하고, `content_hash`로 변경 여부를 분류한다(NEW/CHANGED/UNCHANGED).
- 소스에서 사라진 문서는 소프트 삭제(is_active=False)한다.
- ETL 실행 이력(run_ledger)을 기록한다(관찰 가능성).
표준 라이브러리 sqlite3만 사용 → 외부 의존성 없이 동작/테스트 가능.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

from sejong_rag.models import BaseDoc


class ChangeKind(str, Enum):
    NEW = "new"
    CHANGED = "changed"
    UNCHANGED = "unchanged"


@dataclass
class UpsertResult:
    kind: ChangeKind
    doc_id: str


_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id            TEXT PRIMARY KEY,
    doc_type      TEXT NOT NULL,
    source_url    TEXT NOT NULL,
    source_site   TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1,
    crawled_at    TEXT NOT NULL,
    payload       TEXT NOT NULL  -- 전체 문서 JSON
);
CREATE INDEX IF NOT EXISTS idx_documents_site ON documents(source_site);
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(doc_type);

CREATE TABLE IF NOT EXISTS run_ledger (
    run_id      TEXT NOT NULL,
    site        TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    fetched     INTEGER DEFAULT 0,
    new         INTEGER DEFAULT 0,
    changed     INTEGER DEFAULT 0,
    deleted     INTEGER DEFAULT 0,
    errors      INTEGER DEFAULT 0,
    note        TEXT
);
"""


class DocumentStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ----------------------------------------------------------------- #
    # 변경 분류 + upsert
    # ----------------------------------------------------------------- #
    def classify(self, doc: BaseDoc) -> ChangeKind:
        row = self._conn.execute(
            "SELECT content_hash FROM documents WHERE id = ?", (doc.id,)
        ).fetchone()
        if row is None:
            return ChangeKind.NEW
        return ChangeKind.UNCHANGED if row["content_hash"] == doc.content_hash else ChangeKind.CHANGED

    def upsert(self, doc: BaseDoc) -> UpsertResult:
        kind = self.classify(doc)
        if kind is ChangeKind.UNCHANGED:
            # 활성 상태만 보장하고 재기록하지 않음
            self._conn.execute(
                "UPDATE documents SET is_active = 1 WHERE id = ?", (doc.id,)
            )
            self._conn.commit()
            return UpsertResult(kind, doc.id)

        self._conn.execute(
            """
            INSERT INTO documents (id, doc_type, source_url, source_site, content_hash,
                                   is_active, crawled_at, payload)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                doc_type=excluded.doc_type,
                source_url=excluded.source_url,
                source_site=excluded.source_site,
                content_hash=excluded.content_hash,
                is_active=1,
                crawled_at=excluded.crawled_at,
                payload=excluded.payload
            """,
            (
                doc.id,
                doc.doc_type.value,
                doc.source_url,
                doc.source_site,
                doc.content_hash,
                doc.crawled_at,
                doc.model_dump_json(),
            ),
        )
        self._conn.commit()
        return UpsertResult(kind, doc.id)

    # ----------------------------------------------------------------- #
    # 소프트 삭제 (소스에서 사라진 항목)
    # ----------------------------------------------------------------- #
    def active_ids(self, site: str) -> set[str]:
        rows = self._conn.execute(
            "SELECT id FROM documents WHERE source_site = ? AND is_active = 1", (site,)
        ).fetchall()
        return {r["id"] for r in rows}

    def deactivate_missing(self, site: str, seen_ids: Iterable[str]) -> list[str]:
        """이번 크롤에서 보이지 않은 활성 문서를 비활성화하고 그 id를 반환."""
        seen = set(seen_ids)
        stale = [i for i in self.active_ids(site) if i not in seen]
        for doc_id in stale:
            self._conn.execute("UPDATE documents SET is_active = 0 WHERE id = ?", (doc_id,))
        self._conn.commit()
        return stale

    # ----------------------------------------------------------------- #
    # 조회
    # ----------------------------------------------------------------- #
    def get_payload(self, doc_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT payload FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def active_payloads(self, site: str) -> list[dict]:
        """해당 사이트의 활성 문서 payload(JSON) 목록 — 점검/덤프용."""
        rows = self._conn.execute(
            "SELECT payload FROM documents WHERE source_site = ? AND is_active = 1 ORDER BY id",
            (site,),
        ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    def count_active(self, site: str | None = None) -> int:
        if site:
            row = self._conn.execute(
                "SELECT COUNT(*) c FROM documents WHERE is_active = 1 AND source_site = ?",
                (site,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) c FROM documents WHERE is_active = 1"
            ).fetchone()
        return row["c"]

    # ----------------------------------------------------------------- #
    # 실행 이력
    # ----------------------------------------------------------------- #
    def record_run(
        self,
        run_id: str,
        site: str,
        started_at: str,
        finished_at: str | None = None,
        *,
        fetched: int = 0,
        new: int = 0,
        changed: int = 0,
        deleted: int = 0,
        errors: int = 0,
        note: str | None = None,
    ) -> None:
        self._conn.execute(
            """INSERT INTO run_ledger
               (run_id, site, started_at, finished_at, fetched, new, changed, deleted, errors, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, site, started_at, finished_at, fetched, new, changed, deleted, errors, note),
        )
        self._conn.commit()
