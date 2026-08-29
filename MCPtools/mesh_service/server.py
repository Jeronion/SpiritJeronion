from __future__ import annotations

import asyncio
import base64
import json
import os
from datetime import date, datetime, time, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import __version__
from .adapter import build_client, collect


def _contingent_guid_from_token(token: str) -> str | None:
    """Read the non-secret student GUID claim; API still validates the token."""
    try:
        payload_part = token.split(".", 2)[1]
        padding = "=" * (-len(payload_part) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_part + padding))
        value = payload.get("msh")
        return str(value).strip() if value else None
    except (IndexError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _load_local_env() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _range(query: dict[str, list[str]]) -> tuple[datetime, datetime]:
    today = date.today()
    start_day = date.fromisoformat(query.get("from", [(today - timedelta(days=1)).isoformat()])[0])
    end_day = date.fromisoformat(query.get("to", [(today + timedelta(days=14)).isoformat()])[0])
    if end_day < start_day or (end_day - start_day).days > 45:
        raise ValueError("invalid_date_range")
    return datetime.combine(start_day, time.min), datetime.combine(end_day, time.max.replace(microsecond=0))


class Handler(BaseHTTPRequestHandler):
    server_version = "SpiritMesh/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")

    def _send(self, status: int, value: dict[str, Any]) -> None:
        body = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        route = urlparse(self.path)
        if route.path == "/api/health":
            configured = bool(os.environ.get("MESH_TOKEN") and os.environ.get("MESH_PROFILE_ID"))
            self._send(HTTPStatus.OK, {"ok": True, "service": "mesh-adapter", "version": __version__, "configured": configured})
            return
        if route.path != "/api/mesh/collect":
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            token = os.environ.get("MESH_TOKEN", "").strip()
            profile_raw = os.environ.get("MESH_PROFILE_ID", "").strip()
            if not token or not profile_raw:
                raise ValueError("mesh_credentials_not_configured")
            start, end = _range(parse_qs(route.query))
            client = build_client(token, int(profile_raw))
            contingent_guid = os.environ.get("MESH_CONTINGENT_GUID") or _contingent_guid_from_token(token)
            result = asyncio.run(collect(client, start, end, contingent_guid))
            self._send(HTTPStatus.OK, result)
        except ValueError as error:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except Exception as error:
            self._send(HTTPStatus.BAD_GATEWAY, {"error": type(error).__name__, "message": str(error)})


def run() -> None:
    _load_local_env()
    host = os.environ.get("MESH_HOST", "127.0.0.1")
    port = int(os.environ.get("MESH_PORT", "8900"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"SpiritJeronion MESH adapter: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
