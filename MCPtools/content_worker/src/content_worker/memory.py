from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


class MemoryStore:
    """Private local file memory. Nothing here is published to GitHub."""

    def __init__(self, project_root: Path) -> None:
        self.root = project_root / ".cache" / "memory"
        self.files = self.root / "files"
        self.db_path = self.root / "memory.sqlite"
        self.files.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self._init_db()

    def status(self) -> dict[str, Any]:
        with closing(self._connect()) as db:
            count = int(db.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
        return {"enabled": True, "private": True, "documents": count}

    def store_bytes(self, filename: str, data: bytes, source: dict[str, Any] | None = None) -> dict[str, Any]:
        if not data or len(data) > 100 * 1024 * 1024:
            raise ValueError("invalid_file_size")
        digest = hashlib.sha256(data).hexdigest()
        safe_name = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ._-]+", "-", Path(filename).name).strip(".-") or "file"
        path = self.files / f"{digest[:16]}-{safe_name}"
        if not path.exists():
            path.write_bytes(data)
        text = self._extract(path)
        metadata = source or {}
        with self.lock, closing(self._connect()) as db:
            db.execute(
                "INSERT INTO documents(id, filename, path, sha256, text, metadata, created_at) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(sha256) DO UPDATE SET filename=excluded.filename, metadata=excluded.metadata",
                (f"mem_{digest[:20]}", safe_name, str(path), digest, text, json.dumps(metadata, ensure_ascii=False), _now()),
            )
            db.commit()
            row = db.execute("SELECT id, filename, path, created_at FROM documents WHERE sha256=?", (digest,)).fetchone()
        return {"id": row[0], "filename": row[1], "path": row[2], "created_at": row[3], "text_length": len(text)}

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        words = [word.casefold() for word in re.findall(r"[\wа-яА-ЯёЁ]{3,}", query)][:12]
        if not words:
            return []
        with self.lock, closing(self._connect()) as db:
            rows = db.execute("SELECT id, filename, path, text, metadata, created_at FROM documents ORDER BY created_at DESC LIMIT 2000").fetchall()
        ranked = []
        for row in rows:
            folded = (row[3] or "").casefold()
            scores = [len(word) if word in folded else 1 if word[:5] in folded else 0 for word in words]
            if any(scores):
                ranked.append((sum(scores), row))
        ranked.sort(key=lambda value: value[0], reverse=True)
        results = []
        for _, row in ranked[:max(1, min(limit, 20))]:
            text = row[3] or ""
            folded = text.casefold()
            positions = [folded.find(word) for word in words if word in folded]
            position = min(positions, default=0)
            excerpt = text[max(0, position - 300):max(0, position - 300) + 1800].strip()
            results.append({"id": row[0], "filename": row[1], "path": row[2], "excerpt": excerpt, "metadata": json.loads(row[4] or "{}"), "created_at": row[5]})
        return results

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.lock, closing(self._connect()) as db:
            rows = db.execute("SELECT id, filename, path, metadata, created_at, length(text) FROM documents ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
        return [{"id": row[0], "filename": row[1], "path": row[2], "metadata": json.loads(row[3] or "{}"), "created_at": row[4], "text_length": row[5]} for row in rows]

    def _init_db(self) -> None:
        with closing(self._connect()) as db:
            db.execute("CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, filename TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT UNIQUE NOT NULL, text TEXT NOT NULL, metadata TEXT NOT NULL, created_at TEXT NOT NULL)")
            db.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=30)

    @staticmethod
    def _extract(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md", ".csv", ".json", ".html", ".htm"}:
            return path.read_text(encoding="utf-8", errors="replace")[:2_000_000]
        if suffix == ".docx":
            with zipfile.ZipFile(path) as archive:
                root = ElementTree.fromstring(archive.read("word/document.xml"))
            return "\n".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))[:2_000_000]
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
                return "\n\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)[:2_000_000]
            except (ImportError, OSError, ValueError):
                return ""
        return ""
