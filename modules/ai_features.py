"""AI-adjacent route helpers for Feedme.

Groups account, generated-image, and nutrition endpoints so server.py can stay
focused on route wiring without creating many tiny helper modules.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from core.ai import client as ai_client, get_ai_config
import core.config as config
from modules import ai_chef, importer

TOPUP_METHODS = {
    "xmr": {"min": 5, "max": 10000},
}


def extract_json_object(text: str) -> dict:
    """Extract and parse the first JSON object embedded in AI text."""
    match = re.search(r"\{[\s\S]*\}", text or "")
    if not match:
        raise ValueError("AI returned unexpected format")
    return json.loads(match.group(0))


def parse_servings(servings_raw) -> int:
    """Return the first integer in a recipe yield string, or 1."""
    match = re.search(r"\d+", str(servings_raw or ""))
    return int(match.group(0)) if match else 1


def test_connection() -> dict[str, object]:
    """Send a minimal request to the configured AI provider."""
    ai_config = get_ai_config()
    if not ai_config.api_key:
        return {"ok": False, "error": "No API key configured"}
    try:
        client = ai_client(ai_config)
        client.chat.completions.create(
            model=ai_config.text_model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
        return {
            "ok": True,
            "recipe_model": ai_config.text_model,
            "image_model": ai_config.image_model,
            "vision_model": ai_config.vision_model,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def balance() -> dict[str, object]:
    credit_id = config.get("PPQ_CREDIT_ID", "")
    if not credit_id:
        return {"ok": False, "error": "No credit ID configured"}
    try:
        body = json.dumps({"credit_id": credit_id}).encode()
        rq = urllib.request.Request(
            "https://api.ppq.ai/credits/balance",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(rq, timeout=10) as resp:
            data = json.loads(resp.read())
        return {"ok": True, "balance": data.get("balance", 0)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def create_topup(data: dict | None) -> tuple[dict[str, object], int]:
    ai_config = get_ai_config()
    api_key = ai_config.api_key
    if not api_key:
        return {"ok": False, "error": "No API key configured"}, 400
    data = data or {}
    method = data.get("method", "")
    amount = data.get("amount")
    currency = data.get("currency", "USD")
    if method not in TOPUP_METHODS:
        return {"ok": False, "error": f"Unsupported method. Use: {', '.join(TOPUP_METHODS)}"}, 400
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid amount"}, 400
    limits = TOPUP_METHODS[method]
    if currency == "USD" and (amount < limits["min"] or amount > limits["max"]):
        return {"ok": False, "error": f"Amount must be ${limits['min']}-${limits['max']} for {method}"}, 400
    try:
        body = json.dumps({"amount": amount, "currency": currency}).encode()
        rq = urllib.request.Request(
            f"https://api.ppq.ai/topup/create/{method}",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(rq, timeout=15) as resp:
            result = json.loads(resp.read())
        return {"ok": True, **result}, 200
    except urllib.error.HTTPError as e:
        err_body = e.read().decode() if e.fp else str(e)
        return {"ok": False, "error": err_body}, e.code
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


def topup_status(invoice_id: str) -> tuple[dict[str, object], int]:
    api_key = get_ai_config().api_key
    if not api_key:
        return {"ok": False, "error": "No API key configured"}, 400
    try:
        rq = urllib.request.Request(
            f"https://api.ppq.ai/topup/status/{invoice_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        with urllib.request.urlopen(rq, timeout=10) as resp:
            result = json.loads(resp.read())
        return {"ok": True, **result}, 200
    except urllib.error.HTTPError as e:
        err_body = e.read().decode() if e.fp else str(e)
        return {"ok": False, "error": err_body}, e.code
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


def regenerate_recipe_image(slug: str) -> tuple[dict[str, object], int]:
    """Regenerate the AI food photo for an existing recipe."""
    ai_config = get_ai_config()
    if not ai_config.api_key:
        return {"error": "No API key configured"}, 400
    recipe = importer.get_recipe(slug)
    if not recipe:
        return {"error": "Recipe not found"}, 404

    json_path = recipe.get("json_path")
    full = {}
    if json_path:
        try:
            with open(json_path) as f:
                full = json.load(f)
        except Exception:
            pass
    full.setdefault("name", recipe.get("name", slug))
    try:
        image_path = ai_chef._generate_image(
            full,
            slug,
            ai_config.api_key,
            ai_config.base_url,
            ai_config.image_model,
        )
    except Exception as e:
        return {"error": str(e)}, 500
    rel = f"images/{image_path.name}"
    importer.update_recipe(slug, {"image": rel})
    return {"ok": True, "image": rel}, 200


def estimate_nutrition(slug: str) -> tuple[dict[str, object], int]:
    ai_config = get_ai_config()
    if not ai_config.api_key:
        return {"error": "No API key configured"}, 400
    recipe = importer.get_recipe(slug)
    if not recipe:
        return {"error": "Recipe not found"}, 404
    full = recipe.get("full", {})
    ingredients = full.get("recipeIngredient", [])
    servings = parse_servings(full.get("recipeYield", ""))
    if not ingredients:
        return {"error": "Recipe has no ingredients"}, 400
    try:
        client = ai_client(ai_config)
        recipe_name = full.get("name") or recipe.get("name", slug)
        resp = client.chat.completions.create(
            model=ai_config.text_model,
            messages=[
                {"role": "system", "content": (
                    "You are a nutrition expert. Estimate per-serving nutritional values for a recipe.\n"
                    "IMPORTANT:\n"
                    f"- The recipe is: {recipe_name}\n"
                    f"- Total yield: {servings} serving(s)\n"
                    "- Calculate the TOTAL nutrition for ALL ingredients combined, then DIVIDE by the number of servings.\n"
                    "- Return values for ONE serving only.\n"
                    "- Calories should be a realistic number (typical main dish: 400-800 kcal/serving, side dish: 150-350 kcal/serving).\n"
                    "Return ONLY a JSON object with these exact fields:\n"
                    '{"calories": number, "proteinContent": "Xg", "fatContent": "Xg", "carbohydrateContent": "Xg", '
                    '"fiberContent": "Xg", "sugarContent": "Xg", "sodiumContent": "Xmg"}\n'
                    "No markdown, no explanation — just the JSON object."
                )},
                {"role": "user", "content": f"Recipe: {recipe_name} ({servings} servings)\nIngredients:\n" + "\n".join(ingredients)},
            ],
            max_tokens=300,
            temperature=0,
        )
        text = resp.choices[0].message.content.strip()
        nutrition = extract_json_object(text)
        nutrition["@type"] = "NutritionInformation"
        importer.update_recipe(slug, {"nutrition": nutrition})
        return {"ok": True, "nutrition": nutrition}, 200
    except ValueError as e:
        return {"error": str(e)}, 500
    except Exception as e:
        return {"error": str(e)}, 500
