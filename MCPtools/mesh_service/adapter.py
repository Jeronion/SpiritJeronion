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


def normalize_homework(value: Any) -> dict[str, Any]:
    data = _dump(value)
    subject = str(_value(data, "subject_name", "subject", "discipline_name", default="Без предмета"))
    description = str(_value(data, "description", "homework", "text", "task", default=""))
    homework_id = str(_value(data, "id", "homework_id", "external_id", default=""))
    due_at = _iso(_value(data, "date", "due_date", "deadline", "planned_date"))
    return {
        "id": f"mesh-homework-{homework_id}" if homework_id else "",
        "kind": "homework",
        "subject": subject,
        "title": f"Домашнее задание — {subject}",
        "text": description,
        "updated_at": _iso(_value(data, "updated_at", "created_at")) or datetime.now(UTC).isoformat(),
        "url": _value(data, "url", "link"),
        "attachments": _value(data, "attachments", "materials", default=[]) or [],
        "payload": {"subject": subject, "task": description, "due_at": due_at, "raw_id": homework_id},
    }


def normalize_event(value: Any) -> dict[str, Any]:
    data = _dump(value)
    subject = str(_value(data, "subject_name", "subject", "title", "name", default="Событие МЭШ"))
    event_id = str(_value(data, "id", "event_id", "external_id", default=""))
    day_value = _value(data, "date", "event_date", "lesson_date", "start_date")
    start_at = _iso(_value(data, "start_at", "begin_at", "begin_time", "start_time"), day_value)
    end_at = _iso(_value(data, "end_at", "finish_at", "end_time", "finish_time"), day_value)
    room = str(_value(data, "room_name", "room", "room_number", default=""))
    teacher = str(_value(data, "teacher_name", "teacher", default=""))
    pieces = [subject]
    if start_at:
        pieces.append(f"начало {start_at}")
    if end_at:
        pieces.append(f"окончание {end_at}")
    if room:
        pieces.append(f"кабинет {room}")
    return {
        "id": f"mesh-event-{event_id}" if event_id else "",
        "kind": "event",
        "subject": subject,
        "title": subject,
        "text": ", ".join(pieces),
        "updated_at": _iso(_value(data, "updated_at", "created_at")) or datetime.now(UTC).isoformat(),
        "url": _value(data, "url", "link"),
        "attachments": [],
        "payload": {"title": subject, "start_at": start_at, "end_at": end_at, "timezone": "Europe/Moscow", "location": room, "teacher": teacher, "raw_id": event_id},
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
        )
        homeworks = getattr(homeworks_result, "payload", None) or _dump(homeworks_result).get("payload") or []
        events = getattr(events_result, "response", None) or _dump(events_result).get("response") or []
        items = [normalize_homework(item) for item in homeworks] + [normalize_event(item) for item in events]
        return {"items": items, "counts": {"homework": len(homeworks), "events": len(events)}, "from": from_date.isoformat(), "to": to_date.isoformat(), "generated_at": datetime.now(UTC).isoformat()}
    finally:
        await _close(client)


def build_client(token: str, profile_id: int) -> Any:
    from schoolmospy import StudentClient

    return StudentClient(token=token, profile_id=profile_id)
