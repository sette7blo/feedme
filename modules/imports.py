"""Shared import and recipe normalization helpers.

This module keeps URL, RSS, text, and camera import paths aligned without
splitting common parsing into many tiny files.
"""
from __future__ import annotations

import gzip
import json
import re
import urllib.error
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from modules.importer import slugify

BASE_DIR = Path(__file__).resolve().parent.parent
IMAGES_DIR = BASE_DIR / "images"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class _LdJsonParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._in_ld = False
        self.blocks: list[str] = []
        self._buf: list[str] = []

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


def strip_json_fences(text: str) -> str:
    """Remove optional markdown JSON fences around model output."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def fetch_text(url: str, *, timeout: int = 15, headers: dict[str, str] | None = None) -> str:
    """Fetch URL content and decode text, supporting gzip responses."""
    req_headers = {**BROWSER_HEADERS, **(headers or {})}
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        charset = "utf-8"
        content_type = resp.headers.get("Content-Type", "")
        match = re.search(r"charset=([^\s;]+)", content_type)
        if match:
            charset = match.group(1)
        return raw.decode(charset, errors="replace")


def scan_for_recipe(data: Any, *, max_depth: int = 12, _depth: int = 0) -> dict | None:
    """Recursively scan JSON-LD/Next.js data for a schema.org Recipe object."""
    if _depth > max_depth:
        return None
    if isinstance(data, list):
        for item in data:
            result = scan_for_recipe(item, max_depth=max_depth, _depth=_depth + 1)
            if result:
                return result
    elif isinstance(data, dict):
        types = data.get("@type", "")
        if isinstance(types, str):
            types = [types]
        if "Recipe" in types and (data.get("name") or data.get("recipeIngredient")):
            return data
        if "@graph" in data:
            result = scan_for_recipe(data["@graph"], max_depth=max_depth, _depth=_depth + 1)
            if result:
                return result
        for value in data.values():
            result = scan_for_recipe(value, max_depth=max_depth, _depth=_depth + 1)
            if result:
                return result
    return None


def find_recipe_ld(html: str) -> dict | None:
    """Search application/ld+json blocks for a schema.org Recipe object."""
    parser = _LdJsonParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    for block in parser.blocks:
        try:
            result = scan_for_recipe(json.loads(strip_json_fences(block)))
            if result:
                return result
        except Exception:
            continue
    return None


def find_recipe_next_data(html: str) -> dict | None:
    """Search a Next.js __NEXT_DATA__ script for embedded recipe data."""
    match = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.DOTALL)
    if not match:
        return None
    try:
        return scan_for_recipe(json.loads(match.group(1)))
    except Exception:
        return None


def find_recipe_data(html: str) -> dict | None:
    """Find recipe data in standard JSON-LD or common framework payloads."""
    return find_recipe_ld(html) or find_recipe_next_data(html)


def scalar(value: Any, default: str = "", sep: str = ", ") -> str:
    """Return a stable string from schema values that may be scalar/list/dict."""
    if value is None:
        return default
    if isinstance(value, list):
        cleaned = [scalar(v, "", sep) for v in value]
        cleaned = [v for v in cleaned if v]
        return sep.join(cleaned) if len(cleaned) > 1 else (cleaned[0] if cleaned else default)
    if isinstance(value, dict):
        return str(value.get("name") or value.get("text") or value.get("url") or default)
    return str(value)


def first_scalar(value: Any, default: str = "") -> str:
    """Return only the first meaningful scalar from list-capable schema fields."""
    if isinstance(value, list):
        return first_scalar(value[0], default) if value else default
    return scalar(value, default)


def extract_image_url(image_value: Any) -> str:
    """Pull a URL string out of common schema.org image shapes."""
    if not image_value:
        return ""
    if isinstance(image_value, str):
        return image_value
    if isinstance(image_value, list):
        for item in image_value:
            found = extract_image_url(item)
            if found:
                return found
        return ""
    if isinstance(image_value, dict):
        return scalar(image_value.get("url") or image_value.get("contentUrl"), "")
    return ""


def normalize_author(author: Any) -> dict:
    if isinstance(author, list):
        author = author[0] if author else {}
    if isinstance(author, dict):
        return {"@type": author.get("@type", "Person"), "name": scalar(author.get("name"), "")}
    return {"@type": "Person", "name": scalar(author, "")}


def normalize_ingredients(ingredients: Any) -> list[str]:
    if isinstance(ingredients, str):
        ingredients = [ingredients]
    if not isinstance(ingredients, list):
        return []
    return [scalar(item).strip() for item in ingredients if scalar(item).strip()]


def normalize_instructions(raw_steps: Any) -> list[dict]:
    """Normalize strings, HowToStep, and nested HowToSection objects to steps."""
    steps: list[dict] = []

    def add_text(text: Any, name: str = "") -> None:
        text = scalar(text).strip()
        if not text:
            return
        step = {"@type": "HowToStep", "text": text}
        if name:
            step["name"] = name
        steps.append(step)

    def walk(value: Any) -> None:
        if not value:
            return
        if isinstance(value, str):
            add_text(value)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            nested = value.get("itemListElement") or value.get("steps")
            if nested:
                walk(nested)
                return
            add_text(value.get("text") or value.get("description"), scalar(value.get("name"), ""))

    walk(raw_steps)
    return steps


def normalize_schema_recipe(ld: dict, *, source_url: str = "", source_type: str = "url", rss_item: dict | None = None) -> dict:
    """Normalize schema.org Recipe data into Feedme's canonical JSON shape."""
    rss_item = rss_item or {}
    name = first_scalar(ld.get("name"), rss_item.get("title") or "Imported Recipe").strip()
    image = extract_image_url(ld.get("image")) or scalar(rss_item.get("image"), "")
    source = source_url or rss_item.get("link") or scalar(ld.get("url"), "")
    return {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": name,
        "slug": slugify(name),
        "description": scalar(ld.get("description"), rss_item.get("description", "")),
        "image": image,
        "author": normalize_author(ld.get("author", {})),
        "datePublished": first_scalar(ld.get("datePublished"), date.today().isoformat()),
        "prepTime": first_scalar(ld.get("prepTime")),
        "cookTime": first_scalar(ld.get("cookTime")),
        "totalTime": first_scalar(ld.get("totalTime")),
        "recipeYield": first_scalar(ld.get("recipeYield")),
        "recipeCategory": first_scalar(ld.get("recipeCategory")),
        "recipeCuisine": first_scalar(ld.get("recipeCuisine")),
        "keywords": scalar(ld.get("keywords")),
        "recipeIngredient": normalize_ingredients(ld.get("recipeIngredient", [])),
        "recipeInstructions": normalize_instructions(ld.get("recipeInstructions", [])),
        "nutrition": ld.get("nutrition") or {},
        "source_url": source,
        "source_type": source_type,
    }


def download_image(image_url: str, slug: str, *, timeout: int = 15, images_dir: Path | None = None) -> Path | None:
    """Download an external recipe image to images/<slug>.<ext>; best-effort."""
    if not image_url or not image_url.startswith("http"):
        return None
    images_dir = images_dir or IMAGES_DIR
    images_dir.mkdir(parents=True, exist_ok=True)
    match = re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", image_url, re.IGNORECASE)
    suffix = f".{match.group(1).lower()}" if match else ".jpg"
    if suffix == ".jpeg":
        suffix = ".jpg"
    dest = images_dir / f"{slug}{suffix}"
    try:
        req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0 (compatible; Feedme/1.0)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            dest.write_bytes(resp.read())
        return dest
    except Exception:
        return None


def local_image_ref(path: Path | None) -> str | None:
    return f"images/{path.name}" if path else None
