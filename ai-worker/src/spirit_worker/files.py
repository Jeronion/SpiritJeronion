from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any


TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".heic"}


def _allowed(path: Path, project_root: Path) -> bool:
    roots = ((project_root / "uploads").resolve(), (project_root / "textbooks").resolve())
    return any(path.is_relative_to(root) for root in roots)


def collect(file_values: Any, project_root: str | Path | None = None) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(file_values, list):
        return "", []
    root = Path(project_root or os.environ.get("SPIRIT_PROJECT_ROOT", r"C:\SpiritJeronion")).resolve()
    contexts: list[str] = []
    attachments: list[dict[str, Any]] = []
    for value in file_values[:10]:
        raw_path = value.get("path") if isinstance(value, dict) else value
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = root / path
        path = path.resolve()
        if not _allowed(path, root):
            raise ValueError("file_outside_allowed_folders")
        if not path.is_file():
            raise ValueError("file_not_found")
        size = path.stat().st_size
        if size > 25 * 1024 * 1024:
            raise ValueError("file_too_large")
        extension = path.suffix.lower()
        item = {
            "name": path.name,
            "relative_path": str(path.relative_to(root)).replace("\\", "/"),
            "content_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            "size": size,
            "text_extracted": False,
        }
        if extension in TEXT_EXTENSIONS:
            text = path.read_text(encoding="utf-8", errors="replace")[:100_000]
            contexts.append(f"\n--- Файл {path.name} ---\n{text}")
            item["text_extracted"] = True
        elif extension == ".pdf":
            try:
                from pypdf import PdfReader  # type: ignore[import-not-found]

                pages = PdfReader(str(path)).pages[:50]
                text = "\n".join(page.extract_text() or "" for page in pages)[:150_000]
                contexts.append(f"\n--- PDF {path.name} ---\n{text}")
                item["text_extracted"] = bool(text.strip())
                item["pages_read"] = len(pages)
            except ImportError:
                item["notice"] = "Для извлечения текста PDF установите pypdf"
        elif extension in IMAGE_EXTENSIONS:
            item["notice"] = "Фотография зарегистрирована; OCR будет добавлен отдельным модулем"
        else:
            item["notice"] = "Файл зарегистрирован без извлечения текста"
        attachments.append(item)
    return "".join(contexts), attachments
