"""Agendamentos salvos em SQLite (biblioteca padrão)."""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime

from .schedule import TZ, Interval

SCHEMA = """
CREATE TABLE IF NOT EXISTS appointments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    phone       TEXT NOT NULL,
    name        TEXT,
    service     TEXT NOT NULL,
    start       TEXT NOT NULL,      -- ISO 8601 com fuso, ex.: 2026-11-10T14:00:00-03:00
    end         TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'agendado',   -- agendado | confirmado | cancelado
    event_id    TEXT,               -- id do evento no Google Agenda, quando houver
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_appt_start ON appointments(start);
"""

ACTIVE = ("agendado", "confirmado")


def _row(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    d["start"] = datetime.fromisoformat(d["start"])
    d["end"] = datetime.fromisoformat(d["end"])
    return d


class AppointmentRepository:
    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def create(self, phone: str, name: str, service: str, start: datetime, end: datetime) -> dict:
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO appointments (phone, name, service, start, end, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (phone, name, service, start.isoformat(), end.isoformat(),
                 datetime.now(TZ).isoformat(timespec="seconds")),
            )
            self.conn.commit()
        return self.get(cur.lastrowid)

    def get(self, appt_id: int) -> dict | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM appointments WHERE id = ?", (appt_id,)).fetchone()
        return _row(row)

    def set_status(self, appt_id: int, status: str) -> None:
        with self.lock:
            self.conn.execute("UPDATE appointments SET status = ? WHERE id = ?", (status, appt_id))
            self.conn.commit()

    def set_event_id(self, appt_id: int, event_id: str) -> None:
        with self.lock:
            self.conn.execute("UPDATE appointments SET event_id = ? WHERE id = ?", (event_id, appt_id))
            self.conn.commit()

    def busy_between(self, start: datetime, end: datetime) -> list[Interval]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT start, end FROM appointments WHERE status IN (?, ?) AND start < ? AND end > ?",
                (*ACTIVE, end.isoformat(), start.isoformat()),
            ).fetchall()
        return [(datetime.fromisoformat(r["start"]), datetime.fromisoformat(r["end"])) for r in rows]

    def upcoming_for(self, phone: str, now: datetime) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM appointments WHERE phone = ? AND status IN (?, ?) AND start > ? "
                "ORDER BY start",
                (phone, *ACTIVE, now.isoformat()),
            ).fetchall()
        return [_row(r) for r in rows]

    def on_day(self, start: datetime, end: datetime) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM appointments WHERE start >= ? AND start < ? ORDER BY start",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        return [_row(r) for r in rows]
