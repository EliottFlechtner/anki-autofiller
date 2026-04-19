"""Inbox storage for phone-captured vocabulary.

Supports either a local SQLite fallback or a remote Supabase table.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib import parse, request

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT_DIR / "output" / "inbox.sqlite3"
DEFAULT_TABLE_NAME = os.environ.get("ANKI_JISHO2ANKI_INBOX_TABLE", "inbox_items")
DEFAULT_SUPABASE_URL = os.environ.get("ANKI_JISHO2ANKI_SUPABASE_URL", "").strip()
DEFAULT_SUPABASE_SERVICE_KEY = os.environ.get(
    "ANKI_JISHO2ANKI_SUPABASE_SERVICE_ROLE_KEY", ""
).strip()
DEFAULT_SUPABASE_CAPTURE_TOKEN = os.environ.get(
    "ANKI_JISHO2ANKI_SUPABASE_CAPTURE_TOKEN",
    os.environ.get("ANKI_AUTOFILLER_SUPABASE_CAPTURE_TOKEN", ""),
).strip()
SUPABASE_CAPTURE_TOKEN_HEADER = "X-J2A-Capture-Token"


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _supabase_enabled() -> bool:
    return bool(DEFAULT_SUPABASE_URL and DEFAULT_SUPABASE_SERVICE_KEY)


def _supabase_rest_url(path: str) -> str:
    base_url = DEFAULT_SUPABASE_URL.rstrip("/")
    return f"{base_url}/rest/v1/{path.lstrip('/')}"


def _supabase_headers(*, prefer_return: bool = False) -> dict[str, str]:
    headers = {
        "apikey": DEFAULT_SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {DEFAULT_SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer_return:
        headers["Prefer"] = "return=representation"
    if DEFAULT_SUPABASE_CAPTURE_TOKEN:
        headers[SUPABASE_CAPTURE_TOKEN_HEADER] = DEFAULT_SUPABASE_CAPTURE_TOKEN
    return headers


def _supabase_request(
    method: str,
    path: str,
    *,
    query: dict[str, str] | None = None,
    payload: Any = None,
    prefer_return: bool = False,
    prefer_count: bool = False,
) -> tuple[Any, dict[str, str]]:
    url = _supabase_rest_url(path)
    if query:
        url = f"{url}?{parse.urlencode(query)}"

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    headers = _supabase_headers(prefer_return=prefer_return)
    if prefer_count:
        headers["Prefer"] = headers.get("Prefer", "") + (
            ",count=exact" if headers.get("Prefer") else "count=exact"
        )

    req = request.Request(url, data=data, headers=headers, method=method.upper())
    with request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw
        return parsed, {key.lower(): value for key, value in resp.headers.items()}


def ensure_inbox_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Create local inbox table if Supabase is not configured."""
    if _supabase_enabled():
        return

    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inbox_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT '',
                received_at_ms INTEGER NOT NULL,
                created_at_ms INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                ankied_at_ms INTEGER
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_inbox_items_status ON inbox_items(status)"
        )
        conn.commit()


def add_inbox_items(
    items: list[str],
    *,
    source: str = "capture",
    received_at_ms: int | None = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """Insert pending inbox items and return inserted rows."""
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    if not cleaned:
        return []

    now_ms = int(time.time() * 1000)
    ts_ms = int(received_at_ms or now_ms)

    if _supabase_enabled():
        payload = [
            {
                "text": text,
                "source": source,
                "received_at_ms": ts_ms,
                "created_at_ms": now_ms,
                "status": "pending",
            }
            for text in cleaned
        ]
        rows, _headers = _supabase_request(
            "POST",
            DEFAULT_TABLE_NAME,
            payload=payload,
            prefer_return=True,
        )
        if isinstance(rows, list):
            return [dict(row) for row in rows]
        return []

    ensure_inbox_db(db_path)
    inserted: list[dict[str, Any]] = []
    with _connect(db_path) as conn:
        for text in cleaned:
            cursor = conn.execute(
                """
                INSERT INTO inbox_items(text, source, received_at_ms, created_at_ms, status)
                VALUES (?, ?, ?, ?, 'pending')
                """,
                (text, source, ts_ms, now_ms),
            )
            lastrowid = cursor.lastrowid
            if lastrowid is None:
                raise RuntimeError("SQLite insert did not return a row id")
            inserted.append(
                {
                    "id": int(lastrowid),
                    "text": text,
                    "source": source,
                    "received_at_ms": ts_ms,
                    "created_at_ms": now_ms,
                    "status": "pending",
                }
            )
        conn.commit()
    return inserted


def list_pending_inbox_items(
    *,
    limit: int = 200,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """Return pending inbox rows ordered oldest-first."""
    safe_limit = max(1, min(int(limit), 1000))
    if _supabase_enabled():
        query = {
            "select": "id,text,source,received_at_ms,created_at_ms,status",
            "status": "eq.pending",
            "order": "id.asc",
            "limit": str(safe_limit),
        }
        rows, _headers = _supabase_request("GET", DEFAULT_TABLE_NAME, query=query)
        return [dict(row) for row in rows] if isinstance(rows, list) else []

    ensure_inbox_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, text, source, received_at_ms, created_at_ms, status
            FROM inbox_items
            WHERE status = 'pending'
            ORDER BY id ASC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_inbox_items_ankied(
    ids: list[int],
    *,
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    """Mark pending inbox rows as ankied. Returns count changed."""
    clean_ids = sorted({int(item) for item in ids if int(item) > 0})
    if not clean_ids:
        return 0

    now_ms = int(time.time() * 1000)
    if _supabase_enabled():
        query = {"id": f"in.({','.join(str(item) for item in clean_ids)})"}
        payload = {"status": "ankied", "ankied_at_ms": now_ms}
        rows, _headers = _supabase_request(
            "PATCH",
            DEFAULT_TABLE_NAME,
            query=query,
            payload=payload,
            prefer_return=True,
        )
        if isinstance(rows, list):
            return len(rows)
        return 0

    ensure_inbox_db(db_path)
    placeholders = ",".join(["?"] * len(clean_ids))
    with _connect(db_path) as conn:
        cursor = conn.execute(
            f"""
            UPDATE inbox_items
            SET status = 'ankied', ankied_at_ms = ?
            WHERE status = 'pending' AND id IN ({placeholders})
            """,
            (now_ms, *clean_ids),
        )
        conn.commit()
        return int(cursor.rowcount)


def delete_inbox_item(
    item_id: int,
    *,
    db_path: Path = DEFAULT_DB_PATH,
) -> bool:
    """Delete an inbox item by ID. Returns True if deleted successfully."""
    if not (isinstance(item_id, int) and item_id > 0):
        return False

    if _supabase_enabled():
        try:
            _supabase_request(
                "DELETE",
                DEFAULT_TABLE_NAME,
                query={"id": f"eq.{item_id}"},
            )
            return True
        except Exception:
            return False

    ensure_inbox_db(db_path)
    with _connect(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM inbox_items WHERE id = ?",
            (item_id,),
        )
        conn.commit()
        return int(cursor.rowcount) > 0


def pending_inbox_count(*, db_path: Path = DEFAULT_DB_PATH) -> int:
    """Return count of pending inbox rows."""
    if _supabase_enabled():
        query = {
            "select": "id",
            "status": "eq.pending",
            "limit": "1",
        }
        _rows, headers = _supabase_request(
            "GET",
            DEFAULT_TABLE_NAME,
            query=query,
            prefer_count=True,
        )
        content_range = headers.get("content-range", "")
        if "/" in content_range:
            try:
                return int(content_range.split("/")[-1])
            except ValueError:
                return 0
        return 0

    ensure_inbox_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM inbox_items WHERE status = 'pending'"
        ).fetchone()
    return int(row["count"] if row else 0)
