from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, data_dir: str | Path | None = None) -> None:
        base = Path(data_dir or os.environ.get("SPIRIT_DATA_DIR", ".spirit-data"))
        base.mkdir(parents=True, exist_ok=True)
        self.path = base / "assistant.sqlite"
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        statements = [
            """CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT,
                external_id TEXT,
                excerpt TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                received_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS proposals (
                id TEXT PRIMARY KEY,
                proposal_type TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected','applied','failed')),
                title TEXT NOT NULL,
                reason TEXT NOT NULL,
                confidence REAL NOT NULL,
                source_id TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                FOREIGN KEY(source_id) REFERENCES sources(id)
            )""",
            """CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                subject TEXT,
                due_at TEXT,
                important INTEGER NOT NULL DEFAULT 0,
                urgent INTEGER NOT NULL DEFAULT 0,
                quadrant INTEGER NOT NULL CHECK(quadrant BETWEEN 1 AND 4),
                status TEXT NOT NULL DEFAULT 'open',
                source_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(source_id) REFERENCES sources(id)
            )""",
            """CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_proposals_status_created ON proposals(status, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_status_quadrant ON tasks(status, quadrant)",
            "CREATE INDEX IF NOT EXISTS idx_sources_external ON sources(source_type, external_id)",
        ]
        with self.connect() as db:
            for statement in statements:
                db.execute(statement)
            db.execute("PRAGMA optimize")

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        for field in ("payload_json", "metadata_json", "details_json"):
            if field in value:
                value[field.removesuffix("_json")] = json.loads(value.pop(field) or "{}")
        for field in ("important", "urgent"):
            if field in value:
                value[field] = bool(value[field])
        return value

    def create_source(self, source: dict[str, Any], excerpt: str) -> str:
        source_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute(
                "INSERT INTO sources(id,source_type,title,url,external_id,excerpt,metadata_json,received_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    source_id,
                    str(source.get("type") or "manual"),
                    str(source.get("title") or "Ручной ввод"),
                    source.get("url"),
                    source.get("external_id"),
                    excerpt[:4000],
                    json.dumps(source.get("metadata") or {}, ensure_ascii=False),
                    now_iso(),
                ),
            )
        return source_id

    def create_proposal(self, item: dict[str, Any], source_id: str) -> dict[str, Any]:
        proposal_id = str(uuid.uuid4())
        confidence = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        with self.connect() as db:
            db.execute(
                "INSERT INTO proposals(id,proposal_type,status,title,reason,confidence,source_id,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    proposal_id,
                    str(item.get("type") or "task.create"),
                    "pending",
                    str(item.get("title") or "Новое предложение"),
                    str(item.get("reason") or "Получено из нового источника"),
                    confidence,
                    source_id,
                    json.dumps(payload, ensure_ascii=False),
                    now_iso(),
                ),
            )
        return self.get_proposal(proposal_id)

    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
        if not row:
            raise KeyError("proposal_not_found")
        return self._row(row)

    def list_proposals(self, status: str | None = None) -> list[dict[str, Any]]:
        sql = """SELECT p.*, s.source_type, s.title AS source_title, s.url AS source_url
                 FROM proposals p LEFT JOIN sources s ON s.id=p.source_id"""
        params: tuple[Any, ...] = ()
        if status:
            sql += " WHERE p.status = ?"
            params = (status,)
        sql += " ORDER BY p.created_at DESC"
        with self.connect() as db:
            return [self._row(row) for row in db.execute(sql, params).fetchall()]

    def list_tasks(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT t.*, s.source_type, s.title AS source_title, s.url AS source_url
                   FROM tasks t LEFT JOIN sources s ON s.id=t.source_id
                   ORDER BY t.status, t.quadrant, COALESCE(t.due_at,'9999')"""
            ).fetchall()
        return [self._row(row) for row in rows]

    def state(self) -> dict[str, Any]:
        return {
            "tasks": self.list_tasks(),
            "proposals": self.list_proposals(),
            "generated_at": now_iso(),
        }

    @staticmethod
    def quadrant(important: bool, urgent: bool) -> int:
        if important and urgent:
            return 1
        if important:
            return 2
        if urgent:
            return 3
        return 4

    def decide(self, proposal_id: str, decision: str, edited_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        proposal = self.get_proposal(proposal_id)
        if proposal["status"] != "pending":
            raise ValueError("proposal_already_resolved")
        if decision not in {"approve", "reject"}:
            raise ValueError("invalid_decision")
        payload = edited_payload if isinstance(edited_payload, dict) else proposal["payload"]
        resolved_at = now_iso()
        new_status = "rejected" if decision == "reject" else "approved"
        result: dict[str, Any] = {"ready_for_execution": False}
        with self.connect() as db:
            if decision == "approve" and proposal["proposal_type"] == "task.create":
                task_id = str(uuid.uuid4())
                important = bool(payload.get("important", True))
                urgent = bool(payload.get("urgent", False))
                db.execute(
                    """INSERT INTO tasks(id,title,description,subject,due_at,important,urgent,quadrant,status,source_id,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        task_id,
                        str(payload.get("title") or proposal["title"]),
                        str(payload.get("description") or ""),
                        payload.get("subject"),
                        payload.get("due_at"),
                        int(important),
                        int(urgent),
                        self.quadrant(important, urgent),
                        "open",
                        proposal["source_id"],
                        resolved_at,
                        resolved_at,
                    ),
                )
                new_status = "applied"
                result["task_id"] = task_id
            elif decision == "approve":
                result["ready_for_execution"] = True
            db.execute(
                "UPDATE proposals SET status=?, payload_json=?, resolved_at=? WHERE id=?",
                (new_status, json.dumps(payload, ensure_ascii=False), resolved_at, proposal_id),
            )
            db.execute(
                "INSERT INTO audit_log(id,action,entity_type,entity_id,details_json,created_at) VALUES(?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    decision,
                    "proposal",
                    proposal_id,
                    json.dumps({"previous_status": "pending", "new_status": new_status}, ensure_ascii=False),
                    resolved_at,
                ),
            )
        result["proposal"] = self.get_proposal(proposal_id)
        return result
