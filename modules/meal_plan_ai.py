"""
modules/meal_plan_ai.py — AI-powered week plan generation
"""
import json
import re
from datetime import date, timedelta

from core.ai import client as ai_client, require_api_key
from modules.importer import list_recipes
from modules.pantry import list_pantry

MAX_LIBRARY_SCAN = 500
MAX_AI_CANDIDATES = 60


def _minutes(value: str) -> int | None:
    if not value:
        return None
    text = str(value).upper()
    iso = re.search(r"PT(?:(\d+)H)?(?:(\d+)M)?", text)
    if iso:
        hours = int(iso.group(1) or 0)
        mins = int(iso.group(2) or 0)
        return hours * 60 + mins
    m = re.search(r"(\d+)", text)
    return int(m.group(1)) if m else None


def _terms(*values) -> set[str]:
    words = set()
    for value in values:
        for word in re.findall(r"[a-z0-9]+", str(value or "").lower()):
            if len(word) >= 4:
                words.add(word)
    return words


def _shortlist_recipes(recipes: list[dict], pantry_items: list[str], prompt: str, max_weeknight_mins: int) -> list[dict]:
    pantry_terms = _terms(" ".join(pantry_items[:50]))
    prompt_terms = _terms(prompt)

    scored = []
    for idx, recipe in enumerate(recipes):
        searchable = _terms(
            recipe.get("name"),
            recipe.get("category"),
            recipe.get("cuisine"),
            recipe.get("tags"),
        )
        mins = _minutes(recipe.get("cook_time") or recipe.get("total_time"))
        score = 0
        if prompt_terms:
            score += 5 * len(searchable & prompt_terms)
        if pantry_terms:
            score += 2 * len(searchable & pantry_terms)
        if max_weeknight_mins and mins is not None and mins <= max_weeknight_mins:
            score += 2
        if recipe.get("favorited"):
            score += 1
        # Stable tie-break keeps earlier/recent list ordering without sending everything.
        scored.append((score, -idx, recipe))

    scored.sort(reverse=True)
    selected = [recipe for _, _, recipe in scored[:MAX_AI_CANDIDATES]]
    if not selected:
        selected = recipes[:MAX_AI_CANDIDATES]
    return selected


def _recipe_summary(recipe: dict) -> dict:
    return {
        "slug": recipe["slug"],
        "name": recipe["name"],
        "category": recipe.get("category") or "",
        "cuisine": recipe.get("cuisine") or "",
        "cook_time": recipe.get("cook_time") or recipe.get("total_time") or "",
        "tags": recipe.get("tags") or "",
    }


def generate_week_plan(
    week_start: str,
    meals: list,
    people: int,
    max_weeknight_mins: int,
    dietary: list,
    use_pantry: bool,
    prompt: str,
) -> dict:
    try:
        ai_config = require_api_key()
    except ValueError:
        raise ValueError("No AI API key configured")

    data = list_recipes(status="active", page=1, per_page=MAX_LIBRARY_SCAN)
    recipes = data.get("recipes", [])
    if not recipes:
        raise ValueError("No active recipes found in library")

    pantry_items = []
    if use_pantry:
        pantry_items = [p["food"] for p in list_pantry()]

    candidates = _shortlist_recipes(recipes, pantry_items, prompt or "", max_weeknight_mins)
    recipe_list = [_recipe_summary(r) for r in candidates]
    recipes_by_slug = {r["slug"]: r for r in recipes}

    if not meals:
        meals = ["dinner"]

    try:
        start = date.fromisoformat(week_start)
    except Exception:
        start = date.today() - timedelta(days=date.today().weekday())
    dates = [(start + timedelta(days=i)).isoformat() for i in range(7)]

    constraints = []
    if people:
        constraints.append(f"Planning for {people} people")
    if max_weeknight_mins:
        constraints.append(
            f"Weeknight recipes (Monday-Friday) should have cook_time <= {max_weeknight_mins} min where possible"
        )
    if dietary:
        constraints.append(f"Dietary requirements: {', '.join(dietary)}")
    if pantry_items:
        constraints.append(
            f"Prefer recipes that use these pantry items: {', '.join(pantry_items[:30])}"
        )
    if prompt:
        constraints.append(prompt)
    constraint_text = "; ".join(constraints) if constraints else "Balanced variety across cuisines"

    system_prompt = (
        "You are a meal planning assistant. Select recipes from the provided candidate library to fill a weekly plan.\n"
        "Return ONLY a JSON array. Each element must have:\n"
        '  "date": "YYYY-MM-DD"\n'
        '  "meal_type": one of ' + json.dumps(meals) + "\n"
        '  "recipe_slug": exact slug from the candidate library\n'
        "Rules:\n"
        "- Use only slugs from the candidate library. Never invent slugs.\n"
        "- Avoid repeating the same recipe in the same week.\n"
        f"- Plan dates: {', '.join(dates)}\n"
        f"- Meals to plan per day: {', '.join(meals)}\n"
        f"- Additional constraints: {constraint_text}\n"
        "Return the raw JSON array with no markdown, no explanation."
    )

    client = ai_client(ai_config)
    resp = client.chat.completions.create(
        model=ai_config.text_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Candidate recipes ({len(recipe_list)} max):\n{json.dumps(recipe_list, ensure_ascii=False)}"},
        ],
        max_tokens=1200,
        temperature=0.7,
    )

    text = resp.choices[0].message.content.strip()
    m = re.search(r'\[[\s\S]*\]', text)
    if not m:
        raise ValueError("AI returned an unexpected format — no JSON array found")
    plan = json.loads(m.group(0))

    valid_slugs = {r["slug"] for r in candidates}
    cleaned = []
    for item in plan:
        if not isinstance(item, dict):
            continue
        slug = item.get("recipe_slug")
        if slug not in valid_slugs or item.get("meal_type") not in meals or item.get("date") not in dates:
            continue
        recipe = recipes_by_slug.get(slug, {})
        cleaned.append({
            "date": item["date"],
            "meal_type": item["meal_type"],
            "recipe_slug": slug,
            "recipe_name": recipe.get("name") or item.get("recipe_name") or slug,
        })

    return {"plan": cleaned, "candidate_count": len(recipe_list)}
