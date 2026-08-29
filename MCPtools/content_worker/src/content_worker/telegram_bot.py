from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class TelegramBotCollector:
    """Long-polling Telegram collector that forwards approved-user messages to n8n."""

    def __init__(self) -> None:
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.allowed_user_id = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip()
        self.n8n_url = os.getenv("N8N_INTERNAL_URL", "http://127.0.0.1:5678").rstrip("/")
        self.queue_secret = os.getenv("SPIRIT_QUEUE_SECRET", "")
        self.running = False
        self.bot_username: str | None = None
        self.last_error: str | None = None
        self.last_update_at: str | None = None
        self._thread: threading.Thread | None = None

    def status(self) -> dict[str, Any]:
        return {
            "configured": bool(self.token),
            "paired": bool(self.allowed_user_id),
            "running": self.running,
            "bot_username": self.bot_username,
            "last_update_at": self.last_update_at,
            "last_error": self.last_error,
        }

    def start(self) -> None:
        if not self.token or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="telegram-bot", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self.running = True
        offset: int | None = None
        try:
            me = self._telegram("getMe", {})
            self.bot_username = str((me.get("result") or {}).get("username") or "") or None
            print(f"Telegram bot collector ready: @{self.bot_username or 'unknown'}", flush=True)
            while True:
                payload: dict[str, Any] = {"timeout": 25, "allowed_updates": ["message"]}
                if offset is not None:
                    payload["offset"] = offset
                result = self._telegram("getUpdates", payload)
                for update in result.get("result") or []:
                    offset = int(update.get("update_id", 0)) + 1
                    self._handle(update)
                self.last_error = None
        except Exception as exc:
            self.last_error = self._safe_error(exc)
            print(f"Telegram collector stopped: {self.last_error}", flush=True)
        finally:
            self.running = False

    def _handle(self, update: dict[str, Any]) -> None:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        chat_id = chat.get("id")
        user_id = str(sender.get("id") or "")
        if not chat_id or not user_id:
            return
        if not self.allowed_user_id:
            self._send(chat_id, f"Твой Telegram ID: {user_id}\nДобавь TELEGRAM_ALLOWED_USER_ID={user_id} в secrets/keys.env и перезапусти content worker.")
            return
        if user_id != self.allowed_user_id:
            self._send(chat_id, "Этот бот привязан к другому пользователю.")
            return
        text = str(message.get("text") or message.get("caption") or "").strip()
        media = self._media_description(message)
        text = "\n".join(value for value in (text, media) if value).strip()
        if text.startswith("/start"):
            self._send(chat_id, "Бот подключён. Перешли мне сообщение из школьного чата — оно попадёт в очередь SpiritJeronion.")
            return
        if not text:
            self._send(chat_id, "В сообщении нет текста, который можно распознать.")
            return
        origin = self._origin(message)
        response = self._n8n({"secret": self.queue_secret, "text": text, "history": [], "source_type": "telegram", "source_title": origin["title"], "source_sender": origin["sender"], "message_id": str(message.get("message_id") or update.get("update_id") or "")})
        queued = response.get("queued") or []
        self.last_update_at = datetime.now(timezone.utc).isoformat()
        self._send(chat_id, f"Готово: добавлено в очередь предложений — {len(queued)}." if queued else "Сообщение распознано, но изменений для очереди не найдено.")

    def _origin(self, message: dict[str, Any]) -> dict[str, str]:
        origin = message.get("forward_origin") or {}
        origin_type = origin.get("type")
        if origin_type == "user":
            user = origin.get("sender_user") or {}
            sender = " ".join(str(user.get(k) or "") for k in ("first_name", "last_name")).strip()
            return {"title": "Переслано из Telegram", "sender": sender or "пользователь Telegram"}
        if origin_type in {"chat", "channel"}:
            source = origin.get("sender_chat") or origin.get("chat") or {}
            return {"title": str(source.get("title") or "Telegram"), "sender": str(origin.get("author_signature") or source.get("title") or "Telegram")}
        if origin_type == "hidden_user":
            name = str(origin.get("sender_user_name") or "скрытый пользователь")
            return {"title": "Переслано из Telegram", "sender": name}
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        name = " ".join(str(sender.get(k) or "") for k in ("first_name", "last_name")).strip()
        return {"title": str(chat.get("title") or "Telegram"), "sender": name or str(sender.get("username") or "Telegram")}

    @staticmethod
    def _media_description(message: dict[str, Any]) -> str:
        if message.get("document"):
            doc = message["document"]
            return f"Вложение: документ {doc.get('file_name') or ''} ({doc.get('mime_type') or 'неизвестный тип'})".strip()
        if message.get("photo"):
            return "Вложение: фотография"
        if message.get("video"):
            return "Вложение: видео"
        if message.get("voice"):
            return "Вложение: голосовое сообщение"
        return ""

    def _send(self, chat_id: int | str, text: str) -> None:
        self._telegram("sendMessage", {"chat_id": chat_id, "text": text})

    def _telegram(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post(f"https://api.telegram.org/bot{self.token}/{method}", payload)

    def _n8n(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post(f"{self.n8n_url}/webhook/sj-chat", payload)

    @staticmethod
    def _post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=40) as response:
            value = json.loads(response.read().decode("utf-8"))
        if not isinstance(value, dict) or value.get("ok") is False:
            raise RuntimeError(str(value.get("description") if isinstance(value, dict) else "invalid_response"))
        return value

    def _safe_error(self, exc: Exception) -> str:
        value = str(exc)
        if self.token:
            value = value.replace(self.token, "[redacted]")
        if isinstance(exc, (HTTPError, URLError)) and not value:
            value = type(exc).__name__
        return value[:500]

