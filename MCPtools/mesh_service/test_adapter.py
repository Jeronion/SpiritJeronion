import unittest
from datetime import datetime
from types import SimpleNamespace

from mesh_service.adapter import collect, normalize_event, normalize_homework


class Endpoint:
    def __init__(self, result):
        self.result = result

    async def get(self, **kwargs):
        return self.result


class FakeClient:
    def __init__(self):
        self.homeworks = Endpoint(SimpleNamespace(payload=[SimpleNamespace(homework_id=10, subject_name="Алгебра", homework="№ 15", description="Письменно", date_prepared_for="2026-09-02", homework_updated_at="2026-09-01T12:00:00", materials=[])]))
        self.events = Endpoint(SimpleNamespace(response=[SimpleNamespace(id=20, subject_name="Физика", start_at="2026-09-01T09:00:00+03:00", finish_at="2026-09-01T09:45:00+03:00", room_name="205", cancelled=False, replaced=True, lesson_theme="Механика")]))
        self.closed = False

    async def get_me(self):
        return SimpleNamespace(children=[SimpleNamespace(contingent_guid="student-guid")])

    async def close(self):
        self.closed = True


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_collects_and_normalizes_homework_and_events(self):
        client = FakeClient()
        result = await collect(client, datetime(2026, 9, 1), datetime(2026, 9, 7))
        self.assertTrue(result["ok"])
        self.assertEqual(result["counts"], {"homework": 1, "events": 1, "total": 2})
        homework = next(item for item in result["items"] if item["kind"] == "homework")
        event = next(item for item in result["items"] if item["kind"] == "event")
        self.assertEqual(homework["payload"]["due_at"], "2026-09-02T00:00:00")
        self.assertEqual(event["payload"]["start_at"], "2026-09-01T09:00:00+03:00")
        self.assertTrue(event["payload"]["replaced"])
        self.assertTrue(client.closed)

    def test_normalizes_materials_and_cancelled_lesson(self):
        homework = normalize_homework({"homework_id": 7, "subject_name": "История", "homework": "§ 3", "date_prepared_for": "2026-09-03", "materials": [{"uuid": "m1", "title": "Карта", "type": "file", "urls": [{"url": "https://example.test/map", "type": "download"}]}]})
        event = normalize_event({"id": 8, "subject_name": "Химия", "start_at": "2026-09-03T10:00:00+03:00", "finish_at": "2026-09-03T10:45:00+03:00", "cancelled": True})
        self.assertEqual(homework["attachments"][0]["urls"][0]["url"], "https://example.test/map")
        self.assertTrue(event["payload"]["cancelled"])
        self.assertIn("отменён", event["text"])


if __name__ == "__main__":
    unittest.main()
