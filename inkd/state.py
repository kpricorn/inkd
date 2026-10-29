"""SQLite state: what was synced last, so a cycle only touches what changed."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id      TEXT PRIMARY KEY,
    tablet_path TEXT NOT NULL,
    version     TEXT,           -- tablet version stamp last exported (NULL: never)
    note_path   TEXT,           -- vault-relative note the document writes into
    origin      TEXT NOT NULL,  -- 'tablet' or 'obsidian' (published from a note)
    has_ink     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pages (
    doc_id    TEXT NOT NULL,
    page_id   TEXT NOT NULL,
    rm_hash   TEXT NOT NULL,    -- hash of the page's .rm file
    text      TEXT NOT NULL,    -- transcription of that version
    PRIMARY KEY (doc_id, page_id)
);
CREATE TABLE IF NOT EXISTS published (
    note_path    TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL, -- hash of the note body as last published
    tablet_path  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inbox (
    name TEXT PRIMARY KEY,
    size INTEGER,
    modified TEXT
);
"""


class State:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    # documents

    def document(self, doc_id: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()

    def document_at(self, tablet_path: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM documents WHERE tablet_path = ?", (tablet_path,)
        ).fetchone()

    def documents(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM documents ORDER BY tablet_path").fetchall()

    def save_document(self, doc_id, tablet_path, version, note_path, origin, has_ink=False) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?, ?, ?)",
                (doc_id, tablet_path, version, note_path, origin, int(has_ink)),
            )

    # pages

    def page_text(self, doc_id: str, page_id: str, rm_hash: str) -> str | None:
        row = self.db.execute(
            "SELECT text FROM pages WHERE doc_id = ? AND page_id = ? AND rm_hash = ?",
            (doc_id, page_id, rm_hash),
        ).fetchone()
        return row["text"] if row else None

    def save_page(self, doc_id: str, page_id: str, rm_hash: str, text: str) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO pages VALUES (?, ?, ?, ?)",
                (doc_id, page_id, rm_hash, text),
            )

    # published notes

    def published(self, note_path: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM published WHERE note_path = ?", (note_path,)
        ).fetchone()

    def save_published(self, note_path: str, content_hash: str, tablet_path: str) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO published VALUES (?, ?, ?)",
                (note_path, content_hash, tablet_path),
            )

    # inbox

    def inbox_seen(self, name: str, size: int, modified: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM inbox WHERE name = ? AND size = ? AND modified = ?",
            (name, size, modified),
        ).fetchone()
        return row is not None

    def save_inbox(self, name: str, size: int, modified: str) -> None:
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO inbox VALUES (?, ?, ?)", (name, size, modified))
