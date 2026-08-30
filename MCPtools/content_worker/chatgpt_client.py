from __future__ import annotations

import logging
import os
import socket
import subprocess
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
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
        except ImportError as exc:
            raise RuntimeError("chatgpt_automation_not_installed") from exc

        profile_dir = (self.project_root / ".cache" / "chatgpt-profile").resolve()
        profile_dir.mkdir(parents=True, exist_ok=True)
        default_chrome = Path(r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")
        default_driver = self.project_root / "launcher" / "bin" / "chromedriver.exe"
        chrome_path = Path(os.getenv("CHATGPT_CHROME_PATH", str(default_chrome))).resolve()
        driver_path = Path(os.getenv("CHATGPT_CHROME_DRIVER_PATH", str(default_driver))).resolve()
        if not chrome_path.is_file():
            raise FileNotFoundError(f"chrome_not_found: {chrome_path}")
        if not driver_path.is_file():
            raise FileNotFoundError(f"chromedriver_not_found: {driver_path}")

        def launch_chrome(bot: Any, port: int, url: str) -> None:
            target = url if "://" in url else f"https://{url}"
            subprocess.Popen(
                [
                    str(chrome_path),
                    f"--remote-debugging-port={port}",
                    f"--user-data-dir={profile_dir}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    target,
                ],
                cwd=self.project_root,
            )
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                with socket.socket() as probe:
                    probe.settimeout(0.5)
                    if probe.connect_ex(("127.0.0.1", port)) == 0:
                        return
                time.sleep(0.25)
            raise TimeoutError("chrome_debug_port_timeout")

        def setup_webdriver(bot: Any, port: int) -> Any:
            options = webdriver.ChromeOptions()
            options.binary_location = str(chrome_path)
            options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
            return webdriver.Chrome(service=Service(str(driver_path)), options=options)

        def prompt_element(bot: Any) -> Any:
            selectors = [
                "#prompt-textarea",
                "textarea#prompt-textarea",
                "div[contenteditable='true'][data-placeholder]",
                "div[contenteditable='true'].ProseMirror",
            ]
            for selector in selectors:
                elements = bot.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    return elements[-1]
            if bot.driver.find_elements(By.CSS_SELECTOR, "a[href*='auth/login'], a[href*='auth.openai.com']"):
                raise RuntimeError("chatgpt_login_required")
            raise RuntimeError("chatgpt_prompt_not_found")

        def send_prompt(bot: Any, prompt: str) -> None:
            bot._spirit_answer_count = len(
                bot.driver.find_elements(By.CSS_SELECTOR, "[data-message-author-role='assistant']")
            )
            bot._spirit_user_count = len(
                bot.driver.find_elements(By.CSS_SELECTOR, "[data-message-author-role='user']")
            )
            box = prompt_element(bot)
            box.click()
            box.send_keys(prompt)
            deadline = time.monotonic() + 10
            sent = False
            while time.monotonic() < deadline:
                buttons = bot.driver.find_elements(
                    By.CSS_SELECTOR,
                    "button[data-testid='send-button'], button[aria-label*='Отправить'], button[aria-label*='Send']",
                )
                buttons = [button for button in buttons if button.is_displayed() and button.is_enabled()]
                if buttons:
                    buttons[-1].click()
                    sent = True
                    break
                time.sleep(0.25)
            if not sent:
                box.send_keys(Keys.ENTER)
            deadline = time.monotonic() + 15
            baseline = int(getattr(bot, "_spirit_user_count", 0))
            while time.monotonic() < deadline:
                messages = bot.driver.find_elements(By.CSS_SELECTOR, "[data-message-author-role='user']")
                if len(messages) > baseline:
                    return
                time.sleep(0.25)
            raise RuntimeError("chatgpt_prompt_not_sent")

        def check_response(bot: Any) -> bool:
            answers = bot.driver.find_elements(By.CSS_SELECTOR, "[data-message-author-role='assistant']")
            baseline = int(getattr(bot, "_spirit_answer_count", 0))
            generating = bool(bot.driver.find_elements(By.CSS_SELECTOR, "button[data-testid='stop-button']"))
            return len(answers) > baseline and not generating and bool(answers[-1].text.strip())

        def return_last_response(bot: Any) -> str:
            answers = bot.driver.find_elements(By.CSS_SELECTOR, "[data-message-author-role='assistant']")
            return answers[-1].text.strip() if answers else ""

        def upload_file(bot: Any, filename: str, retry_count: int = 1) -> None:
            path = Path(filename).resolve()
            if not path.is_file():
                raise FileNotFoundError(path)
            inputs = bot.driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            if not inputs:
                raise RuntimeError("chatgpt_file_input_not_found")
            inputs[-1].send_keys(str(path))
            time.sleep(3)

        ChatGPTAutomation.launch_chrome_with_remote_debugging = launch_chrome
        ChatGPTAutomation.setup_webdriver = setup_webdriver
        ChatGPTAutomation.send_prompt_to_chatgpt = send_prompt
        ChatGPTAutomation.check_response_status = check_response
        ChatGPTAutomation.return_last_response = return_last_response
        ChatGPTAutomation.upload_file_for_prompt = upload_file

        log_path = self.project_root / ".cache" / "chatgpt_automation.log"
        root_logger = logging.getLogger()
        if not any(getattr(handler, "baseFilename", None) == str(log_path) for handler in root_logger.handlers):
            handler = logging.FileHandler(log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s:%(levelname)s:%(message)s"))
            root_logger.addHandler(handler)

        kwargs: dict[str, str] = {
            "chrome_path": str(chrome_path),
            "chrome_driver_path": str(driver_path),
            "user_data_dir": str(profile_dir),
        }
        email = os.getenv("CHATGPT_EMAIL", "").strip()
        password = os.getenv("CHATGPT_PASSWORD", "").strip()
        if email and password:
            kwargs.update(username=email, password=password)
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
