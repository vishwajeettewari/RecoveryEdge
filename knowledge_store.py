from __future__ import annotations

import os
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from typing import Iterable, List, Optional


@dataclass
class KnowledgeChunk:
    doc_id: str
    title: str
    chunk_id: int
    text: str
    score: float


def _chunk_text(text: str, chunk_size: int = 550, overlap: int = 120) -> List[str]:
    t = (text or "").strip()
    if not t:
        return []
    out: List[str] = []
    i = 0
    n = len(t)
    while i < n:
        j = min(n, i + chunk_size)
        out.append(t[i:j].strip())
        if j >= n:
            break
        i = max(i + 1, j - overlap)
    return [c for c in out if c]


class SQLiteFTSKnowledgeStore:
    def __init__(self, db_path: str, knowledge_dir: str) -> None:
        self.db_path = db_path
        self.knowledge_dir = knowledge_dir
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        os.makedirs(self.knowledge_dir, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    doc_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    chunk_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    PRIMARY KEY (doc_id, chunk_id)
                )
                """
            )
            # FTS5 is part of modern SQLite builds; if it's missing, ingestion/query will raise.
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
                USING fts5(doc_id, title, chunk_id, text, content='knowledge_chunks', content_rowid='rowid')
                """
            )
            conn.commit()
        finally:
            conn.close()

    def reindex(self) -> int:
        files = self._iter_files()
        conn = self._connect()
        try:
            conn.execute("DELETE FROM knowledge_chunks")
            conn.execute("DELETE FROM knowledge_fts")
            total = 0
            for path in files:
                doc_id = os.path.basename(path)
                title = os.path.splitext(doc_id)[0].replace("_", " ").strip()
                with open(path, "r", encoding="utf-8") as handle:
                    text = handle.read()
                chunks = _chunk_text(text)
                for idx, chunk in enumerate(chunks):
                    total += 1
                    conn.execute(
                        "INSERT OR REPLACE INTO knowledge_chunks (doc_id, title, chunk_id, text) VALUES (?, ?, ?, ?)",
                        (doc_id, title, idx, chunk),
                    )
                    conn.execute(
                        "INSERT INTO knowledge_fts (doc_id, title, chunk_id, text) VALUES (?, ?, ?, ?)",
                        (doc_id, title, idx, chunk),
                    )
            conn.commit()
            return total
        finally:
            conn.close()

    def query(self, q: str, limit: int = 3) -> List[KnowledgeChunk]:
        q = (q or "").strip()
        if not q:
            return []
        conn = self._connect()
        try:
            # Use bm25 ranking (available with FTS5). Lower is better; invert for display.
            rows = conn.execute(
                """
                SELECT doc_id, title, chunk_id, text, bm25(knowledge_fts) AS score
                FROM knowledge_fts
                WHERE knowledge_fts MATCH ?
                ORDER BY score ASC
                LIMIT ?
                """,
                (self._fts_query(q), max(1, int(limit))),
            ).fetchall()
            out: List[KnowledgeChunk] = []
            for r in rows:
                score = float(r["score"]) if r["score"] is not None else 0.0
                out.append(
                    KnowledgeChunk(
                        doc_id=str(r["doc_id"]),
                        title=str(r["title"]),
                        chunk_id=int(r["chunk_id"]),
                        text=str(r["text"]),
                        score=score,
                    )
                )
            return out
        finally:
            conn.close()

    def _iter_files(self) -> List[str]:
        out: List[str] = []
        for name in os.listdir(self.knowledge_dir):
            if name.startswith("."):
                continue
            if not (name.endswith(".md") or name.endswith(".txt")):
                continue
            out.append(os.path.join(self.knowledge_dir, name))
        return sorted(out)

    @staticmethod
    def _fts_query(q: str) -> str:
        # Keep native-script letters and digits so Indic policy documents remain retrievable.
        tokens: List[str] = []
        current: List[str] = []
        for ch in unicodedata.normalize("NFKC", q or ""):
            cat = unicodedata.category(ch)
            if cat[0] in {"L", "N"} or cat in {"Mn", "Mc", "Me"}:
                current.append(ch)
                continue
            if current:
                token = "".join(current).strip("_")
                if token:
                    tokens.append(token)
                current = []
        if current:
            token = "".join(current).strip("_")
            if token:
                tokens.append(token)
        if not tokens:
            return q
        return " AND ".join(tokens[:12])

    @staticmethod
    def format_for_prompt(chunks: List[KnowledgeChunk]) -> str:
        if not chunks:
            return ""
        lines = [
            "Knowledge references (use for policy/SOP claims; cite by [doc:chunk]):",
        ]
        for c in chunks:
            snippet = c.text.strip().replace("\n", " ")
            if len(snippet) > 380:
                snippet = snippet[:380].rstrip() + "..."
            lines.append(f"- [{c.doc_id}:{c.chunk_id}] {c.title}: {snippet}")
        return "\n".join(lines).strip()
