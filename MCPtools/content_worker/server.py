from __future__ import annotations

import json
import logging
import os
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .chatgpt_client import ChatGPTAutomationClient
from .storage import SiteStore, now_iso
from .telegram_bot import TelegramBotCollector
from .queue_store import QueueStore
from .memory import MemoryStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTOMATION_LOG = PROJECT_ROOT / ".cache" / "chatgpt_automation.log"
AUTOMATION_LOG.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(AUTOMATION_LOG),
    level=logging.INFO,
    format="%(asctime)s:%(levelname)s:%(message)s",
    force=True,
)
STORE = SiteStore(PROJECT_ROOT)
CHATGPT = ChatGPTAutomationClient(PROJECT_ROOT)
MEMORY = MemoryStore(PROJECT_ROOT)
TELEGRAM = TelegramBotCollector(MEMORY, PROJECT_ROOT)
QUEUE = QueueStore(PROJECT_ROOT)


def normalize_proposal(body: dict[str, Any]) -> dict[str, Any]:
    value = body.get("item") if isinstance(body.get("item"), dict) else body
    if isinstance(value.get("item"), dict):
        inner = dict(value["item"])
        inner.setdefault("id", value.get("id"))
        return inner
    return value


class Handler(BaseHTTPRequestHandler):
    server_version = "SpiritContentWorker/1.0"

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._headers()
        self.end_headers()

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route != "/api/health":
            return self._json(404, {"ok": False, "error": "not_found"})
        self._json(200, {"ok": True, "service": "content-worker", "github_sync": bool(STORE.github_token), "chatgpt": CHATGPT.status(), "telegram": TELEGRAM.status(), "memory": MEMORY.status()})

    def do_POST(self) -> None:
        try:
            body = self._body()
            expected = os.getenv("SPIRIT_QUEUE_SECRET", "")
            supplied = str(body.get("secret") or "")
            if not expected or supplied != expected:
                return self._json(401, {"ok": False, "error": "unauthorized"})
            route = urlparse(self.path).path
            if route == "/api/queue/list":
                return self._json(200, QUEUE.list())
            if route == "/api/queue/enqueue":
                values = body.get("items") if isinstance(body.get("items"), list) else [body.get("item") or body]
                created = QUEUE.enqueue(values)
                try:
                    TELEGRAM.notify_proposals(created)
                except Exception as exc:
                    print(f"Telegram notification failed: {exc}", flush=True)
                return self._json(200, {"ok": True, "reply": body.get("reply"), "proposals": created, "queued": [{"id": item["id"], "status": item["status"]} for item in created]})
            if route == "/api/queue/decision":
                if str(body.get("decision") or "") == "edit":
                    changes = body.get("changes") if isinstance(body.get("changes"), dict) else {}
                    return self._json(200, QUEUE.edit(str(body.get("id") or ""), changes))
                return self._json(200, QUEUE.decide(str(body.get("id") or ""), str(body.get("decision") or "")))
            if route == "/api/memory/list":
                return self._json(200, {"ok": True, "documents": MEMORY.list(int(body.get("limit") or 100))})
            if route == "/api/memory/search":
                return self._json(200, {"ok": True, "results": MEMORY.search(str(body.get("query") or ""), int(body.get("limit") or 5))})
            proposal = normalize_proposal(body)
            if route == "/api/calendar/upsert":
                result = STORE.upsert_event(proposal)
            elif route == "/api/tasks/upsert":
                result = STORE.upsert_task(proposal)
            elif route == "/api/notes/generate":
                result = self._generate("note", proposal)
            elif route == "/api/homework/solve":
                result = self._generate("homework", proposal)
            else:
                return self._json(404, {"ok": False, "error": "not_found"})
            self._json(200, {"ok": True, "result": result, "github_sync": bool(STORE.github_token)})
        except Exception as exc:
            traceback.print_exc()
            self._json(500, {"ok": False, "error": type(exc).__name__, "message": str(exc)})

    def _generate(self, mode: str, proposal: dict[str, Any]) -> dict[str, Any]:
        text = CHATGPT.generate(mode, proposal)
        source = proposal.get("source") or {}
        title = proposal.get("title") or ("Конспект" if mode == "note" else "Решение ДЗ")
        header = (
            f"# {title}\n\n"
            f"> Создано: {now_iso()}  \n"
            f"> Источник запроса: {source.get('title') or source.get('type') or 'сайт'}  \n"
            f"> Требует проверки учеником.\n\n"
        )
        return STORE.save_material(mode, proposal, header + text)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 10_000_000:
            raise ValueError("invalid_body_size")
        raw = self.rfile.read(length)
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("body_must_be_object")
        return value

    def _headers(self) -> None:
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-store")

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._headers()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[content-worker] {self.address_string()} {fmt % args}", flush=True)


def run() -> None:
    host = os.getenv("CONTENT_WORKER_HOST", "127.0.0.1")
    port = int(os.getenv("CONTENT_WORKER_PORT", "8910"))
    server = ThreadingHTTPServer((host, port), Handler)
    TELEGRAM.start()
    print(f"Content worker ready on http://{host}:{port}", flush=True)
    server.serve_forever()
