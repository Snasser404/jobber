"""SQLite tracking of applications so you never apply to the same job twice."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from . import config
from .models import RankedJob, TailoredApplication

DB_PATH = config.ROOT / "data" / "jobber.db"

# new -> prepared -> approved -> applied   (or skipped)
STATUSES = ("new", "prepared", "approved", "applied", "skipped")


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with _conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS applications (
                job_id      TEXT PRIMARY KEY,
                title       TEXT,
                company     TEXT,
                location    TEXT,
                source      TEXT,
                url         TEXT,
                apply_url   TEXT,
                score       INTEGER,
                status      TEXT,
                resume_path TEXT,
                cover_path  TEXT,
                created_at  REAL,
                updated_at  REAL,
                data        TEXT
            )"""
        )


def status_map() -> dict[str, str]:
    """job_id -> status, for everything we've touched."""
    with _conn() as c:
        rows = c.execute("SELECT job_id, status FROM applications").fetchall()
    return {r["job_id"]: r["status"] for r in rows}


def save_prepared(ranked: RankedJob, tailored: TailoredApplication) -> None:
    job = ranked.job
    now = time.time()
    payload = json.dumps({
        "reasons": ranked.reasons,
        "concerns": ranked.concerns,
        "summary": ranked.summary,
        "resume_changes": tailored.resume_changes,
    })
    with _conn() as c:
        existing = c.execute(
            "SELECT created_at, status FROM applications WHERE job_id=?", (job.id,)
        ).fetchone()
        created = existing["created_at"] if existing else now
        # don't downgrade an already-applied job
        status = existing["status"] if (existing and existing["status"] == "applied") else "prepared"
        c.execute(
            """INSERT INTO applications
               (job_id,title,company,location,source,url,apply_url,score,status,
                resume_path,cover_path,created_at,updated_at,data)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(job_id) DO UPDATE SET
                 score=excluded.score, status=excluded.status,
                 resume_path=excluded.resume_path, cover_path=excluded.cover_path,
                 updated_at=excluded.updated_at, data=excluded.data""",
            (job.id, job.title, job.company, job.location, job.source, job.url,
             job.best_apply_url, ranked.score, status,
             tailored.resume_docx_path, tailored.cover_letter_path,
             created, now, payload),
        )


def set_status(job_id: str, status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status}")
    with _conn() as c:
        c.execute(
            "UPDATE applications SET status=?, updated_at=? WHERE job_id=?",
            (status, time.time(), job_id),
        )


def list_applications(status: str | None = None) -> list[dict]:
    q = "SELECT * FROM applications"
    params: tuple = ()
    if status:
        q += " WHERE status=?"
        params = (status,)
    q += " ORDER BY updated_at DESC"
    with _conn() as c:
        return [dict(r) for r in c.execute(q, params).fetchall()]
