"""
modules/url_importer.py — URL → schema.org/Recipe JSON
Fetches a recipe page, extracts JSON-LD Recipe data, saves as staged.
Uses only stdlib (urllib, html.parser, gzip) — no extra dependencies.
"""
import gzip
import json
import re
import urllib.request
import urllib.error
from html.parser import HTMLParser
from datetime import date
from pathlib import Path
from modules.importer import save_recipe_json, slugify

IMAGES_DIR = Path(__file__).parent.parent / "images"


class _LdJsonParser(HTMLParser):
    """Extract all <script type="application/ld+json"> blocks from HTML."""

    def __init__(self):
        super().__init__()
        self._in_ld = False
        self.blocks = []
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            attrs_d = {k.lower(): v for k, v in attrs}
            if "ld+json" in attrs_d.get("type", ""):
                self._in_ld = True
                self._buf = []

    def handle_endtag(self, tag):
        if tag == "script" and self._in_ld:
            self.blocks.append("".join(self._buf))
            self._in_ld = False
            self._buf = []

    def handle_data(self, data):
        if self._in_ld:
            self._buf.append(data)


def _scan_for_recipe(data) -> dict | None:
    """Recursively scan a JSON-LD value for a Recipe object."""
    if isinstance(data, list):
        for item in data:
            r = _scan_for_recipe(item)
            if r:
                return r
    elif isinstance(data, dict):
        types = data.get("@type", "")
        if isinstance(types, str):
            types = [types]
        if "Recipe" in types:
            return data
        if "@graph" in data:
            return _scan_for_recipe(data["@graph"])
    return None


def _find_recipe_ld(html: str) -> dict | None:
    """Search JSON-LD blocks for a schema.org Recipe object."""
    parser = _LdJsonParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    for block in parser.blocks:
        try:
            result = _scan_for_recipe(json.loads(block))
            if result:
                return result
        except Exception:
            continue
    return None


def _find_recipe_next_data(html: str) -> dict | None:
    """Fallback: scan __NEXT_DATA__ script tag (Next.js sites)."""
    m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return None
    try:
        return _deep_scan(json.loads(m.group(1)))
    except Exception:
        return None


def _deep_scan(obj, depth=0) -> dict | None:
    if depth > 12:
        return None
    if isinstance(obj, dict):
        types = obj.get("@type", "")
        if isinstance(types, str):
            types = [types]
        if "Recipe" in types and "name" in obj:
            return obj
        for v in obj.values():
            r = _deep_scan(v, depth + 1)
            if r:
                return r
    elif isinstance(obj, list):
        for item in obj:
            r = _deep_scan(item, depth + 1)
            if r:
                return r
    return None


def _normalize(ld: dict, source_url: str) -> dict:
    name = ld.get("name", "Imported Recipe")
    if isinstance(name, list):
        name = name[0] if name else "Imported Recipe"

    raw_steps = ld.get("recipeInstructions", [])
    if isinstance(raw_steps, str):
        raw_steps = [raw_steps]
    steps = []
    for s in raw_steps:
        if isinstance(s, str) and s.strip():
            steps.append({"@type": "HowToStep", "text": s.strip()})
        elif isinstance(s, dict):
            text = s.get("text", s.get("description", "")).strip()
            if text:
                steps.append({"@type": "HowToStep", "text": text})

    image = ld.get("image", "")
    if isinstance(image, list):
        image = image[0] if image else ""
    if isinstance(image, dict):
        image = image.get("url", "")

    author = ld.get("author", {"@type": "Person", "name": "Unknown"})
    if isinstance(author, list):
        author = author[0] if author else {"@type": "Person", "name": "Unknown"}

    recipe_yield = ld.get("recipeYield", "")
    if isinstance(recipe_yield, list):
        recipe_yield = recipe_yield[0] if recipe_yield else ""

    return {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": name,
        "slug": slugify(name),
        "description": ld.get("description", ""),
        "image": image,
        "author": author,
        "datePublished": date.today().isoformat(),
        "prepTime": ld.get("prepTime", ""),
        "cookTime": ld.get("cookTime", ""),
        "totalTime": ld.get("totalTime", ""),
        "recipeYield": recipe_yield,
        "recipeCategory": ld.get("recipeCategory", ""),
        "recipeCuisine": ld.get("recipeCuisine", ""),
        "keywords": ld.get("keywords", ""),
        "recipeIngredient": ld.get("recipeIngredient", []),
        "recipeInstructions": steps,
        "nutrition": ld.get("nutrition", {}),
        "source_url": source_url,
        "source_type": "url",
    }


def import_from_url(url: str) -> dict:
    """
    Fetch *url*, extract schema.org/Recipe JSON-LD, save as staged.
    Raises ValueError with a user-readable message on failure.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            ct = resp.headers.get("Content-Type", "")
            m = re.search(r"charset=([^\s;]+)", ct)
            html = raw.decode(m.group(1) if m else "utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise ValueError(
                "This site blocks automated access (403 Forbidden). "
                "Try the Import from Image option — take a screenshot of the recipe page instead."
            ) from exc
        raise ValueError(f"Could not fetch URL: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Could not fetch URL: {exc}") from exc

    ld = _find_recipe_ld(html) or _find_recipe_next_data(html)
    if not ld:
        raise ValueError(
            "No schema.org/Recipe found at this URL. "
            "The site may not use standard markup — try the Import from Image option instead."
        )

    recipe = _normalize(ld, url)

    # Download image locally (best-effort — never blocks recipe save)
    remote_image = recipe.get("image", "")
    if remote_image and remote_image.startswith("http"):
        local_path = _download_image(remote_image, recipe["slug"])
        if local_path:
            recipe["image"] = f"images/{local_path.name}"

    save_recipe_json(recipe, status="staged")
    return recipe


def _download_image(image_url: str, slug: str) -> Path | None:
    IMAGES_DIR.mkdir(exist_ok=True)
    # Guess extension from URL, default to .jpg
    ext = re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", image_url, re.IGNORECASE)
    suffix = f".{ext.group(1).lower()}" if ext else ".jpg"
    dest = IMAGES_DIR / f"{slug}{suffix}"
    try:
        req = urllib.request.Request(
            image_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Feedme/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            dest.write_bytes(resp.read())
        return dest
    except Exception:
        return None
