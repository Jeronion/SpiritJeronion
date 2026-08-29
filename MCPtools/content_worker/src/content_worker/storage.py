from __future__ import annotations

import base64
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ_-]+", "-", value.strip().lower())
    return value.strip("-")[:72] or "material"


class SiteStore:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.site_root = (self.project_root / "WebsiteHosting").resolve()
        self.data_root = (self.site_root / "data").resolve()
        self.github_token = os.getenv("GITHUB_TOKEN", "").strip()
        self.github_repo = os.getenv("GITHUB_REPOSITORY", "Jeronion/SpiritJeronion").strip()
        self.github_branch = os.getenv("GITHUB_BRANCH", "main").strip()

    def _safe(self, relative: str) -> Path:
        target = (self.site_root / relative).resolve()
        if self.site_root not in target.parents:
            raise ValueError("path_outside_website")
        return target

    def read_json(self, relative: str, fallback: dict[str, Any]) -> dict[str, Any]:
        path = self._safe(relative)
        if not path.exists():
            return fallback
        return json.loads(path.read_text(encoding="utf-8"))

    def write(self, relative: str, content: str, message: str) -> None:
        path = self._safe(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        temp_path.replace(path)
        if self.github_token:
            self._github_put(relative.replace("\\", "/"), content, message)

    def write_json(self, relative: str, payload: dict[str, Any], message: str) -> None:
        self.write(relative, json.dumps(payload, ensure_ascii=False, indent=2) + "\n", message)

    def upsert_event(self, proposal: dict[str, Any]) -> dict[str, Any]:
        payload = proposal.get("payload") or {}
        event = {
            "id": proposal.get("id") or f"event-{int(datetime.now().timestamp())}",
            "title": proposal.get("title") or payload.get("title") or "Событие",
            "description": proposal.get("summary") or payload.get("description") or "",
            "start_at": payload.get("start_at"),
            "end_at": payload.get("end_at"),
            "timezone": payload.get("timezone") or "Europe/Moscow",
            "location": payload.get("location"),
            "source": proposal.get("source") or {},
            "updated_at": now_iso(),
        }
        doc = self.read_json("data/calendar.json", {"updated_at": None, "events": []})
        items = [item for item in doc.get("events", []) if item.get("id") != event["id"]]
        items.append(event)
        items.sort(key=lambda item: item.get("start_at") or "9999")
        doc = {"updated_at": now_iso(), "events": items}
        self.write_json("data/calendar.json", doc, f"calendar: {event['title']}")
        return event

    def upsert_task(self, proposal: dict[str, Any]) -> dict[str, Any]:
        payload = proposal.get("payload") or {}
        important = bool(payload.get("important", True))
        urgent = bool(payload.get("urgent", False))
        quadrant = payload.get("quadrant") or ("q1" if important and urgent else "q2" if important else "q3" if urgent else "q4")
        task = {
            "id": proposal.get("id") or f"task-{int(datetime.now().timestamp())}",
            "title": proposal.get("title") or payload.get("title") or "Задача",
            "description": proposal.get("summary") or payload.get("description") or "",
            "subject": payload.get("subject"),
            "due_at": payload.get("due_at"),
            "quadrant": quadrant,
            "status": payload.get("status") or "todo",
            "source": proposal.get("source") or {},
            "updated_at": now_iso(),
        }
        doc = self.read_json("data/tasks.json", {"updated_at": None, "tasks": []})
        items = [item for item in doc.get("tasks", []) if item.get("id") != task["id"]]
        items.append(task)
        doc = {"updated_at": now_iso(), "tasks": items}
        self.write_json("data/tasks.json", doc, f"tasks: {task['title']}")
        return task

    def save_material(self, kind: str, proposal: dict[str, Any], markdown: str) -> dict[str, Any]:
        folder = "notes" if kind == "note" else "homework"
        index_key = "notes" if kind == "note" else "items"
        title = proposal.get("title") or ("Конспект" if kind == "note" else "Решение ДЗ")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{stamp}-{slugify(title)}.md"
        relative_file = f"data/{folder}/{filename}"
        self.write(relative_file, markdown.rstrip() + "\n", f"{folder}: {title}")
        payload = proposal.get("payload") or {}
        record = {
            "id": proposal.get("id") or f"{folder}-{stamp}",
            "title": title,
            "subject": payload.get("subject") or proposal.get("subject"),
            "summary": proposal.get("summary") or payload.get("task") or "",
            "task": payload.get("task"),
            "created_at": now_iso(),
            "path": relative_file,
            "source": proposal.get("source") or {},
        }
        index_path = f"data/{folder}/index.json"
        doc = self.read_json(index_path, {"updated_at": None, index_key: []})
        items = [item for item in doc.get(index_key, []) if item.get("id") != record["id"]]
        items.insert(0, record)
        doc = {"updated_at": now_iso(), index_key: items}
        self.write_json(index_path, doc, f"{folder} index: {title}")
        return record

    def _github_put(self, relative: str, content: str, message: str) -> None:
        encoded_path = urllib.parse.quote(f"WebsiteHosting/{relative}", safe="/")
        url = f"https://api.github.com/repos/{self.github_repo}/contents/{encoded_path}"
        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SpiritJeronion-worker",
        }
        sha = None
        try:
            request = urllib.request.Request(f"{url}?ref={urllib.parse.quote(self.github_branch)}", headers=headers)
            with urllib.request.urlopen(request, timeout=30) as response:
                sha = json.load(response).get("sha")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        body = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": self.github_branch,
        }
        if sha:
            body["sha"] = sha
        request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={**headers, "Content-Type": "application/json"}, method="PUT")
        with urllib.request.urlopen(request, timeout=45):
            pass
