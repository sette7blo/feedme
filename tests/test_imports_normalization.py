import json
import unittest

from modules import imports


class ImportNormalizationTests(unittest.TestCase):
    def test_strip_json_fences_accepts_markdown_wrapped_json(self):
        wrapped = "```json\n{\"name\": \"Soup\"}\n```"
        self.assertEqual(imports.strip_json_fences(wrapped), '{"name": "Soup"}')

    def test_find_recipe_data_finds_recipe_in_ld_json_graph_and_next_data(self):
        ld_html = """
        <html><script type="application/ld+json">
        {"@graph":[{"@type":"WebPage"},{"@type":["Recipe","Article"],"name":"Pasta"}]}
        </script></html>
        """
        self.assertEqual(imports.find_recipe_data(ld_html)["name"], "Pasta")

        next_html = """
        <script id="__NEXT_DATA__" type="application/json">
        {"props":{"pageProps":{"recipe":{"@type":"Recipe","name":"Cake"}}}}
        </script>
        """
        self.assertEqual(imports.find_recipe_data(next_html)["name"], "Cake")

    def test_normalize_schema_recipe_matches_url_and_rss_shape(self):
        ld = {
            "@type": "Recipe",
            "name": ["Pasta"],
            "description": ["Fast dinner"],
            "image": [{"url": "https://example.test/pasta.webp"}],
            "author": [{"@type": "Person", "name": "Ada"}],
            "recipeYield": ["4 servings"],
            "recipeCategory": ["Dinner"],
            "recipeCuisine": ["Italian"],
            "keywords": ["quick", "pasta"],
            "recipeIngredient": ["200g pasta", "1 cup sauce", ""],
            "recipeInstructions": [
                {"@type": "HowToSection", "itemListElement": [
                    {"@type": "HowToStep", "text": "Boil pasta."},
                    "Toss with sauce.",
                ]}
            ],
            "nutrition": {"calories": "400"},
        }
        rss_item = {"title": "Fallback", "link": "https://example.test/rss", "description": "rss desc"}
        url_recipe = imports.normalize_schema_recipe(ld, source_url="https://example.test/url", source_type="url")
        rss_recipe = imports.normalize_schema_recipe(ld, rss_item=rss_item, source_type="rss")

        for recipe in (url_recipe, rss_recipe):
            self.assertEqual(recipe["name"], "Pasta")
            self.assertEqual(recipe["slug"], "pasta")
            self.assertEqual(recipe["image"], "https://example.test/pasta.webp")
            self.assertEqual(recipe["author"], {"@type": "Person", "name": "Ada"})
            self.assertEqual(recipe["recipeIngredient"], ["200g pasta", "1 cup sauce"])
            self.assertEqual(
                [step["text"] for step in recipe["recipeInstructions"]],
                ["Boil pasta.", "Toss with sauce."],
            )
            self.assertEqual(recipe["recipeYield"], "4 servings")
            self.assertEqual(recipe["recipeCategory"], "Dinner")
            self.assertEqual(recipe["recipeCuisine"], "Italian")
            self.assertEqual(recipe["keywords"], "quick, pasta")
            self.assertEqual(recipe["nutrition"], {"calories": "400"})

        self.assertEqual(url_recipe["source_url"], "https://example.test/url")
        self.assertEqual(url_recipe["source_type"], "url")
        self.assertEqual(rss_recipe["source_url"], "https://example.test/rss")
        self.assertEqual(rss_recipe["source_type"], "rss")


if __name__ == "__main__":
    unittest.main()
