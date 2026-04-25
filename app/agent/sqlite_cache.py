from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from app.config import settings

log = logging.getLogger(__name__)

DB_PATH = settings.cache_dir / "apollo_cache.db"
_CONN_LOCK = threading.Lock()


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_payload(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hash_text(payload)


def normalize_query(value: str) -> str:
    return " ".join(value.lower().strip().split())


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    try:
        with _CONN_LOCK, _get_conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS pubmed_cache (
                    patient_id TEXT,
                    query TEXT,
                    papers JSON,
                    updated_at REAL DEFAULT (unixepoch()),
                    PRIMARY KEY (patient_id, query)
                );

                CREATE TABLE IF NOT EXISTS rag_answer_cache (
                    patient_id TEXT,
                    question TEXT,
                    answer_data JSON,
                    updated_at REAL DEFAULT (unixepoch()),
                    PRIMARY KEY (patient_id, question)
                );

                CREATE TABLE IF NOT EXISTS summary_cache (
                    patient_id TEXT,
                    content_hash TEXT,
                    summary_data JSON,
                    updated_at REAL DEFAULT (unixepoch()),
                    PRIMARY KEY (patient_id, content_hash)
                );

                CREATE TABLE IF NOT EXISTS node_cache (
                    namespace TEXT,
                    cache_key TEXT,
                    payload JSON,
                    updated_at REAL DEFAULT (unixepoch()),
                    PRIMARY KEY (namespace, cache_key)
                );

                CREATE TABLE IF NOT EXISTS indexed_documents (
                    patient_id TEXT,
                    source_doc TEXT,
                    content_hash TEXT,
                    chunk_count INTEGER DEFAULT 0,
                    updated_at REAL DEFAULT (unixepoch()),
                    PRIMARY KEY (patient_id, source_doc)
                );

                CREATE TABLE IF NOT EXISTS chunk_cache (
                    chunk_key TEXT PRIMARY KEY,
                    patient_id TEXT NOT NULL,
                    source_doc TEXT NOT NULL,
                    doc_type TEXT,
                    page INTEGER,
                    chunk_index INTEGER,
                    text TEXT NOT NULL,
                    updated_at REAL DEFAULT (unixepoch())
                );

                CREATE INDEX IF NOT EXISTS idx_chunk_cache_patient
                    ON chunk_cache(patient_id, doc_type, source_doc);

                CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts
                USING fts5(
                    chunk_key UNINDEXED,
                    patient_id UNINDEXED,
                    source_doc UNINDEXED,
                    doc_type UNINDEXED,
                    text,
                    tokenize = 'porter unicode61'
                );
                """
            )
    except Exception as exc:
        log.error("[sqlite_cache] Init error: %s", exc)


init_db()


def _is_fresh(updated_at: float | None, max_age_seconds: int | None) -> bool:
    if max_age_seconds is None or updated_at is None:
        return True
    try:
        updated = float(updated_at)
    except (TypeError, ValueError):
        try:
            updated = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00")).timestamp()
        except ValueError:
            return False
    return (time.time() - updated) <= max_age_seconds


def _get_json_row(
    table: str,
    key_fields: dict[str, Any],
    value_field: str,
    *,
    max_age_seconds: int | None = None,
) -> Any | None:
    where = " AND ".join(f"{name} = ?" for name in key_fields)
    params = list(key_fields.values())
    sql = f"SELECT {value_field}, updated_at FROM {table} WHERE {where}"
    try:
        with _CONN_LOCK, _get_conn() as conn:
            row = conn.execute(sql, params).fetchone()
        if not row or not _is_fresh(row["updated_at"], max_age_seconds):
            return None
        return json.loads(row[value_field])
    except Exception as exc:
        log.error("[sqlite_cache] read error from %s: %s", table, exc)
        return None


def _set_json_row(
    table: str,
    key_fields: dict[str, Any],
    value_field: str,
    value: Any,
) -> None:
    columns = [*key_fields.keys(), value_field, "updated_at"]
    placeholders = ", ".join("?" for _ in columns)
    updates = ", ".join(
        [f"{value_field} = excluded.{value_field}", "updated_at = excluded.updated_at"]
    )
    sql = f"""
        INSERT INTO {table} ({", ".join(columns)})
        VALUES ({placeholders})
        ON CONFLICT({", ".join(key_fields.keys())}) DO UPDATE SET {updates}
    """
    params = [*key_fields.values(), json.dumps(value, default=str), time.time()]
    try:
        with _CONN_LOCK, _get_conn() as conn:
            conn.execute(sql, params)
    except Exception as exc:
        log.error("[sqlite_cache] write error to %s: %s", table, exc)


def get_pubmed(patient_id: str, query: str, *, max_age_seconds: int | None = 7 * 24 * 3600) -> list | None:
    return _get_json_row(
        "pubmed_cache",
        {"patient_id": patient_id, "query": normalize_query(query)},
        "papers",
        max_age_seconds=max_age_seconds,
    )


def set_pubmed(patient_id: str, query: str, papers: list) -> None:
    _set_json_row(
        "pubmed_cache",
        {"patient_id": patient_id, "query": normalize_query(query)},
        "papers",
        papers,
    )


def get_answer(patient_id: str, question: str, *, max_age_seconds: int | None = 7 * 24 * 3600) -> dict | None:
    return _get_json_row(
        "rag_answer_cache",
        {"patient_id": patient_id, "question": normalize_query(question)},
        "answer_data",
        max_age_seconds=max_age_seconds,
    )


def set_answer(patient_id: str, question: str, answer_data: dict) -> None:
    _set_json_row(
        "rag_answer_cache",
        {"patient_id": patient_id, "question": normalize_query(question)},
        "answer_data",
        answer_data,
    )


def get_summary(patient_id: str, content_hash: str) -> dict | None:
    return _get_json_row(
        "summary_cache",
        {"patient_id": patient_id, "content_hash": content_hash},
        "summary_data",
        max_age_seconds=None,
    )


def set_summary(patient_id: str, content_hash: str, summary_data: dict) -> None:
    _set_json_row(
        "summary_cache",
        {"patient_id": patient_id, "content_hash": content_hash},
        "summary_data",
        summary_data,
    )


def get_node_cache(
    namespace: str,
    cache_key: str,
    *,
    max_age_seconds: int | None = 7 * 24 * 3600,
) -> dict | list | None:
    return _get_json_row(
        "node_cache",
        {"namespace": namespace, "cache_key": cache_key},
        "payload",
        max_age_seconds=max_age_seconds,
    )


def set_node_cache(namespace: str, cache_key: str, payload: dict | list) -> None:
    _set_json_row(
        "node_cache",
        {"namespace": namespace, "cache_key": cache_key},
        "payload",
        payload,
    )


def is_document_indexed(patient_id: str, source_doc: str, content_hash: str) -> bool:
    try:
        with _CONN_LOCK, _get_conn() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM indexed_documents
                WHERE patient_id = ? AND source_doc = ? AND content_hash = ?
                """,
                (patient_id, source_doc, content_hash),
            ).fetchone()
        return row is not None
    except Exception as exc:
        log.error("[sqlite_cache] is_document_indexed error: %s", exc)
        return False


def mark_document_indexed(
    patient_id: str,
    source_doc: str,
    content_hash: str,
    *,
    chunk_count: int,
) -> None:
    try:
        with _CONN_LOCK, _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO indexed_documents (patient_id, source_doc, content_hash, chunk_count, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(patient_id, source_doc) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    chunk_count = excluded.chunk_count,
                    updated_at = excluded.updated_at
                """,
                (patient_id, source_doc, content_hash, chunk_count, time.time()),
            )
    except Exception as exc:
        log.error("[sqlite_cache] mark_document_indexed error: %s", exc)


def upsert_chunk_records(chunks: Iterable[dict[str, Any]]) -> None:
    rows = [
        (
            chunk["chunk_id"],
            chunk["patient_id"],
            chunk["source_doc"],
            chunk.get("doc_type", "clinical_note"),
            chunk.get("page", 1),
            chunk.get("chunk_index", 0),
            chunk["text"],
            time.time(),
        )
        for chunk in chunks
        if chunk.get("chunk_id") and chunk.get("text")
    ]
    if not rows:
        return

    try:
        with _CONN_LOCK, _get_conn() as conn:
            conn.executemany(
                """
                INSERT INTO chunk_cache (
                    chunk_key, patient_id, source_doc, doc_type, page, chunk_index, text, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_key) DO UPDATE SET
                    patient_id = excluded.patient_id,
                    source_doc = excluded.source_doc,
                    doc_type = excluded.doc_type,
                    page = excluded.page,
                    chunk_index = excluded.chunk_index,
                    text = excluded.text,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
            conn.executemany("DELETE FROM chunk_fts WHERE chunk_key = ?", [(row[0],) for row in rows])
            conn.executemany(
                """
                INSERT INTO chunk_fts (chunk_key, patient_id, source_doc, doc_type, text)
                VALUES (?, ?, ?, ?, ?)
                """,
                [(row[0], row[1], row[2], row[3], row[6]) for row in rows],
            )
    except Exception as exc:
        log.error("[sqlite_cache] upsert_chunk_records error: %s", exc)


def _fts_query(value: str) -> str:
    terms = []
    for token in normalize_query(value).split():
        if len(token) >= 2 and token.isascii():
            terms.append(f'"{token}"')
    return " OR ".join(terms[:8])


def search_chunk_records(
    query: str,
    patient_id: str,
    *,
    doc_type: str | None = None,
    limit: int = 60,
) -> list[dict[str, Any]]:
    fts_query = _fts_query(query)
    if not fts_query:
        return []

    doc_clause = "AND c.doc_type = ?" if doc_type else ""
    params: list[Any] = [fts_query, patient_id]
    if doc_type:
        params.append(doc_type)
    params.append(limit)

    sql = f"""
        SELECT
            c.chunk_key AS chunk_id,
            c.patient_id,
            c.source_doc,
            c.doc_type,
            c.page,
            c.chunk_index,
            c.text
        FROM chunk_fts f
        JOIN chunk_cache c ON c.chunk_key = f.chunk_key
        WHERE f.text MATCH ?
          AND c.patient_id = ?
          {doc_clause}
        ORDER BY bm25(chunk_fts)
        LIMIT ?
    """
    try:
        with _CONN_LOCK, _get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    except Exception as exc:
        log.warning("[sqlite_cache] FTS search failed: %s", exc)
        return []
