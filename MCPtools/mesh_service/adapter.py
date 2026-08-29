from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Callable


def _dump(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        result = value.model_dump(mode="json")
        return result if isinstance(result, dict) else {}
    if hasattr(value, "dict"):
        result = value.dict()
        return result if isinstance(result, dict) else {}
    try:
        return dict(vars(value))
    except TypeError:
        return {}


def _value(data: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        value = data.get(name)
        if value not in (None, ""):
            return value
    return default


def _iso(value: Any, day_value: Any = None) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return datetime.combine(value, time.min).isoformat()
    text = str(value).strip()
    if not text:
        return None
    if len(text) <= 8 and ":" in text and day_value:
        try:
            day = date.fromisoformat(str(day_value)[:10])
            clock = time.fromisoformat(text)
            return datetime.combine(day, clock).isoformat()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return text


def _attachments(data: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in data.get("materials") or []:
        material = _dump(raw)
        urls = []
        for raw_url in material.get("urls") or []:
            url_data = _dump(raw_url)
            url = str(_value(url_data, "url", default="")).strip()
            if url:
                urls.append({"url": url, "type": str(_value(url_data, "type", default=""))})
        result.append(
            {
                "kind": "material",
                "id": str(_value(material, "uuid", "id", default="")),
                "title": str(_value(material, "title", "type_name", default="Материал МЭШ")),
                "type": str(_value(material, "type", "content_type", default="material")),
                "description": str(_value(material, "description", default="") or ""),
                "urls": urls,
            }
        )
    for raw in data.get("attachments") or []:
        attachment = _dump(raw)
        if attachment:
            result.append(
                {
                    "kind": "attachment",
                    "id": str(_value(attachment, "id", "uuid", default="")),
                    "title": str(_value(attachment, "title", "name", "file_name", default="Файл МЭШ")),
                    "url": _value(attachment, "url", "download_url", "link"),
                    "mime_type": _value(attachment, "mime_type", "content_type"),
                }
            )
        elif raw not in (None, ""):
            result.append({"kind": "attachment", "title": str(raw)})
    return result


def normalize_homework(value: Any) -> dict[str, Any]:
    data = _dump(value)
    subject = str(_value(data, "subject_name", "subject", "discipline_name", default="Без предмета"))
    text_parts = []
    for field in ("homework", "description", "text", "task"):
        part = str(data.get(field) or "").strip()
        if part and part not in text_parts:
            text_parts.append(part)
    description = "\n".join(text_parts)
    homework_id = str(_value(data, "homework_id", "homework_entry_id", "id", "external_id", default=""))
    due_at = _iso(_value(data, "date_prepared_for", "date", "due_date", "deadline", "planned_date"))
    assigned_at = _iso(_value(data, "date_assigned_on", "lesson_date_time"))
    attachments = _attachments(data)
    first_url = next((url.get("url") for item in attachments for url in item.get("urls", []) if url.get("url")), None)
    return {
        "id": f"mesh-homework-{homework_id}" if homework_id else "",
        "kind": "homework",
        "subject": subject,
        "title": f"Домашнее задание — {subject}",
        "text": description,
        "updated_at": _iso(_value(data, "homework_updated_at", "updated_at", "homework_created_at", "created_at")) or datetime.now(UTC).isoformat(),
        "url": _value(data, "url", "link") or first_url,
        "attachments": attachments,
        "payload": {
            "subject": subject,
            "task": description,
            "due_at": due_at,
            "assigned_at": assigned_at,
            "is_done": bool(data.get("is_done", False)),
            "has_teacher_answer": bool(data.get("has_teacher_answer", False)),
            "written_answer": data.get("written_answer"),
            "comments": data.get("comments") or [],
            "raw_id": homework_id,
            "homework_entry_id": _value(data, "homework_entry_id"),
        },
    }


def normalize_event(value: Any) -> dict[str, Any]:
    data = _dump(value)
    subject = str(_value(data, "subject_name", "subject", "title", "name", default="Событие МЭШ"))
    event_id = str(_value(data, "id", "event_id", "external_id", default=""))
    day_value = _value(data, "date", "event_date", "lesson_date", "start_date")
    start_at = _iso(_value(data, "start_at", "begin_at", "begin_time", "start_time"), day_value)
    end_at = _iso(_value(data, "finish_at", "end_at", "end_time", "finish_time"), day_value)
    room = str(_value(data, "room_name", "room", "room_number", default=""))
    teacher = str(_value(data, "teacher_name", "teacher", default=""))
    cancelled = bool(data.get("cancelled", False))
    replaced = bool(data.get("replaced", False))
    lesson_theme = str(data.get("lesson_theme") or "").strip()
    pieces = [f"Урок: {subject}"]
    if start_at:
        pieces.append(f"начало {start_at}")
    if end_at:
        pieces.append(f"окончание {end_at}")
    if room:
        pieces.append(f"кабинет {room}")
    if lesson_theme:
        pieces.append(f"тема: {lesson_theme}")
    if cancelled:
        pieces.append("урок отменён")
    if replaced:
        pieces.append("урок заменён")
    return {
        "id": f"mesh-event-{event_id}" if event_id else "",
        "kind": "event",
        "subject": subject,
        "title": subject,
        "text": ", ".join(pieces),
        "updated_at": _iso(_value(data, "updated_at", "created_at")) or datetime.now(UTC).isoformat(),
        "url": _value(data, "link_to_join", "url", "link"),
        "attachments": [],
        "payload": {
            "title": subject,
            "start_at": start_at,
            "end_at": end_at,
            "timezone": "Europe/Moscow",
            "location": room,
            "teacher": teacher,
            "cancelled": cancelled,
            "replaced": replaced,
            "lesson_type": data.get("lesson_type"),
            "lesson_theme": data.get("lesson_theme"),
            "embedded_homework": data.get("homework"),
            "marks": data.get("marks"),
            "raw_id": event_id,
        },
    }


async def _close(client: Any) -> None:
    close = getattr(client, "close", None)
    if not close:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


async def collect(client: Any, from_date: datetime, to_date: datetime, contingent_guid: str | None = None) -> dict[str, Any]:
    try:
        guid = contingent_guid
        if not guid:
            profile = await client.get_me()
            profile_data = _dump(profile)
            children = profile_data.get("children") or getattr(profile, "children", []) or []
            if not children:
                raise ValueError("mesh_profile_has_no_children")
            child = _dump(children[0])
            guid = str(_value(child, "contingent_guid", "person_id", "id", default=""))
        if not guid:
            raise ValueError("mesh_contingent_guid_missing")
        homeworks_result, events_result = await asyncio.gather(
            client.homeworks.get(from_date=from_date, to_date=to_date),
            client.events.get(from_date=from_date, to_date=to_date, contingent_guid=guid),
            return_exceptions=True,
        )
        errors = []
        if isinstance(homeworks_result, BaseException):
            homeworks = []
            errors.append({"source": "homeworks", "type": type(homeworks_result).__name__, "message": str(homeworks_result)[:500]})
        else:
            homeworks = getattr(homeworks_result, "payload", None) or _dump(homeworks_result).get("payload") or []
        if isinstance(events_result, BaseException):
            events = []
            errors.append({"source": "events", "type": type(events_result).__name__, "message": str(events_result)[:500]})
        else:
            events = getattr(events_result, "response", None) or _dump(events_result).get("response") or []
        if len(errors) == 2:
            raise homeworks_result
        items = [normalize_homework(item) for item in homeworks] + [normalize_event(item) for item in events]
        items.sort(key=lambda item: str((item.get("payload") or {}).get("due_at") or (item.get("payload") or {}).get("start_at") or ""))
        return {
            "ok": True,
            "partial": bool(errors),
            "items": items,
            "counts": {"homework": len(homeworks), "events": len(events), "total": len(items)},
            "errors": errors,
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "generated_at": datetime.now(UTC).isoformat(),
        }
    finally:
        await _close(client)


def build_client(token: str, profile_id: int) -> Any:
    from schoolmospy import StudentClient

    return StudentClient(token=token, profile_id=profile_id)
