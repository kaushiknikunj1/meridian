"""Meridian's memory.

Two kinds. The **journal** is what it did and concluded, append-only, and it is
what gets published. **Notes** are what it has learned and wants to carry forward,
keyed so a later cycle can update rather than duplicate.

SQLite, stdlib only. The agent runs unattended on a laptop; it should not need a
database server to think.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "meridian.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS cycles (
    id          INTEGER PRIMARY KEY,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    intent      TEXT,            -- what it decided to do, in its own words
    outcome     TEXT,            -- done | nothing | error
    summary      TEXT,           -- what it concluded (Telegram + CLI)
    thoughts     TEXT,           -- its unhedged read — Telegram ONLY, never published
    public_title TEXT,           -- neutral one-liner for the public page
    public_body  TEXT,           -- neutral body for the public page
    detail       TEXT,           -- legacy; superseded by public_body
    tokens      INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tool_calls (
    id        INTEGER PRIMARY KEY,
    cycle_id  INTEGER,
    at        TEXT NOT NULL,
    tool      TEXT NOT NULL,
    args      TEXT,
    outcome   TEXT NOT NULL,     -- ok | refused | error
    detail    TEXT
);
CREATE TABLE IF NOT EXISTS notes (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proposals (
    id         INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    cycle_id   INTEGER,
    kind       TEXT NOT NULL,    -- article | fix | opportunity | other
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    status     TEXT DEFAULT 'open'   -- open | accepted | dismissed
);
CREATE INDEX IF NOT EXISTS ix_cycles_started ON cycles(started_at);
"""


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


# ------------------------------------------------------------------ cycles --
def start_cycle() -> int:
    with connect() as con:
        cur = con.execute("INSERT INTO cycles (started_at) VALUES (?)", (now(),))
        return int(cur.lastrowid or 0)


def finish_cycle(
    cycle_id: int, *, intent: str, outcome: str, summary: str,
    thoughts: str = "", public_title: str = "", public_body: str = "",
) -> None:
    with connect() as con:
        con.execute(
            "UPDATE cycles SET finished_at=?, intent=?, outcome=?, summary=?, "
            "thoughts=?, public_title=?, public_body=? WHERE id=?",
            (now(), intent, outcome, summary, thoughts,
             public_title, public_body, cycle_id),
        )


def set_next_wake(minutes: int) -> str:
    """Meridian decides its own cadence; this is where that decision lives."""
    when = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)
    remember("_next_wake_at", when.isoformat(timespec="seconds"))
    return when.isoformat(timespec="seconds")


def due_in_seconds() -> float:
    """Seconds until the next wake. Negative or zero means due now."""
    raw = notes(include_internal=True).get("_next_wake_at")
    if not raw:
        return 0.0
    try:
        when = dt.datetime.fromisoformat(raw)
    except ValueError:
        return 0.0
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return (when - dt.datetime.now(dt.timezone.utc)).total_seconds()


def cycles_since(hours: float) -> list[dict[str, Any]]:
    cutoff = (dt.datetime.now(dt.timezone.utc)
              - dt.timedelta(hours=hours)).isoformat(timespec="seconds")
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM cycles WHERE finished_at IS NOT NULL AND started_at >= ? "
            "ORDER BY id DESC", (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


def hours_since_digest() -> float:
    raw = notes(include_internal=True).get("_last_digest_at")
    if not raw:
        return 1e6
    try:
        when = dt.datetime.fromisoformat(raw)
    except ValueError:
        return 1e6
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - when).total_seconds() / 3600


def mark_digest_sent() -> None:
    remember("_last_digest_at",
             dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))


def recent_cycles(limit: int = 12) -> list[dict[str, Any]]:
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM cycles WHERE finished_at IS NOT NULL "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------- notes --
def remember(key: str, value: str) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO notes (key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
            "updated_at=excluded.updated_at",
            (key[:120], value[:4000], now()),
        )


def notes(include_internal: bool = False) -> dict[str, str]:
    """Its notes. Keys starting with `_` are plumbing and are hidden from it."""
    with connect() as con:
        rows = {r["key"]: r["value"] for r in con.execute("SELECT * FROM notes")}
    if include_internal:
        return rows
    return {k: v for k, v in rows.items() if not k.startswith("_")}


# --------------------------------------------------------------- proposals --
def propose(cycle_id: int, kind: str, title: str, body: str) -> int:
    with connect() as con:
        cur = con.execute(
            "INSERT INTO proposals (created_at, cycle_id, kind, title, body) "
            "VALUES (?,?,?,?,?)",
            (now(), cycle_id, kind[:20], title[:200], body[:8000]),
        )
        return int(cur.lastrowid or 0)


def open_proposals(limit: int = 30) -> list[dict[str, Any]]:
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM proposals WHERE status='open' ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------- audit --
def log_tool(
    cycle_id: int, tool: str, args: dict[str, Any], outcome: str, detail: str = ""
) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO tool_calls (cycle_id, at, tool, args, outcome, detail) "
            "VALUES (?,?,?,?,?,?)",
            (cycle_id, now(), tool, json.dumps(args, default=str)[:2000],
             outcome, detail[:2000]),
        )


def tool_history(limit: int = 40) -> list[dict[str, Any]]:
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM tool_calls ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
