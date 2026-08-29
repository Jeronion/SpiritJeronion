import unittest
from datetime import datetime
from types import SimpleNamespace

from mesh_service.adapter import collect


class Endpoint:
    def __init__(self, result):
        self.result = result

    async def get(self, **kwargs):
        return self.result


class FakeClient:
    def __init__(self):
        self.homeworks = Endpoint(SimpleNamespace(payload=[SimpleNamespace(id=10, subject_name="Алгебра", description="№ 15", date="2026-09-02")]))
        self.events = Endpoint(SimpleNamespace(response=[SimpleNamespace(id=20, subject_name="Физика", date="2026-09-01", begin_time="09:00", end_time="09:45", room_name="205")]))
        self.closed = False

    async def get_me(self):
        return SimpleNamespace(children=[SimpleNamespace(contingent_guid="student-guid")])

    async def close(self):
        self.closed = True


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_collects_and_normalizes_homework_and_events(self):
        client = FakeClient()
        result = await collect(client, datetime(2026, 9, 1), datetime(2026, 9, 7))
        self.assertEqual(result["counts"], {"homework": 1, "events": 1})
        self.assertEqual(result["items"][0]["kind"], "homework")
        self.assertEqual(result["items"][1]["payload"]["start_at"], "2026-09-01T09:00:00")
        self.assertTrue(client.closed)


if __name__ == "__main__":
    unittest.main()
