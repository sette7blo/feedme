import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from modules import ai_features, maintenance


class Phase4ModuleTests(unittest.TestCase):
    def test_create_backup_includes_recipes_images_and_non_secret_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "recipes").mkdir()
            (base / "images").mkdir()
            (base / "recipes" / "soup.json").write_text('{"name":"Soup"}')
            (base / "images" / "soup.jpg").write_bytes(b"jpg")
            (base / ".env").write_text("PPQ_MODEL=model\nFLASK_SECRET=secret\n")

            backup_bytes, filename = maintenance.create_backup(base)

            self.assertTrue(filename.startswith("feedme-backup-"))
            with zipfile.ZipFile(io.BytesIO(backup_bytes)) as zf:
                self.assertIn("recipes/soup.json", zf.namelist())
                self.assertIn("images/soup.jpg", zf.namelist())
                settings = json.loads(zf.read("settings.json"))
            self.assertEqual(settings, {"PPQ_MODEL": "model"})

    def test_parse_servings_uses_first_number_or_one(self):
        self.assertEqual(ai_features.parse_servings("Serves 4-6"), 4)
        self.assertEqual(ai_features.parse_servings("about two"), 1)
        self.assertEqual(ai_features.parse_servings(None), 1)

    def test_extract_json_object_accepts_markdown_wrapped_json(self):
        text = "```json\n{\"calories\": 410}\n```"
        self.assertEqual(ai_features.extract_json_object(text), {"calories": 410})


if __name__ == "__main__":
    unittest.main()
