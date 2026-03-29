"""SQLite models for ChangelogHQ."""

import sqlite3
import os
import uuid
from datetime import datetime, timezone
from typing import Optional


DB_PATH = os.environ.get("CHANGELOG_DB_PATH", "/data/changelog-hq/changelog.db")


def get_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            repo TEXT NOT NULL,
            webhook_secret TEXT,
            github_token TEXT,
            last_generated_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS entries (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            version TEXT,
            category TEXT NOT NULL DEFAULT 'improvement',
            title TEXT NOT NULL,
            body TEXT,
            pr_number INTEGER,
            pr_url TEXT,
            author TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_entries_project ON entries(project_id);
        CREATE INDEX IF NOT EXISTS idx_entries_created ON entries(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_entries_category ON entries(category);
    """)
    conn.commit()
    conn.close()


def create_project(name: str, repo: str, webhook_secret: Optional[str] = None,
                   github_token: Optional[str] = None) -> dict:
    conn = get_db()
    project_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO projects (id, name, repo, webhook_secret, github_token, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (project_id, name, repo, webhook_secret, github_token, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    return dict(row)


def get_project(project_id: str) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_projects() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_project(project_id: str) -> bool:
    conn = get_db()
    cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def add_entry(project_id: str, category: str, title: str, body: str = "",
              pr_number: Optional[int] = None, pr_url: Optional[str] = None,
              author: Optional[str] = None, version: Optional[str] = None) -> dict:
    conn = get_db()
    entry_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO entries (id, project_id, version, category, title, body, pr_number, pr_url, author, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (entry_id, project_id, version, category, title, body, pr_number, pr_url, author, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
    conn.close()
    return dict(row)


def get_entries(project_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM entries WHERE project_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (project_id, limit, offset),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_entries_grouped(project_id: str, limit: int = 100) -> dict[str, list[dict]]:
    entries = get_entries(project_id, limit)
    grouped: dict[str, list[dict]] = {}
    for e in entries:
        cat = e["category"]
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(e)
    return grouped


def get_latest_entry_date(project_id: str) -> Optional[str]:
    conn = get_db()
    row = conn.execute(
        "SELECT MAX(created_at) as latest FROM entries WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    conn.close()
    if row and row["latest"]:
        return row["latest"]
    return None


def update_project_last_generated(project_id: str):
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE projects SET last_generated_at = ? WHERE id = ?", (now, project_id))
    conn.commit()
    conn.close()
