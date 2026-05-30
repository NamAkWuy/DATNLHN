import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from config import LOCAL_OUTBOX_DB


_lock = threading.Lock()
_initialized = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    parent = os.path.dirname(os.path.abspath(LOCAL_OUTBOX_DB))
    if parent:
        os.makedirs(parent, exist_ok=True)
    con = sqlite3.connect(LOCAL_OUTBOX_DB, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    global _initialized
    with _lock:
        if _initialized:
            return
        with _connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS attendance_outbox (
                    event_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    synced_at TEXT
                )
                """
            )
            con.execute(
                """
                UPDATE attendance_outbox
                SET status = 'pending', updated_at = ?
                WHERE status = 'sending'
                """,
                (_now_iso(),),
            )
            con.commit()
        _initialized = True


def save_event(payload: dict[str, Any], status: str = "pending") -> None:
    init_db()
    event_id = payload["client_event_id"]
    now = _now_iso()
    with _lock, _connect() as con:
        con.execute(
            """
            INSERT INTO attendance_outbox (
                event_id, payload_json, status, attempts, created_at, updated_at
            )
            VALUES (?, ?, ?, 0, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                payload_json = excluded.payload_json,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (event_id, json.dumps(payload, ensure_ascii=False), status, now, now),
        )
        con.commit()


def mark_sending(event_id: str) -> None:
    _update_status(event_id, "sending")


def mark_pending(event_id: str, error: str | None = None) -> None:
    init_db()
    with _lock, _connect() as con:
        con.execute(
            """
            UPDATE attendance_outbox
            SET status = 'pending',
                attempts = attempts + 1,
                last_error = ?,
                updated_at = ?
            WHERE event_id = ?
            """,
            (error, _now_iso(), event_id),
        )
        con.commit()


def mark_failed(event_id: str, error: str | None = None) -> None:
    init_db()
    with _lock, _connect() as con:
        con.execute(
            """
            UPDATE attendance_outbox
            SET status = 'failed',
                attempts = attempts + 1,
                last_error = ?,
                updated_at = ?
            WHERE event_id = ?
            """,
            (error, _now_iso(), event_id),
        )
        con.commit()


def mark_synced(event_id: str) -> None:
    init_db()
    now = _now_iso()
    with _lock, _connect() as con:
        con.execute(
            """
            UPDATE attendance_outbox
            SET status = 'synced',
                last_error = NULL,
                updated_at = ?,
                synced_at = ?
            WHERE event_id = ?
            """,
            (now, now, event_id),
        )
        con.commit()


def pending_events(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with _lock, _connect() as con:
        rows = con.execute(
            """
            SELECT event_id, payload_json, attempts
            FROM attendance_outbox
            WHERE status = 'pending'
            ORDER BY created_at
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "event_id": row["event_id"],
            "payload": json.loads(row["payload_json"]),
            "attempts": row["attempts"],
        }
        for row in rows
    ]


def pending_count() -> int:
    init_db()
    with _lock, _connect() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM attendance_outbox WHERE status = 'pending'"
        ).fetchone()
    return int(row["n"])


def _update_status(event_id: str, status: str) -> None:
    init_db()
    with _lock, _connect() as con:
        con.execute(
            """
            UPDATE attendance_outbox
            SET status = ?, updated_at = ?
            WHERE event_id = ?
            """,
            (status, _now_iso(), event_id),
        )
        con.commit()
