"""
modules/rss_fetcher.py — Fetch RSS feeds + scrape recipe pages for full JSON-LD data.
Approach borrowed from mealie-scraper: RSS gives links, page scraping gives recipes.
"""
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from modules.importer import save_recipe_json, slugify

IMAGES_DIR = Path(__file__).parent.parent / "images"

RSS_NS = {
    'media':   'http://search.yahoo.com/mrss/',
    'atom':    'http://www.w3.org/2005/Atom',
    'content': 'http://purl.org/rss/1.0/modules/content/',
    'dc':      'http://purl.org/dc/elements/1.1/',
}

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

MAX_ITEMS   = 10   # items to process per feed
PAGE_DELAY  = 1.0  # seconds between page scrapes
PAGE_TIMEOUT = 20  # seconds per page fetch


def _fetch(url, timeout=30):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ── RSS parsing ───────────────────────────────────────────────────────────────

def fetch_feed(url: str) -> list[dict]:
    """Fetch RSS/Atom feed and return list of candidate items (title, link, image, description)."""
    try:
        content = _fetch(url)
    except Exception as e:
        raise RuntimeError(f"Failed to fetch feed: {e}")

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        raise RuntimeError(f"Invalid XML in feed: {e}")

    # RSS 2.0 items or Atom entries
    items = root.findall('.//item')
    if not items:
        items = root.findall('.//atom:entry', RSS_NS)

    candidates = []
    for item in items[:MAX_ITEMS]:

        # ── title ────────────────────────────────────────────────────────────
        # NOTE: use `is None` checks — ET elements are falsy even when they have text
        title_el = item.find('title')
        if title_el is None:
            title_el = item.find('atom:title', RSS_NS)
        title = (title_el.text or '').strip() if title_el is not None else ''
        if not title:
            continue

        # ── link ─────────────────────────────────────────────────────────────
        link = ''
        link_el = item.find('link')
        if link_el is not None:
            link = (link_el.text or link_el.get('href') or '').strip()
        if not link:
            al = item.find('atom:link', RSS_NS)
            if al is not None:
                link = al.get('href', '').strip()
        if not link:
            guid = item.find('guid')
            if guid is not None:
                link = (guid.text or '').strip()

        # ── description ──────────────────────────────────────────────────────
        desc_el = item.find('description')
        if desc_el is None:
            desc_el = item.find('atom:summary', RSS_NS)
        if desc_el is None:
            desc_el = item.find('atom:content', RSS_NS)
        raw_desc = (desc_el.text or '') if desc_el is not None else ''
        description = re.sub(r'<[^>]+>', '', raw_desc).strip()[:500]

        # ── image (multiple fallback strategies) ─────────────────────────────
        image_url = None

        # 1. media:content
        mc = item.find('media:content', RSS_NS)
        if mc is not None:
            image_url = mc.get('url')

        # 2. media:thumbnail
        if not image_url:
            mt = item.find('media:thumbnail', RSS_NS)
            if mt is not None:
                image_url = mt.get('url')

        # 3. enclosure
        if not image_url:
            enc = item.find('enclosure')
            if enc is not None:
                enc_url = enc.get('url', '')
                enc_type = enc.get('type', '')
                if enc_url and ('image' in enc_type or enc_url.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))):
                    image_url = enc_url

        # 4. <img> tag in raw description HTML
        if not image_url and raw_desc:
            imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', raw_desc)
            if imgs:
                image_url = imgs[0]

        candidates.append({
            'title':       title,
            'link':        link,
            'description': description,
            'image':       image_url,
        })

    return candidates


# ── Page scraping ─────────────────────────────────────────────────────────────

def scrape_recipe_page(url: str) -> dict | None:
    """
    Fetch a recipe page and extract the first JSON-LD Recipe schema block.
    If ingredients or instructions are missing from the JSON-LD, falls back
    to HTML parsing (handles JS-lazy-loaded or plugin-inconsistent pages).
    Returns raw schema.org dict or None if not found.
    """
    if not url or not url.startswith('http'):
        return None
    try:
        html = _fetch(url, timeout=PAGE_TIMEOUT).decode('utf-8', errors='replace')
    except Exception:
        return None

    pattern = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>'
    recipe = None
    for raw in re.findall(pattern, html):
        try:
            data = json.loads(raw.strip())
        except (json.JSONDecodeError, ValueError):
            continue

        # Unwrap list, @graph, or plain dict
        if isinstance(data, list):
            recipe = next((d for d in data if isinstance(d, dict) and d.get('@type') == 'Recipe'), None)
        elif isinstance(data, dict):
            if data.get('@type') == 'Recipe':
                recipe = data
            elif isinstance(data.get('@graph'), list):
                recipe = next((d for d in data['@graph'] if isinstance(d, dict) and d.get('@type') == 'Recipe'), None)

        if recipe:
            break

    if recipe is None:
        return None

    # Fill missing ingredients / instructions from HTML when JSON-LD is incomplete
    needs_ing  = not recipe.get('recipeIngredient')
    needs_inst = not recipe.get('recipeInstructions')
    if needs_ing or needs_inst:
        fallback = _html_fallback(html)
        if needs_ing and fallback.get('recipeIngredient'):
            recipe['recipeIngredient'] = fallback['recipeIngredient']
        if needs_inst and fallback.get('recipeInstructions'):
            recipe['recipeInstructions'] = fallback['recipeInstructions']

    return recipe


def _html_fallback(html: str) -> dict:
    """
    Extract ingredients and instructions from raw HTML using common WordPress
    recipe plugin patterns (WPRM, Tasty Recipes, generic heading-based).
    Only returns keys that were actually found — never overwrites good data.
    """
    result = {}

    # Remove script/style blocks to reduce false matches
    clean = re.sub(r'<(script|style)[^>]*>[\s\S]*?</\1>', '', html, flags=re.IGNORECASE)

    def strip_tags(s: str) -> str:
        return re.sub(r'<[^>]+>', '', s).strip()

    # ── WP Recipe Maker (WPRM) ────────────────────────────────────────────────
    wprm_ing_blocks = re.findall(
        r'<li[^>]*class="[^"]*wprm-recipe-ingredient[^"]*"[^>]*>([\s\S]*?)</li>',
        clean, re.IGNORECASE
    )
    if wprm_ing_blocks:
        ingredients = []
        for block in wprm_ing_blocks:
            amount = unit = name = ''
            m = re.search(r'wprm-recipe-ingredient-amount[^"]*"[^>]*>([\s\S]*?)</span>', block, re.IGNORECASE)
            if m: amount = strip_tags(m.group(1))
            m = re.search(r'wprm-recipe-ingredient-unit[^"]*"[^>]*>([\s\S]*?)</span>', block, re.IGNORECASE)
            if m: unit = strip_tags(m.group(1))
            m = re.search(r'wprm-recipe-ingredient-name[^"]*"[^>]*>([\s\S]*?)</span>', block, re.IGNORECASE)
            if m: name = strip_tags(m.group(1))
            text = ' '.join(filter(None, [amount, unit, name]))
            if text:
                ingredients.append(text)
        if ingredients:
            result['recipeIngredient'] = ingredients

    wprm_inst_blocks = re.findall(
        r'wprm-recipe-instruction-text[^"]*"[^>]*>([\s\S]*?)</(?:div|p)>',
        clean, re.IGNORECASE
    )
    if wprm_inst_blocks:
        steps = [strip_tags(s) for s in wprm_inst_blocks if strip_tags(s)]
        if steps:
            result['recipeInstructions'] = [{'@type': 'HowToStep', 'text': s} for s in steps]

    if result.get('recipeIngredient') and result.get('recipeInstructions'):
        return result

    # ── Tasty Recipes ─────────────────────────────────────────────────────────
    if 'recipeIngredient' not in result:
        m = re.search(
            r'class="[^"]*tasty-recipes-ingredients[^"]*"[^>]*>([\s\S]*?)</(?:div|section)>',
            clean, re.IGNORECASE
        )
        if m:
            items = re.findall(r'<li[^>]*>([\s\S]*?)</li>', m.group(1), re.IGNORECASE)
            ingredients = [strip_tags(i) for i in items if strip_tags(i)]
            if ingredients:
                result['recipeIngredient'] = ingredients

    if 'recipeInstructions' not in result:
        m = re.search(
            r'class="[^"]*tasty-recipes-instructions[^"]*"[^>]*>([\s\S]*?)</(?:div|section)>',
            clean, re.IGNORECASE
        )
        if m:
            items = re.findall(r'<li[^>]*>([\s\S]*?)</li>', m.group(1), re.IGNORECASE)
            steps = [strip_tags(i) for i in items if strip_tags(i)]
            if steps:
                result['recipeInstructions'] = [{'@type': 'HowToStep', 'text': s} for s in steps]

    if result.get('recipeIngredient') and result.get('recipeInstructions'):
        return result

    # ── Generic heading-based ─────────────────────────────────────────────────
    if 'recipeIngredient' not in result:
        m = re.search(
            r'>(?:ingredients)<[^>]*</h[2-4]>([\s\S]*?)<(?:h[2-4]|/section)',
            clean, re.IGNORECASE
        )
        if m:
            items = re.findall(r'<li[^>]*>([\s\S]*?)</li>', m.group(1), re.IGNORECASE)
            ingredients = [strip_tags(i) for i in items if strip_tags(i)]
            if ingredients:
                result['recipeIngredient'] = ingredients

    if 'recipeInstructions' not in result:
        m = re.search(
            r'>(?:instructions|directions|method)<[^>]*</h[2-4]>([\s\S]*?)<(?:h[2-4]|/section)',
            clean, re.IGNORECASE
        )
        if m:
            items = re.findall(r'<li[^>]*>([\s\S]*?)</li>', m.group(1), re.IGNORECASE)
            steps = [strip_tags(i) for i in items if strip_tags(i)]
            if steps:
                result['recipeInstructions'] = [{'@type': 'HowToStep', 'text': s} for s in steps]

    return result


# ── Normalisation ─────────────────────────────────────────────────────────────

def _extract_image(ld_image):
    """Pull a URL string out of the various JSON-LD image formats."""
    if not ld_image:
        return None
    if isinstance(ld_image, str):
        return ld_image
    if isinstance(ld_image, list) and ld_image:
        first = ld_image[0]
        return first.get('url') if isinstance(first, dict) else first
    if isinstance(ld_image, dict):
        return ld_image.get('url')
    return None


def _str(val, sep=', ') -> str:
    """Safely coerce a value that might be a list or None to a string."""
    if val is None:
        return ''
    if isinstance(val, list):
        return sep.join(str(v) for v in val if v)
    return str(val)


def normalize_recipe(ld: dict, rss_item: dict) -> dict:
    """Merge JSON-LD data with RSS fallbacks into Feedme's schema.org/Recipe format."""

    # Ingredients
    ingredients = ld.get('recipeIngredient') or []
    if isinstance(ingredients, list):
        ingredients = [i for i in ingredients if isinstance(i, str) and i.strip()]

    # Instructions — handle HowToStep, HowToSection (nested), and plain strings
    instructions = []

    def _extract_steps(steps):
        """Recursively extract HowToStep text from steps or HowToSection itemListElement."""
        if not steps:
            return
        if isinstance(steps, str):
            if steps.strip():
                instructions.append({'@type': 'HowToStep', 'text': steps.strip()})
            return
        if isinstance(steps, dict):
            steps = [steps]
        for step in steps:
            if isinstance(step, str):
                if step.strip():
                    instructions.append({'@type': 'HowToStep', 'text': step.strip()})
            elif isinstance(step, dict):
                step_type = step.get('@type', '')
                if step_type == 'HowToSection' or 'itemListElement' in step:
                    # Section: recurse into its nested steps
                    _extract_steps(step.get('itemListElement', []))
                else:
                    # Regular HowToStep
                    text = step.get('text') or ''
                    if text.strip():
                        instructions.append({'@type': 'HowToStep', 'text': text.strip(),
                                             'name': step.get('name', '')})

    _extract_steps(ld.get('recipeInstructions') or [])

    # Image: prefer JSON-LD, fall back to RSS feed image
    image_url = _extract_image(ld.get('image')) or rss_item.get('image')

    # Author
    author = ld.get('author', {})
    author_name = author.get('name', '') if isinstance(author, dict) else str(author)

    name = (_str(ld.get('name')) or rss_item['title']).strip()

    return {
        '@context':           'https://schema.org',
        '@type':              'Recipe',
        'name':               name,
        'slug':               slugify(name),
        'description':        _str(ld.get('description')) or rss_item.get('description', ''),
        'image':              image_url,
        'author':             {'@type': 'Person', 'name': author_name},
        'datePublished':      _str(ld.get('datePublished')) or date.today().isoformat(),
        'prepTime':           _str(ld.get('prepTime')),
        'cookTime':           _str(ld.get('cookTime')),
        'totalTime':          _str(ld.get('totalTime')),
        'recipeYield':        _str(ld.get('recipeYield')),
        'recipeCategory':     _str(ld.get('recipeCategory')),
        'recipeCuisine':      _str(ld.get('recipeCuisine')),
        'keywords':           _str(ld.get('keywords')),
        'recipeIngredient':   ingredients,
        'recipeInstructions': instructions,
        'nutrition':          ld.get('nutrition') or {},
        'source_url':         rss_item.get('link', '') or _str(ld.get('url')),
        'source_type':        'rss',
    }


def _stub_recipe(rss_item: dict) -> dict:
    """Minimal recipe from RSS item only (when page scraping fails)."""
    name = rss_item['title']
    return {
        '@context':          'https://schema.org',
        '@type':             'Recipe',
        'name':              name,
        'slug':              slugify(name),
        'description':       rss_item.get('description', ''),
        'image':             rss_item.get('image'),
        'datePublished':     date.today().isoformat(),
        'recipeIngredient':  [],
        'recipeInstructions': [],
        'source_url':        rss_item.get('link', ''),
        'source_type':       'rss',
    }


# ── Image download ────────────────────────────────────────────────────────────

def download_image(image_url: str, slug: str) -> str | None:
    """
    Download image from URL, save to images/<slug>.<ext>.
    Returns local path string like 'images/slug.jpg', or None on failure.
    """
    if not image_url or not image_url.startswith('http'):
        return None
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # Determine extension
    ext = 'jpg'
    url_path = image_url.split('?')[0].lower()
    for candidate in ('webp', 'png', 'jpeg', 'jpg'):
        if url_path.endswith(f'.{candidate}'):
            ext = 'jpg' if candidate == 'jpeg' else candidate
            break

    local_path = IMAGES_DIR / f"{slug}.{ext}"
    try:
        req = urllib.request.Request(image_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            local_path.write_bytes(resp.read())
        return f"images/{slug}.{ext}"
    except Exception:
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def _is_complete(recipe: dict) -> bool:
    """
    Return True only if the recipe has ingredients, instructions, image,
    and enough instruction content to be useful (not just section headers).
    """
    if not recipe.get('recipeIngredient'):
        return False
    if not recipe.get('image'):
        return False

    instructions = recipe.get('recipeInstructions') or []
    if not instructions:
        return False

    # Require at least 2 steps and 50 words of instruction text in total
    total_words = sum(len(s.get('text', '').split()) for s in instructions)
    if len(instructions) < 2 or total_words < 50:
        return False

    return True


def fetch_and_stage(url: str) -> list[dict]:
    """
    Fetch RSS feed, scrape each recipe page for full JSON-LD data,
    download images locally, save complete results as staged recipes.
    Incomplete recipes (missing ingredients, instructions, or image) are silently skipped.
    """
    candidates = fetch_feed(url)
    staged = []

    for i, item in enumerate(candidates):
        try:
            if i > 0:
                time.sleep(PAGE_DELAY)

            ld = scrape_recipe_page(item['link']) if item.get('link') else None
            if not ld:
                continue  # No structured data at all — skip

            recipe = normalize_recipe(ld, item)

            # Download image locally and replace external URL with local path
            external_url = recipe.get('image')
            if external_url:
                local = download_image(external_url, recipe['slug'])
                if local:
                    recipe['image'] = local
                else:
                    recipe['image'] = None  # Download failed — clear so completeness check catches it

            # Only stage recipes that have all three required fields
            if not _is_complete(recipe):
                continue

            save_recipe_json(recipe, status='staged')
            staged.append(recipe)
        except Exception:
            continue

    return staged
