"""
modules/ai_chef.py — PPQ.ai (OpenAI-compatible) → schema.org/Recipe JSON
Generated recipes land in 'staged' status for user approval.
"""
import json
import re
import urllib.request
from datetime import date
from pathlib import Path
from openai import OpenAI
from core import config
from core.db import db
from modules.importer import save_recipe_json, slugify


IMAGES_DIR = Path(__file__).parent.parent / "images"

SYSTEM_PROMPT = """You are a professional chef and recipe writer. 
When given a recipe request, respond ONLY with a valid JSON object following schema.org/Recipe format.
No preamble, no explanation, no markdown — raw JSON only.

Required fields:
- @context: "https://schema.org"
- @type: "Recipe"
- name: string
- slug: url-friendly version of name (lowercase, hyphens)
- description: 1-2 sentence description
- prepTime: ISO 8601 duration (e.g. "PT15M")
- cookTime: ISO 8601 duration
- totalTime: ISO 8601 duration
- recipeYield: "X servings"
- recipeCategory: e.g. "Dinner", "Breakfast", "Dessert"
- recipeCuisine: e.g. "Italian", "French"
- keywords: comma-separated tags
- recipeIngredient: array of strings (e.g. "200g pasta")
- recipeInstructions: array of {"@type": "HowToStep", "text": "..."} objects
- tools: array of strings listing required equipment (e.g. ["Dutch oven", "stand mixer", "baking sheet"]) — only major/specific items, not basic utensils like knives or spoons
- nutrition: {} (empty object if unknown)
- source_type: "ai"
"""


def generate_recipe(prompt: str) -> dict:
    """
    Generate a recipe from a natural language prompt.
    Returns the recipe dict (saved as staged JSON).
    Raises on API error.
    """
    api_key = config.get("PPQ_API_KEY")
    if not api_key:
        raise ValueError("PPQ_API_KEY not configured. Add it in Settings.")

    base_url = config.get("PPQ_BASE_URL", "https://api.ppq.ai/v1")
    model = config.get("PPQ_MODEL", "gpt-4o-mini")

    equipment = config.get("EQUIPMENT", "").strip()
    full_prompt = prompt
    if equipment:
        full_prompt += f"\n\nAvailable kitchen equipment: {equipment}. Only suggest techniques and tools that work with this equipment."

    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": full_prompt}
        ],
        temperature=0.7,
        max_tokens=2000
    )
    content = response.choices[0].message.content.strip()

    # Strip markdown fences if present
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)

    recipe_data = json.loads(content)
    recipe_data["datePublished"] = date.today().isoformat()

    # Ensure slug
    if "slug" not in recipe_data:
        recipe_data["slug"] = slugify(recipe_data.get("name", "recipe"))

    # Generate image (best-effort — never blocks recipe save)
    slug = recipe_data["slug"]
    image_model = config.get("PPQ_IMAGE_MODEL", "dall-e-3")
    try:
        image_path = _generate_image(recipe_data, slug, api_key, base_url, image_model)
    except Exception:
        image_path = None
    if image_path:
        recipe_data["image"] = f"images/{image_path.name}"

    # Save as staged
    path = save_recipe_json(recipe_data, status="staged")

    # Ensure image_url is in DB (ON CONFLICT in save_recipe_json doesn't update it)
    if image_path:
        with db() as conn:
            conn.execute(
                "UPDATE recipes SET image_url=?, updated_at=datetime('now') WHERE slug=?",
                (recipe_data["image"], slug)
            )

    return recipe_data


EXTRACT_PROMPT = """You are a recipe data extractor. The user will paste raw recipe text copied from a website.
Extract it and respond ONLY with a valid JSON object following schema.org/Recipe format.
No preamble, no explanation, no markdown — raw JSON only.

Required fields: @context, @type, name, slug, description, prepTime, cookTime, totalTime,
recipeYield, recipeCategory, recipeCuisine, keywords, recipeIngredient, recipeInstructions,
nutrition, source_type ("url").

Use ISO 8601 durations for times (e.g. "PT15M"). If a value is unknown use "" or [].
slug must be url-friendly lowercase with hyphens.
recipeInstructions must be an array of {"@type": "HowToStep", "text": "..."} objects.
"""


def extract_recipe_from_text(text: str) -> dict:
    """
    Use AI to extract a structured recipe from pasted raw text.
    Saves as staged. Raises on API error or parse failure.
    """
    api_key = config.get("PPQ_API_KEY")
    if not api_key:
        raise ValueError("PPQ_API_KEY not configured. Add it in Settings.")

    base_url = config.get("PPQ_BASE_URL", "https://api.ppq.ai/v1")
    model = config.get("PPQ_MODEL", "gpt-4o-mini")

    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": EXTRACT_PROMPT},
            {"role": "user", "content": text[:12000]},  # cap to avoid token overflow
        ],
        temperature=0.2,
        max_tokens=2000,
    )
    content = response.choices[0].message.content.strip()

    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)

    recipe_data = json.loads(content)
    recipe_data["datePublished"] = date.today().isoformat()
    if "slug" not in recipe_data:
        recipe_data["slug"] = slugify(recipe_data.get("name", "recipe"))

    save_recipe_json(recipe_data, status="staged")
    return recipe_data


def _generate_image(recipe_data: dict, slug: str, api_key: str, base_url: str, model: str) -> Path:
    """
    Generate a food photo for the recipe via the images API.
    Downloads and saves to images/<slug>.png.
    Returns the Path on success, raises on any failure.
    """
    IMAGES_DIR.mkdir(exist_ok=True)
    dest = IMAGES_DIR / f"{slug}.png"

    name = recipe_data.get("name", "dish")
    cuisine = recipe_data.get("recipeCuisine", "")
    category = recipe_data.get("recipeCategory", "")
    description = recipe_data.get("description", "")
    prompt = (
        f"Professional food photography of {name}"
        + (f", {cuisine} cuisine" if cuisine else "")
        + (f", {category}" if category else "")
        + (f". {description}" if description else "")
        + ". Overhead shot, natural light, styled on a wooden surface, high resolution."
    )

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=60.0)
    gpt_image_models = {"gpt-image-1", "gpt-image-1.5", "gpt-image-2"}
    kwargs = dict(model=model, prompt=prompt, n=1)
    if model in gpt_image_models:
        kwargs["quality"] = "low"
    else:
        kwargs["size"] = "1:1"
    response = client.images.generate(**kwargs)
    item = response.data[0]
    if getattr(item, "b64_json", None):
        import base64
        dest.write_bytes(base64.b64decode(item.b64_json))
    elif getattr(item, "url", None):
        urllib.request.urlretrieve(item.url, dest)
    else:
        raise ValueError("Image API returned no url or b64_json data")
    return dest
