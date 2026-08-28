from __future__ import annotations

import json
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .ai import analyze
from .database import Store
from .files import collect


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "SpiritWorker/0.1"

    @property
    def store(self) -> Store:
        return self.server.store  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")

    def _origin(self) -> str:
        origin = self.headers.get("Origin", "")
        allowed = {
            "https://jeronion.github.io",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8123",
            "http://127.0.0.1:8123",
        }
        return origin if origin in allowed else ""

    def _send(self, status: int, value: dict[str, Any] | list[Any]) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        origin = self._origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 10_000_000:
            raise ValueError("invalid_body_size")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("body_must_be_object")
        return value

    def _authorized(self) -> bool:
        expected = os.environ.get("SPIRIT_WORKER_KEY", "")
        return not expected or self.headers.get("X-Spirit-Key", "") == expected

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        origin = self._origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Spirit-Key")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Vary", "Origin")
        self.end_headers()

    def do_GET(self) -> None:
        route = urlparse(self.path)
        query = parse_qs(route.query)
        try:
            if route.path == "/api/health":
                self._send(HTTPStatus.OK, {"ok": True, "service": "spirit-worker", "version": "0.1.0"})
            elif route.path == "/api/state":
                self._send(HTTPStatus.OK, self.store.state())
            elif route.path == "/api/tasks":
                self._send(HTTPStatus.OK, {"tasks": self.store.list_tasks()})
            elif route.path == "/api/proposals":
                status = query.get("status", [None])[0]
                self._send(HTTPStatus.OK, {"proposals": self.store.list_proposals(status)})
            else:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        except Exception as error:
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": type(error).__name__, "message": str(error)})

    def do_POST(self) -> None:
        if not self._authorized():
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        try:
            body = self._body()
            route = urlparse(self.path).path
            if route == "/api/intake":
                text = str(body.get("text") or "").strip()
                if not text:
                    raise ValueError("text_required")
                source = body.get("source") if isinstance(body.get("source"), dict) else {"type": "manual", "title": "Ручной ввод"}
                file_context, attachments = collect(body.get("files"))
                source = dict(source)
                metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
                source["metadata"] = {**metadata, "attachments": attachments}
                combined_text = text + file_context
                source_id = self.store.create_source(source, combined_text)
                items, provider = analyze(combined_text, source)
                proposals = [self.store.create_proposal(item, source_id) for item in items]
                self._send(HTTPStatus.CREATED, {"provider": provider, "source_id": source_id, "attachments": attachments, "proposals": proposals})
                return
            match = re.fullmatch(r"/api/proposals/([0-9a-f-]+)/decision", route)
            if match:
                result = self.store.decide(match.group(1), str(body.get("decision") or ""), body.get("payload"))
                self._send(HTTPStatus.OK, result)
                return
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        except KeyError as error:
            self._send(HTTPStatus.NOT_FOUND, {"error": str(error)})
        except (ValueError, json.JSONDecodeError) as error:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except Exception as error:
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": type(error).__name__, "message": str(error)})


class SpiritServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], store: Store) -> None:
        super().__init__(address, ApiHandler)
        self.store = store


def run() -> None:
    host = os.environ.get("SPIRIT_WORKER_HOST", "127.0.0.1")
    port = int(os.environ.get("SPIRIT_WORKER_PORT", "8899"))
    store = Store()
    server = SpiritServer((host, port), store)
    print(f"SpiritJeronion AI Worker: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
