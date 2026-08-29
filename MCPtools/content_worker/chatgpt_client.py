from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any


class ChatGPTAutomationClient:
    """Lazy, serial adapter around the Selenium-based ChatGPTAutomation package."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self._bot: Any = None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return os.getenv("CHATGPT_AUTOMATION_ENABLED", "false").lower() in {"1", "true", "yes"}

    def status(self) -> dict[str, Any]:
        try:
            import chatgpt_automation  # noqa: F401
            installed = True
        except ImportError:
            installed = False
        return {"enabled": self.enabled, "installed": installed, "browser_started": self._bot is not None}

    def generate(self, mode: str, proposal: dict[str, Any]) -> str:
        if not self.enabled:
            raise RuntimeError("chatgpt_automation_disabled")
        with self._lock:
            bot = self._get_bot()
            payload = proposal.get("payload") or {}
            attachments = payload.get("attachments") or proposal.get("attachments") or []
            for value in attachments[:10]:
                path = self._attachment_path(value)
                bot.upload_file_for_prompt(str(path))
            prompt = self._prompt(mode, proposal)
            bot.send_prompt_to_chatgpt(prompt)
            deadline = time.monotonic() + int(os.getenv("CHATGPT_RESPONSE_TIMEOUT", "300"))
            while time.monotonic() < deadline:
                if bot.check_response_status():
                    response = bot.return_last_response()
                    if response and str(response).strip():
                        return str(response).strip()
                time.sleep(5)
            raise TimeoutError("chatgpt_response_timeout")

    def _get_bot(self) -> Any:
        if self._bot is not None:
            return self._bot
        try:
            from chatgpt_automation.chatgpt_automation import ChatGPTAutomation
        except ImportError as exc:
            raise RuntimeError("chatgpt_automation_not_installed") from exc
        kwargs: dict[str, str] = {}
        email = os.getenv("CHATGPT_EMAIL", "").strip()
        password = os.getenv("CHATGPT_PASSWORD", "").strip()
        chrome_path = os.getenv("CHATGPT_CHROME_PATH", "").strip()
        driver_path = os.getenv("CHATGPT_CHROME_DRIVER_PATH", "").strip()
        if email and password:
            kwargs.update(username=email, password=password)
        if chrome_path:
            kwargs["chrome_path"] = chrome_path
        if driver_path:
            kwargs["chrome_driver_path"] = driver_path
        self._bot = ChatGPTAutomation(**kwargs)
        return self._bot

    def _attachment_path(self, value: Any) -> Path:
        raw = value.get("path") if isinstance(value, dict) else value
        path = Path(str(raw))
        if not path.is_absolute():
            path = self.project_root / path
        path = path.resolve()
        allowed = [self.project_root, (self.project_root / "WebsiteHosting").resolve()]
        if not any(root == path or root in path.parents for root in allowed):
            raise ValueError("attachment_outside_project")
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    @staticmethod
    def _prompt(mode: str, proposal: dict[str, Any]) -> str:
        payload = proposal.get("payload") or {}
        subject = payload.get("subject") or proposal.get("subject") or "не указан"
        task = payload.get("task") or proposal.get("summary") or proposal.get("title") or ""
        evidence = proposal.get("evidence") or []
        sources = payload.get("sources") or evidence
        if mode == "note":
            return (
                "Напиши качественный школьный конспект на русском языке в формате Markdown. "
                "Не выдумывай факты и ссылки. Объясняй понятно, структурируй заголовками, "
                "выдели определения и в конце добавь краткое повторение. "
                f"Предмет: {subject}. Тема и задание: {task}. Источники: {sources}. "
                "Если загружены файлы, используй их как основные источники и укажи страницы, когда они видны."
            )
        return (
            "Реши школьное практическое домашнее задание на русском языке. Верни Markdown. "
            "Покажи ход решения, итоговый ответ и отдельно перечисли места, которые ученик должен проверить. "
            "Не утверждай, что работа сдана. "
            f"Предмет: {subject}. Условие: {task}. Источники: {sources}. "
            "Если загружены файлы, внимательно учти их содержимое."
        )
