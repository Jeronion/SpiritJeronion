import unittest
from unittest.mock import patch

from spirit_worker.ai import analyze


class AiTests(unittest.TestCase):
    @patch("spirit_worker.ai.urllib.request.urlopen", side_effect=OSError("offline"))
    def test_fallback_marks_tomorrow_grade_task_urgent_and_important(self, _urlopen) -> None:
        proposals, provider = analyze(
            "Нужно исправить двойку по алгебре до завтра",
            {"type": "manual", "title": "Тест"},
        )
        self.assertEqual(provider, "fallback")
        self.assertTrue(proposals[0]["payload"]["urgent"])
        self.assertTrue(proposals[0]["payload"]["important"])


if __name__ == "__main__":
    unittest.main()
