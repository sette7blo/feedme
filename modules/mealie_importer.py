"""
modules/mealie_importer.py — Import recipes from a Mealie instance
Fetches recipe list and full recipe details via the Mealie REST API.
Converts Mealie format → schema.org/Recipe JSON, saves as staged.
"""
import json
import re
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path

from modules.importer import save_recipe_json, slugify, RECIPES_DIR
from core.db import db

IMAGES_DIR = Path(__file__).parent.parent / "images"
PAGE_SIZE = 50


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def _get(base_url: str, token: str, path: str) -> dict:
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(url, headers=_headers(token))
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise ValueError("Invalid Mealie token — check your API key in Settings.") from exc
        if exc.code == 404:
            raise ValueError(f"Mealie endpoint not found: {url} — check your Mealie URL in Settings (no trailing slash needed).") from exc
        raise ValueError(f"Mealie returned HTTP {exc.code} for {url}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Could not reach Mealie at {base_url}: {exc.reason}") from exc


def browse(base_url: str, token: str, page: int = 1) -> dict:
    """
    Return a page of recipes from Mealie with already-imported flags.
    Response: { items: [...], total, page, per_page, pages }
    Each item: { slug, name, image, description, total_time, recipe_yield, already_imported }
    """
    data = _get(base_url, token, f"/api/recipes?page={page}&perPage={PAGE_SIZE}")

    items = data.get("items", data.get("data", []))
    total = data.get("total", len(items))
    pages = data.get("total_pages", data.get("pages", max(1, -(-total // PAGE_SIZE))))

    # Build feedme slugs for each item (same logic as import_recipes)
    # and check which are already active/staged in Feedme (ignore trashed)
    feedme_slugs = [slugify(r.get("name", r.get("slug", ""))) for r in items]
    existing = set()
    if feedme_slugs:
        with db() as conn:
            placeholders = ",".join("?" * len(feedme_slugs))
            rows = conn.execute(
                f"SELECT slug FROM recipes WHERE slug IN ({placeholders}) AND status != 'trashed'",
                feedme_slugs
            ).fetchall()
            existing = {r["slug"] for r in rows}

    result = []
    for r, feedme_slug in zip(items, feedme_slugs):
        slug = r.get("slug", "")
        # Image path uses UUID, not slug; proxy through Feedme so browser gets auth
        recipe_id = r.get("id", "")
        image = f"/api/import/mealie/image/{recipe_id}" if recipe_id else ""
        result.append({
            "slug":             slug,
            "name":             r.get("name", ""),
            "description":      r.get("description", "") or "",
            "image":            image,
            "total_time":       r.get("totalTime") or "",
            "recipe_yield":     r.get("recipeYield") or "",
            "recipe_category":  r.get("recipeCategory") or "",
            "already_imported": feedme_slug in existing,
        })

    return {
        "items":    result,
        "total":    total,
        "page":     page,
        "per_page": PAGE_SIZE,
        "pages":    pages,
    }


def _parse_duration(val) -> str:
    """PT45M → '45 min', PT1H30M → '1h 30min'"""
    if not val:
        return ""
    val = str(val)
    if val.startswith("PT"):
        val = val[2:]
    return val.replace("H", "h ").replace("M", "min").strip()


def _normalize_steps(raw) -> list:
    if not raw:
        return []
    if isinstance(raw, str):
        return [{"@type": "HowToStep", "text": raw.strip()}]
    steps = []
    for s in raw:
        if isinstance(s, str) and s.strip():
            steps.append({"@type": "HowToStep", "text": s.strip()})
        elif isinstance(s, dict):
            text = s.get("text", s.get("description", "")).strip()
            if text:
                steps.append({"@type": "HowToStep", "text": text})
    return steps


def _download_image(image_url: str, slug: str, token: str) -> str | None:
    """Download Mealie image (needs auth). Returns relative path or None."""
    IMAGES_DIR.mkdir(exist_ok=True)
    dest = IMAGES_DIR / f"{slug}.webp"
    try:
        req = urllib.request.Request(
            image_url,
            headers={"Authorization": f"Bearer {token}", "Accept": "image/*"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            dest.write_bytes(resp.read())
        return f"images/{slug}.webp"
    except Exception:
        return None


def import_recipes(base_url: str, token: str, slugs: list[str]) -> dict:
    """
    Fetch full recipe details for each slug from Mealie and save as staged.
    Returns { imported: [...], skipped: [...], errors: [...] }
    """
    imported, skipped, errors = [], [], []

    for slug in slugs:
        try:
            data = _get(base_url, token, f"/api/recipes/{slug}")
        except ValueError as exc:
            errors.append({"slug": slug, "error": str(exc)})
            continue

        name = data.get("name", slug)
        feedme_slug = slugify(name)

        ingredients = []
        for ing in (data.get("recipeIngredient") or []):
            if isinstance(ing, str):
                ingredients.append(ing)
            elif isinstance(ing, dict):
                parts = []
                qty = ing.get("quantity")
                if qty:  # skip 0 and None — 0 means amount is in note
                    parts.append(str(int(qty)) if float(qty) == int(qty) else str(qty))
                unit = (ing.get("unit") or {})
                if isinstance(unit, dict):
                    unit = unit.get("name", "")
                if unit:
                    parts.append(unit)
                food = (ing.get("food") or {})
                if isinstance(food, dict):
                    food = food.get("name", "")
                if food:
                    parts.append(food)
                note = (ing.get("note") or "").strip()
                if note:
                    # If note is the only content, use it as-is (no parens)
                    if not parts:
                        parts.append(note)
                    else:
                        parts.append(f"({note})")
                if parts:
                    ingredients.append(" ".join(parts))

        recipe_yield = data.get("recipeYield", "")
        if isinstance(recipe_yield, list):
            recipe_yield = recipe_yield[0] if recipe_yield else ""

        category = data.get("recipeCategory", "")
        if isinstance(category, list):
            category = ", ".join(c.get("name", c) if isinstance(c, dict) else c for c in category)

        cuisine = data.get("recipeCuisine", "")
        if isinstance(cuisine, list):
            cuisine = ", ".join(cuisine)

        keywords = data.get("tags", [])
        if isinstance(keywords, list):
            keywords = ", ".join(t.get("name", t) if isinstance(t, dict) else t for t in keywords)

        recipe = {
            "@context": "https://schema.org",
            "@type": "Recipe",
            "name": name,
            "slug": feedme_slug,
            "description": data.get("description", "") or "",
            "prepTime": _parse_duration(data.get("prepTime")),
            "cookTime": _parse_duration(data.get("cookTime")),
            "totalTime": _parse_duration(data.get("totalTime")),
            "recipeYield": str(recipe_yield) if recipe_yield else "",
            "recipeCategory": category,
            "recipeCuisine": cuisine,
            "keywords": keywords,
            "recipeIngredient": ingredients,
            "recipeInstructions": _normalize_steps(data.get("recipeInstructions")),
            "nutrition": data.get("nutrition") or {},
            "source_url": f"{base_url.rstrip('/')}/recipe/{slug}",
            "source_type": "mealie",
            "mealie_id": data.get("id", ""),
            "datePublished": date.today().isoformat(),
        }

        # Download image (auth required)
        recipe_id = data.get("id", slug)
        mealie_image_url = f"{base_url.rstrip('/')}/api/media/recipes/{recipe_id}/images/original.webp"
        local_image = _download_image(mealie_image_url, feedme_slug, token)
        if local_image:
            recipe["image"] = local_image

        path = save_recipe_json(recipe, status="staged")
        if path is None:
            skipped.append(name)
        else:
            imported.append(name)

    return {"imported": imported, "skipped": skipped, "errors": errors}
