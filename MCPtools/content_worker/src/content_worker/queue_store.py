from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


class QueueStore:
    def __init__(self, project_root: Path) -> None:
        self.path = project_root / ".cache" / "approval-queue.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def list(self) -> dict[str, Any]:
        with self.lock:
            queue = self._read()
        return {
            "ok": True,
            "queue": queue,
            "stats": {
                "pending": sum(item.get("status") == "pending" for item in queue),
                "approved": sum(item.get("status") == "approved" for item in queue),
                "rejected": sum(item.get("status") == "rejected" for item in queue),
            },
            "generated_at": iso_now(),
        }

    def enqueue(self, values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        with self.lock:
            queue = self._read()
            existing = {str(item.get("dedupe_key") or self._signature(item)) for item in queue}
            created: list[dict[str, Any]] = []
            for value in values[:50]:
                if not isinstance(value, dict):
                    continue
                key = str(value.get("dedupe_key") or self._signature(value))
                if key in existing:
                    continue
                existing.add(key)
                now = iso_now()
                item = dict(value)
                item.setdefault("id", f"q_{uuid.uuid4().hex[:16]}")
                item["dedupe_key"] = key
                item["status"] = "pending"
                item.setdefault("created_at", now)
                item["updated_at"] = now
                item["resolved_at"] = None
                created.append(item)
            if created:
                queue = (created + queue)[:500]
                self._write(queue)
            return created

    def decide(self, item_id: str, decision: str) -> dict[str, Any]:
        if decision not in {"approve", "reject"}:
            return {"authorized": True, "approved": False, "error": "invalid_decision"}
        with self.lock:
            queue = self._read()
            item = next((value for value in queue if str(value.get("id")) == item_id), None)
            if item is None:
                return {"authorized": True, "approved": False, "error": "queue_item_not_found"}
            if item.get("status") != "pending":
                return {"authorized": True, "approved": False, "error": "already_resolved", "item": item}
            now = iso_now()
            item["status"] = "approved" if decision == "approve" else "rejected"
            item["resolved_at"] = now
            item["updated_at"] = now
            self._write(queue)
        return {"authorized": True, "approved": decision == "approve", "decision": decision, "item": item}

    @staticmethod
    def _signature(value: dict[str, Any]) -> str:
        source = value.get("source") if isinstance(value.get("source"), dict) else {}
        payload = value.get("payload") if isinstance(value.get("payload"), dict) else {}
        parts = [source.get("type"), source.get("external_id"), value.get("kind"), value.get("action"), payload.get("start_at") or payload.get("due_at"), value.get("title")]
        return "|".join(str(part or "") for part in parts).lower()

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _write(self, queue: list[dict[str, Any]]) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

