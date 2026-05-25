import json
import tempfile
import unittest
from pathlib import Path

import core.db as dbmod
import core.schema as schema
from core.db import db
from modules import importer, meal_planner


class BatchEndpointHelperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.old_db_path = dbmod.DB_PATH
        self.old_recipes_dir = importer.RECIPES_DIR
        dbmod.DB_PATH = self.base / "chef.db"
        importer.RECIPES_DIR = self.base / "recipes"
        schema.init_db()
        self._save_recipe("alpha", "Alpha", "staged")
        self._save_recipe("beta", "Beta", "active")
        self._save_recipe("gamma", "Gamma", "active")

    def tearDown(self):
        dbmod.DB_PATH = self.old_db_path
        importer.RECIPES_DIR = self.old_recipes_dir
        self.tmp.cleanup()

    def _save_recipe(self, slug, name, status):
        importer.save_recipe_json({
            "@context": "https://schema.org",
            "@type": "Recipe",
            "name": name,
            "slug": slug,
            "recipeYield": "2 servings",
            "recipeIngredient": ["1 cup rice"],
            "recipeInstructions": [{"@type": "HowToStep", "text": "Cook."}],
            "status": status,
        }, status=status)

    def test_batch_recipe_action_returns_per_item_results(self):
        result = importer.batch_recipe_action("favorite", ["beta", "missing"])

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["ok"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["results"][0], {"slug": "beta", "ok": True, "favorited": True})
        self.assertEqual(result["results"][1]["slug"], "missing")
        self.assertFalse(result["results"][1]["ok"])

        with db() as conn:
            row = conn.execute("SELECT favorited FROM recipes WHERE slug='beta'").fetchone()
        self.assertEqual(row["favorited"], 1)

    def test_batch_recipe_action_approve_and_trash_updates_statuses(self):
        approved = importer.batch_recipe_action("approve", ["alpha"])
        trashed = importer.batch_recipe_action("trash", ["beta"])

        self.assertEqual(approved["ok"], 1)
        self.assertEqual(trashed["ok"], 1)
        with db() as conn:
            statuses = dict(conn.execute("SELECT slug, status FROM recipes").fetchall())
        self.assertEqual(statuses["alpha"], "active")
        self.assertEqual(statuses["beta"], "trashed")

        alpha_json = json.loads((importer.RECIPES_DIR / "alpha.json").read_text())
        beta_json = json.loads((importer.RECIPES_DIR / "beta.json").read_text())
        self.assertEqual(alpha_json["status"], "active")
        self.assertEqual(beta_json["status"], "trashed")

    def test_add_slots_batch_returns_success_and_failure_counts(self):
        result = meal_planner.add_slots_batch([
            {"date": "2026-05-25", "meal_type": "dinner", "recipe_slug": "beta"},
            {"date": "2026-05-26", "meal_type": "dinner", "recipe_slug": "missing"},
        ])

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["ok"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertTrue(result["results"][0]["ok"])
        self.assertEqual(result["results"][0]["entry"]["recipe_slug"], "beta")
        self.assertFalse(result["results"][1]["ok"])


if __name__ == "__main__":
    unittest.main()
