"""
modules/nostr_importer.py — Import recipes from Nostr relays
Parses kind:30078 events tagged with both 'feedme' and 'recipe'.
Converts event content (schema.org Recipe JSON) → staged recipes.
"""
import json
import urllib.request
from datetime import date
from pathlib import Path

from modules.importer import save_recipe_json, slugify

IMAGES_DIR = Path(__file__).parent.parent / "images"


def _download_image(url: str, slug: str) -> str | None:
    """Download image from a public URL. Returns relative path or None."""
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return None
    IMAGES_DIR.mkdir(exist_ok=True)
    ext = url.split("?")[0].rsplit(".", 1)[-1].lower()
    if ext not in {"jpg", "jpeg", "png", "webp", "gif"}:
        ext = "jpg"
    dest = IMAGES_DIR / f"{slug}.{ext}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Feedme/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            dest.write_bytes(resp.read())
        return f"images/{slug}.{ext}"
    except Exception:
        return None

NOSTR_KIND = 30078
REQUIRED_TAGS = {"feedme", "recipe"}


def _extract_tags(tags: list) -> set:
    """Return the set of 't' tag values from a Nostr event tags array."""
    return {v for tag in tags if len(tag) >= 2 and tag[0] == "t" for v in [tag[1]]}


def _get_tag(tags: list, key: str) -> str | None:
    """Return first value of a specific tag key."""
    for tag in tags:
        if len(tag) >= 2 and tag[0] == key:
            return tag[1]
    return None


def is_recipe_event(event: dict) -> bool:
    """Return True if event is a valid Feedme recipe event."""
    if event.get("kind") != NOSTR_KIND:
        return False
    tag_values = _extract_tags(event.get("tags", []))
    return REQUIRED_TAGS.issubset(tag_values)


def parse_event(event: dict) -> dict | None:
    """
    Parse a Nostr event into a Feedme recipe dict.
    Returns None if content is not valid recipe JSON.
    """
    try:
        content = json.loads(event.get("content", ""))
    except (json.JSONDecodeError, TypeError):
        return None

    name = content.get("name")
    if not name:
        return None

    slug = content.get("slug") or slugify(name)

    recipe = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": name,
        "slug": slug,
        "description": content.get("description", "") or "",
        "prepTime": content.get("prepTime", ""),
        "cookTime": content.get("cookTime", ""),
        "totalTime": content.get("totalTime", ""),
        "recipeYield": content.get("recipeYield", ""),
        "recipeCategory": content.get("recipeCategory", ""),
        "recipeCuisine": content.get("recipeCuisine", ""),
        "keywords": content.get("keywords", ""),
        "recipeIngredient": content.get("recipeIngredient", []),
        "recipeInstructions": content.get("recipeInstructions", []),
        "nutrition": content.get("nutrition") or {},
        "image": content.get("image", ""),
        "source_url": content.get("source_url", ""),
        "source_type": content.get("source_type", "manual"),
        "nostr_event_id": event.get("id", ""),
        "nostr_pubkey": event.get("pubkey", ""),
        "datePublished": date.today().isoformat(),
    }

    return recipe


def import_events(events: list[dict]) -> dict:
    """
    Parse and save a list of Nostr events as staged recipes.
    Returns { imported: [...], skipped: [...], errors: [...] }
    """
    imported, skipped, errors = [], [], []

    for event in events:
        if not is_recipe_event(event):
            errors.append({"id": event.get("id", "?"), "error": "Not a valid Feedme recipe event"})
            continue

        recipe = parse_event(event)
        if not recipe:
            errors.append({"id": event.get("id", "?"), "error": "Could not parse recipe content"})
            continue

        # Download image locally if a public URL is present
        remote_image = recipe.get("image", "")
        local_image = _download_image(remote_image, recipe["slug"])
        if local_image:
            recipe["image"] = local_image

        path = save_recipe_json(recipe, status="staged")
        if path is None:
            skipped.append(recipe["name"])
        else:
            imported.append(recipe["name"])

    return {"imported": imported, "skipped": skipped, "errors": errors}
