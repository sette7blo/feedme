"""
modules/camera.py — Image(s) → schema.org/Recipe JSON via AI vision.
Accepts one or more images (e.g. multi-page cookbook spread), sends them
all in a single vision request, extracts and saves a complete recipe.
The first image is saved locally and used as the recipe photo.
Lands in 'staged' status.
"""
import base64
import json
import re
from datetime import date
from pathlib import Path
from openai import OpenAI
from core import config
from core.db import db
from modules.importer import save_recipe_json, slugify
from modules.ai_chef import _generate_image

_SINGLE_PROMPT = """You are a recipe data extractor with computer vision.
The user will provide an image of a recipe — a cookbook page, recipe card,
handwritten note, or screenshot. Extract EVERY part of the recipe visible
in the image and respond ONLY with a valid JSON object following
schema.org/Recipe format.
No preamble, no explanation, no markdown fences — raw JSON only."""

_MULTI_PROMPT = """You are a recipe data extractor with computer vision.
The user will provide multiple images that together show a single recipe —
for example two pages of a cookbook, or several screenshots of a long recipe.
Scan ALL images carefully and combine them into one complete recipe.
Respond ONLY with a valid JSON object following schema.org/Recipe format.
No preamble, no explanation, no markdown fences — raw JSON only."""

_FIELDS = """
Required fields:
- @context: "https://schema.org"
- @type: "Recipe"
- name: string
- slug: url-friendly lowercase with hyphens
- description: 1-2 sentences
- prepTime: ISO 8601 (e.g. "PT15M") or ""
- cookTime: ISO 8601 or ""
- totalTime: ISO 8601 or ""
- recipeYield: "X servings" or ""
- recipeCategory: e.g. "Dinner" or ""
- recipeCuisine: e.g. "Italian" or ""
- keywords: comma-separated string or ""
- recipeIngredient: array of ingredient strings (e.g. ["200g pasta", "2 eggs"])
- recipeInstructions: array of {"@type": "HowToStep", "text": "..."} objects

IMPORTANT for recipeInstructions: look carefully for the method, directions,
or steps section — it may be in a different column, smaller text, or lower on
the page. Extract EVERY numbered or bulleted step. Do not leave this empty if
instructions are visible anywhere in the images.

- nutrition: {}
- source_type: "camera"

If a field truly cannot be read from the images, use "" or []. Never invent
information that is not visible in the images.
"""

_MIME = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".webp": "image/webp",
    ".gif":  "image/gif",
}


def import_from_images(images: list[tuple[bytes, str]]) -> dict:
    """
    Send one or more images to the vision model, extract a complete recipe,
    save as staged. Returns the recipe dict. Raises ValueError or Exception on failure.

    images: list of (image_bytes, filename) tuples — order matters (page 1, page 2, …)
    """
    if not images:
        raise ValueError("No images provided.")

    api_key  = config.get("PPQ_API_KEY")
    if not api_key:
        raise ValueError("PPQ_API_KEY not configured. Add it in Settings.")

    base_url = config.get("PPQ_BASE_URL", "https://api.ppq.ai/v1")
    model    = config.get("PPQ_VISION_MODEL", "gpt-4o")

    multi    = len(images) > 1
    system   = (_MULTI_PROMPT if multi else _SINGLE_PROMPT) + _FIELDS
    user_text = (
        "Extract the complete recipe from these images. "
        "They show different parts of the same recipe — combine them into one result."
        if multi else
        "Extract the recipe from this image."
    )

    # Build content blocks: all images first, then the instruction text
    content_blocks = []
    for img_bytes, filename in images:
        ext       = Path(filename).suffix.lower()
        mime_type = _MIME.get(ext, "image/jpeg")
        b64       = base64.b64encode(img_bytes).decode("utf-8")
        data_url  = f"data:{mime_type};base64,{b64}"
        content_blocks.append({
            "type":      "image_url",
            "image_url": {"url": data_url, "detail": "high"},
        })
    content_blocks.append({"type": "text", "text": user_text})

    client = OpenAI(api_key=api_key, base_url=base_url)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": content_blocks},
        ],
        max_tokens=2500,
        temperature=0.2,
    )

    content = response.choices[0].message.content.strip()
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$",          "", content)

    recipe_data = json.loads(content)
    recipe_data["datePublished"] = date.today().isoformat()
    recipe_data["source_type"]   = "camera"

    if "slug" not in recipe_data or not recipe_data["slug"]:
        recipe_data["slug"] = slugify(recipe_data.get("name", "recipe"))

    # Generate a clean food photo from the recipe data (best-effort, never blocks save)
    slug        = recipe_data["slug"]
    image_model = config.get("PPQ_IMAGE_MODEL", "dall-e-3")
    image_path  = _generate_image(recipe_data, slug, api_key, base_url, image_model)
    if image_path:
        recipe_data["image"] = f"images/{image_path.name}"

    save_recipe_json(recipe_data, status="staged")

    # Ensure image_url is stored in DB
    if image_path:
        with db() as conn:
            conn.execute(
                "UPDATE recipes SET image_url=?, updated_at=datetime('now') WHERE slug=?",
                (recipe_data["image"], slug)
            )

    return recipe_data
