"""
modules/url_importer.py — URL → schema.org/Recipe JSON
Fetches a recipe page, extracts JSON-LD Recipe data, saves as staged.
"""
import urllib.error

from modules import imports
from modules.importer import save_recipe_json


def import_from_url(url: str) -> dict:
    """
    Fetch *url*, extract schema.org/Recipe JSON-LD, save as staged.
    Raises ValueError with a user-readable message on failure.
    """
    try:
        html = imports.fetch_text(url, timeout=15, headers={"Accept-Encoding": "gzip, deflate"})
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise ValueError(
                "This site blocks automated access (403 Forbidden). "
                "Try the Import from Image option — take a screenshot of the recipe page instead."
            ) from exc
        raise ValueError(f"Could not fetch URL: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Could not fetch URL: {exc}") from exc

    ld = imports.find_recipe_data(html)
    if not ld:
        raise ValueError(
            "No schema.org/Recipe found at this URL. "
            "The site may not use standard markup — try the Import from Image option instead."
        )

    recipe = imports.normalize_schema_recipe(ld, source_url=url, source_type="url")

    local_path = imports.download_image(recipe.get("image", ""), recipe["slug"], timeout=10)
    local_ref = imports.local_image_ref(local_path)
    if local_ref:
        recipe["image"] = local_ref

    save_recipe_json(recipe, status="staged")
    return recipe
