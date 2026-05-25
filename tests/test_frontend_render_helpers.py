import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


class FrontendRenderHelperTests(unittest.TestCase):
    def _read(self, filename):
        return (FRONTEND / filename).read_text()

    def test_core_exposes_shared_recipe_card_helpers(self):
        core = self._read("core.js")

        for helper in [
            "recipeImageHtml",
            "cardMetaHtml",
            "selectionCheckHtml",
            "quickPlanButtonHtml",
            "renderRecipeCard",
            "renderEmptyState",
        ]:
            self.assertRegex(core, rf"function\s+{helper}\s*\(")

        self.assertIn('loading="lazy"', core)
        self.assertIn('class="empty-state"', core)

    def test_recipe_grids_use_shared_card_renderer_instead_of_repeated_card_templates(self):
        recipes = self._read("recipes.js")

        for renderer in ["renderRecipes", "renderFavorites", "renderStaged", "renderTrashed"]:
            body = self._function_body(recipes, renderer)
            self.assertIn("renderRecipeCard(", body, f"{renderer} should use the shared renderer")

        self.assertLessEqual(recipes.count('class="recipe-card'), 1)
        self.assertNotIn('class="sel-check"', recipes)

    def test_picker_uses_shared_image_helper_and_lazy_images(self):
        planner = self._read("planner.js")
        body = self._function_body(planner, "renderPickerGrid")

        self.assertIn("recipeImageHtml(", body)
        self.assertNotIn("onerror=", body)
        self.assertNotIn("<img src=", body)

    def _function_body(self, source, name):
        match = re.search(rf"function\s+{name}\s*\([^)]*\)\s*{{", source)
        self.assertIsNotNone(match, f"missing function {name}")
        start = match.end()
        depth = 1
        i = start
        while i < len(source) and depth:
            if source[i] == "{":
                depth += 1
            elif source[i] == "}":
                depth -= 1
            i += 1
        return source[start:i - 1]


if __name__ == "__main__":
    unittest.main()
