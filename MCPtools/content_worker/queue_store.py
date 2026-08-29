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
        self.schedule_path = project_root / ".cache" / "mesh-schedule-state.json"
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
            schedule_state = self._read_schedule_state()
            schedule_changed = False
            created: list[dict[str, Any]] = []
            for value in values[:50]:
                if not isinstance(value, dict):
                    continue
                key = str(value.get("dedupe_key") or self._signature(value))
                value, changed = self._mark_schedule_change(dict(value), schedule_state)
                schedule_changed = schedule_changed or changed
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
            if schedule_changed:
                self._write_schedule_state(schedule_state)
            return created

    def _mark_schedule_change(self, value: dict[str, Any], state: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        source = value.get("source") if isinstance(value.get("source"), dict) else {}
        if source.get("type") != "mesh" or value.get("kind") != "event":
            return value, False
        external_id = str(source.get("external_id") or "")
        if not external_id:
            return value, False
        payload = value.get("payload") if isinstance(value.get("payload"), dict) else {}
        current = {
            "title": str(value.get("title") or ""),
            "start_at": str(payload.get("start_at") or ""),
            "end_at": str(payload.get("end_at") or ""),
            "location": str(payload.get("location") or ""),
        }
        previous = state.get(external_id)
        state[external_id] = current
        if not isinstance(previous, dict) or previous == current:
            return value, previous != current
        labels = {"title": "предмет", "start_at": "начало", "end_at": "окончание", "location": "место"}
        changes = [f"{labels[key]}: {previous.get(key) or '—'} → {current.get(key) or '—'}" for key in labels if previous.get(key) != current.get(key)]
        original_title = current["title"] or "урок"
        value["subtype"] = "schedule_change"
        value["title"] = f"Изменение расписания: {original_title}"
        value["summary"] = "; ".join(changes)
        value["reason"] = "МЭШ изменил ранее полученные данные расписания. Изменение применится только после подтверждения."
        new_payload = dict(payload)
        new_payload["previous"] = previous
        new_payload["changes"] = changes
        value["payload"] = new_payload
        return value, True

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

    def edit(self, item_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        allowed_pairs = {
            ("event", "calendar"),
            ("task", "task_summary"),
            ("homework", "note"),
            ("homework", "homework_solver"),
            ("news", "news_digest"),
        }
        with self.lock:
            queue = self._read()
            item = next((value for value in queue if str(value.get("id")) == item_id), None)
            if item is None:
                return {"authorized": True, "approved": False, "error": "queue_item_not_found"}
            if item.get("status") != "pending":
                return {"authorized": True, "approved": False, "error": "already_resolved", "item": item}
            kind = str(changes.get("kind") or item.get("kind") or "")
            action = str(changes.get("action") or item.get("action") or "")
            if (kind, action) not in allowed_pairs:
                return {"authorized": True, "approved": False, "error": "invalid_kind_action"}
            for key in ("title", "summary", "reason", "subtype"):
                if key in changes:
                    item[key] = str(changes.get(key) or "")[:12000]
            item["kind"] = kind
            item["action"] = action
            if "payload" in changes:
                if not isinstance(changes["payload"], dict):
                    return {"authorized": True, "approved": False, "error": "payload_must_be_object"}
                item["payload"] = changes["payload"]
            item["updated_at"] = iso_now()
            item["dedupe_key"] = self._signature(item)
            self._write(queue)
        return {"authorized": True, "approved": False, "decision": "edit", "item": item, "result": "edited"}

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

    def _read_schedule_state(self) -> dict[str, Any]:
        if not self.schedule_path.exists():
            return {}
        try:
            value = json.loads(self.schedule_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_schedule_state(self, state: dict[str, Any]) -> None:
        temporary = self.schedule_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.schedule_path)
