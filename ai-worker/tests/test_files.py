import tempfile
import unittest
from pathlib import Path

from spirit_worker.files import collect


class FileTests(unittest.TestCase):
    def test_reads_text_only_from_allowed_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            uploads = root / "uploads"
            uploads.mkdir()
            file = uploads / "task.txt"
            file.write_text("Упражнение 15", encoding="utf-8")
            context, attachments = collect(["uploads/task.txt"], root)
            self.assertIn("Упражнение 15", context)
            self.assertTrue(attachments[0]["text_extracted"])

    def test_rejects_path_outside_project_storage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "secret.txt"
            outside.write_text("secret", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "file_outside_allowed_folders"):
                collect([str(outside)], root)


if __name__ == "__main__":
    unittest.main()
