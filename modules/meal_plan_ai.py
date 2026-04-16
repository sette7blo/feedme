"""
modules/meal_plan_ai.py — AI-powered week plan generation
"""
import json
import re
from datetime import date, timedelta

import core.config as config
from modules.importer import list_recipes
from modules.pantry import list_pantry


def generate_week_plan(
    week_start: str,
    meals: list,
    people: int,
    max_weeknight_mins: int,
    dietary: list,
    use_pantry: bool,
    prompt: str,
) -> dict:
    api_key  = config.get("PPQ_API_KEY", "")
    base_url = config.get("PPQ_BASE_URL", "https://api.ppq.ai/v1")
    model    = config.get("PPQ_MODEL", "gpt-4o-mini")
    if not api_key:
        raise ValueError("No AI API key configured")

    data    = list_recipes(status="active", page=1, per_page=200)
    recipes = data.get("recipes", [])
    if not recipes:
        raise ValueError("No active recipes found in library")

    recipe_list = [
        {
            "slug":     r["slug"],
            "name":     r["name"],
            "category": r.get("category") or "",
            "cuisine":  r.get("cuisine") or "",
            "cook_time": r.get("cook_time") or r.get("total_time") or "",
            "tags":     r.get("tags") or "",
        }
        for r in recipes
    ]

    pantry_items = []
    if use_pantry:
        pantry_items = [p["food"] for p in list_pantry()]

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
            f"Weeknight recipes (Monday–Friday) should have cook_time ≤ {max_weeknight_mins} min where possible"
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
        "You are a meal planning assistant. Select recipes from the provided library to fill a weekly plan.\n"
        "Return ONLY a JSON array. Each element must have:\n"
        '  "date": "YYYY-MM-DD"\n'
        '  "meal_type": one of ' + json.dumps(meals) + "\n"
        '  "recipe_slug": exact slug from the library\n'
        '  "recipe_name": recipe name\n'
        "Rules:\n"
        "- Use only slugs from the library. Never invent slugs.\n"
        "- Avoid repeating the same recipe in the same week.\n"
        f"- Plan dates: {', '.join(dates)}\n"
        f"- Meals to plan per day: {', '.join(meals)}\n"
        f"- Additional constraints: {constraint_text}\n"
        "Return the raw JSON array with no markdown, no explanation."
    )

    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=base_url)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Recipe library:\n{json.dumps(recipe_list, ensure_ascii=False)}"},
        ],
        max_tokens=2000,
        temperature=0.7,
    )

    text = resp.choices[0].message.content.strip()
    m = re.search(r'\[[\s\S]*\]', text)
    if not m:
        raise ValueError("AI returned an unexpected format — no JSON array found")
    plan = json.loads(m.group(0))

    valid_slugs = {r["slug"] for r in recipes}
    plan = [
        p for p in plan
        if isinstance(p, dict)
        and p.get("recipe_slug") in valid_slugs
        and p.get("meal_type") in meals
        and p.get("date") in dates
    ]

    return {"plan": plan}
