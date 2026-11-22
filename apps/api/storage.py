"""
Conversation history for the EIH application (SQLite, standard library only).

One file, ``settings.okf.state_dir / "app.sqlite3"`` by default (gitignored with the
bundles). Every query is parameterised (SRS S3). Messages keep the structured answer
metadata (citations, concepts used, proposals, measurements) as JSON, so the history
view can show the same traceability as the live answer.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    bundle TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    meta TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_messages_conv ON messages(conversation_id, created_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class ConversationStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def create(self, title: str, bundle: Optional[str] = None) -> Dict[str, Any]:
        cid, now = uuid.uuid4().hex, _now()
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO conversations VALUES (?, ?, ?, ?, ?)", (cid, title[:200] or "Conversation", bundle, now, now))
        return self.get(cid)

    def get(self, cid: str) -> Optional[Dict[str, Any]]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM conversations WHERE id = ?", (cid,)).fetchone()
            if row is None:
                return None
            msgs = c.execute("SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at, rowid",
                             (cid,)).fetchall()
        return dict(row) | {"messages": [self._msg(m) for m in msgs]}

    @staticmethod
    def _msg(m: sqlite3.Row) -> Dict[str, Any]:
        d = dict(m)
        d["meta"] = json.loads(d["meta"]) if d.get("meta") else None
        return d

    def list(self, limit: int = 100, query: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = ("SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count "
               "FROM conversations c")
        args: list = []
        if query:
            sql += (" WHERE c.title LIKE ? OR EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id "
                    "AND m.content LIKE ?)")
            args += [f"%{query}%", f"%{query}%"]
        sql += " ORDER BY c.updated_at DESC LIMIT ?"
        args.append(int(limit))
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

    def add_message(self, cid: str, role: str, content: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        mid, now = uuid.uuid4().hex, _now()
        with self._lock, self._conn() as c:
            if c.execute("SELECT 1 FROM conversations WHERE id = ?", (cid,)).fetchone() is None:
                raise KeyError(cid)
            c.execute("INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?)",
                      (mid, cid, role, content, json.dumps(meta, default=str) if meta is not None else None, now))
            c.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, cid))
        return {"id": mid, "conversation_id": cid, "role": role, "content": content, "meta": meta, "created_at": now}

    def history(self, cid: str, limit: int = 12) -> List[Dict[str, str]]:
        with self._conn() as c:
            rows = c.execute("SELECT role, content FROM messages WHERE conversation_id = ? "
                             "ORDER BY created_at DESC, rowid DESC LIMIT ?", (cid, int(limit))).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def rename(self, cid: str, title: str) -> bool:
        with self._lock, self._conn() as c:
            return c.execute("UPDATE conversations SET title = ? WHERE id = ?", (title[:200], cid)).rowcount > 0

    def delete(self, cid: str) -> bool:
        with self._lock, self._conn() as c:
            return c.execute("DELETE FROM conversations WHERE id = ?", (cid,)).rowcount > 0
