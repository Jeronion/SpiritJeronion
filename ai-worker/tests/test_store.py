import tempfile
import unittest
from pathlib import Path

from spirit_worker.database import Store


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_task_is_created_only_after_approval(self) -> None:
        source_id = self.store.create_source({"type": "manual", "title": "Тест"}, "Исправить двойку")
        proposal = self.store.create_proposal({
            "type": "task.create",
            "title": "Исправить двойку",
            "reason": "Пользователь сообщил о задаче",
            "confidence": 0.9,
            "payload": {"title": "Исправить двойку", "important": True, "urgent": True},
        }, source_id)
        self.assertEqual(self.store.list_tasks(), [])
        result = self.store.decide(proposal["id"], "approve")
        self.assertEqual(result["proposal"]["status"], "applied")
        self.assertEqual(self.store.list_tasks()[0]["quadrant"], 1)

    def test_rejection_does_not_create_task(self) -> None:
        source_id = self.store.create_source({"type": "email", "title": "Письмо"}, "Неясное сообщение")
        proposal = self.store.create_proposal({"type": "task.create", "title": "Проверить", "payload": {}}, source_id)
        result = self.store.decide(proposal["id"], "reject")
        self.assertEqual(result["proposal"]["status"], "rejected")
        self.assertEqual(self.store.list_tasks(), [])


if __name__ == "__main__":
    unittest.main()
