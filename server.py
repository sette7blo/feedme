"""
server.py — Feedme Flask application
Run: python server.py
"""
import json
import os
import threading
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory

import core.config as config
from core.schema import init_db
from modules import importer, ai_chef, rss_fetcher, url_importer, pantry, meal_planner, grocery, camera, mealie_importer, nostr_importer, nostr_publisher, cook_log, meal_plan_ai

app = Flask(__name__, static_folder="frontend", static_url_path="")

# ── Init ──────────────────────────────────────────────────────────────────────

init_db()

# ── RSS auto-fetch scheduler ──────────────────────────────────────────────────

_rss_last_fetch = 0.0


def _rss_auto_fetch_loop():
    global _rss_last_fetch
    while True:
        time.sleep(300)  # check every 5 minutes
        try:
            hours_str = config.get("RSS_AUTO_FETCH_HOURS", "0")
            hours = float(hours_str) if hours_str else 0
            if hours <= 0:
                continue
            interval = hours * 3600
            if time.time() - _rss_last_fetch < interval:
                continue
            feeds_raw = config.get("RSS_FEEDS", "")
            if not feeds_raw:
                continue
            feeds = [f.strip() for f in feeds_raw.split("\n") if f.strip()]
            for url in feeds:
                try:
                    rss_fetcher.fetch_and_stage(url)
                except Exception:
                    pass
            _rss_last_fetch = time.time()
        except Exception:
            pass


threading.Thread(target=_rss_auto_fetch_loop, daemon=True).start()

# ── Frontend ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("frontend", "index.html")

@app.route("/favicon.svg")
def serve_favicon():
    return send_from_directory("frontend", "favicon.svg")

@app.route("/apple-touch-icon.png")
def serve_touch_icon():
    return send_from_directory("frontend", "apple-touch-icon.png")

@app.route("/images/<path:filename>")
def serve_image(filename):
    return send_from_directory("images", filename)

# ── Recipes ───────────────────────────────────────────────────────────────────

@app.route("/api/recipes")
def list_recipes():
    status = request.args.get("status", "active")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 24))
    return jsonify(importer.list_recipes(status=status, page=page, per_page=per_page))


@app.route("/api/recipes/<slug>")
def get_recipe(slug):
    recipe = importer.get_recipe(slug)
    if not recipe:
        return jsonify({"error": "Not found"}), 404
    return jsonify(recipe)


@app.route("/api/recipes/approve/<slug>", methods=["POST"])
def approve_recipe(slug):
    ok = importer.approve_recipe(slug)
    return jsonify({"ok": ok})


@app.route("/api/recipes/<slug>", methods=["PUT"])
def update_recipe(slug):
    data = request.get_json()
    recipe = importer.update_recipe(slug, data)
    if not recipe:
        return jsonify({"error": "Not found"}), 404
    return jsonify(recipe)


@app.route("/api/recipes/<slug>", methods=["DELETE"])
def trash_recipe(slug):
    ok = importer.trash_recipe(slug)
    return jsonify({"ok": ok})


@app.route("/api/recipes/restore/<slug>", methods=["POST"])
def restore_recipe(slug):
    ok = importer.restore_recipe(slug)
    return jsonify({"ok": ok})


@app.route("/api/recipes/permanent/<slug>", methods=["DELETE"])
def permanent_delete_recipe(slug):
    ok = importer.permanent_delete_recipe(slug)
    return jsonify({"ok": ok})


@app.route("/api/recipes/sync", methods=["POST"])
def sync_recipes():
    result = importer.sync_all()
    return jsonify(result)


@app.route("/api/recipes/favorite/<slug>", methods=["POST"])
def toggle_favorite(slug):
    result = importer.toggle_favorite(slug)
    if result is None:
        return jsonify({"error": "Not found or not active"}), 404
    return jsonify(result)


# ── AI Generation ─────────────────────────────────────────────────────────────

@app.route("/api/ai/test", methods=["GET"])
def ai_test():
    """Quick connection test — sends a minimal request to the AI provider."""
    api_key  = config.get("PPQ_API_KEY", "")
    base_url = config.get("PPQ_BASE_URL", "https://api.ppq.ai/v1")
    model    = config.get("PPQ_MODEL", "gpt-4o-mini")
    if not api_key:
        return jsonify({"ok": False, "error": "No API key configured"})
    image_model  = config.get("PPQ_IMAGE_MODEL",  "dall-e-3")
    vision_model = config.get("PPQ_VISION_MODEL", "gpt-4o")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
        return jsonify({"ok": True, "recipe_model": model, "image_model": image_model, "vision_model": vision_model})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/ai/generate", methods=["POST"])
def ai_generate():
    data = request.get_json()
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "prompt required"}), 400
    try:
        recipe = ai_chef.generate_recipe(prompt)
        return jsonify(recipe)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Generation failed: {e}"}), 500


@app.route("/api/recipes/<slug>/regenerate-image", methods=["POST"])
def recipe_regenerate_image(slug):
    """Regenerate the AI food photo for an existing recipe."""
    api_key     = config.get("PPQ_API_KEY", "")
    base_url    = config.get("PPQ_BASE_URL", "https://api.ppq.ai/v1")
    image_model = config.get("PPQ_IMAGE_MODEL", "dall-e-3")
    if not api_key:
        return jsonify({"error": "No API key configured"}), 400
    recipe = importer.get_recipe(slug)
    if not recipe:
        return jsonify({"error": "Recipe not found"}), 404
    # Load full JSON for richer prompt context
    json_path = recipe.get("json_path")
    full = {}
    if json_path:
        import json as _json
        try:
            with open(json_path) as f:
                full = _json.load(f)
        except Exception:
            pass
    full.setdefault("name", recipe.get("name", slug))
    image_path = ai_chef._generate_image(full, slug, api_key, base_url, image_model)
    if not image_path:
        return jsonify({"error": "Image generation failed"}), 500
    # Update JSON and DB with new image path
    rel = f"images/{image_path.name}"
    importer.update_recipe(slug, {"image": rel})
    return jsonify({"ok": True, "image": rel})


# ── Import ────────────────────────────────────────────────────────────────────

@app.route("/api/import/rss", methods=["POST"])
def import_rss():
    data = request.get_json()
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "url required"}), 400
    try:
        staged = rss_fetcher.fetch_and_stage(url)
        return jsonify({"staged": len(staged), "recipes": staged})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/import/manual", methods=["POST"])
def import_manual():
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"error": "Recipe name required"}), 400
    status = data.pop("status", "active")
    path = importer.save_recipe_json(data, status=status)
    return jsonify({"ok": True, "slug": data.get("slug"), "path": str(path)})


@app.route("/api/import/text", methods=["POST"])
def import_text():
    data = request.get_json()
    text = (data or {}).get("text", "").strip()
    if not text:
        return jsonify({"error": "Text required"}), 400
    try:
        recipe = ai_chef.extract_recipe_from_text(text)
        return jsonify({"ok": True, "name": recipe.get("name"), "slug": recipe.get("slug")})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/import/url", methods=["POST"])
def import_url():
    data = request.get_json()
    url = (data or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "URL required"}), 400
    try:
        recipe = url_importer.import_from_url(url)
        return jsonify({"ok": True, "name": recipe.get("name"), "slug": recipe.get("slug")})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/import/camera", methods=["POST"])
def import_camera():
    files = request.files.getlist("images")
    if not files or all(not f.filename for f in files):
        return jsonify({"error": "No image files provided"}), 400
    allowed = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    images = []
    for f in files:
        if not f.filename:
            continue
        ext = os.path.splitext(f.filename.lower())[1]
        if ext not in allowed:
            return jsonify({"error": f"Unsupported file type: {ext}. Use JPG, PNG, or WebP."}), 400
        images.append((f.read(), f.filename))
    if not images:
        return jsonify({"error": "No valid image files provided"}), 400
    try:
        recipe = camera.import_from_images(images)
        return jsonify({"ok": True, "name": recipe.get("name"), "slug": recipe.get("slug")})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        return jsonify({"error": f"Vision extraction failed: {exc}"}), 500


# ── Mealie Import ─────────────────────────────────────────────────────────────

@app.route("/api/import/mealie/image/<recipe_id>")
def mealie_image_proxy(recipe_id):
    """Proxy a Mealie recipe image — adds auth header the browser can't send."""
    import urllib.request, urllib.error
    base_url = config.get("MEALIE_URL", "").strip()
    token    = config.get("MEALIE_TOKEN", "").strip()
    if not base_url or not token:
        return "", 404
    url = f"{base_url.rstrip('/')}/api/media/recipes/{recipe_id}/images/original.webp"
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read()
            ct   = resp.headers.get("Content-Type", "image/webp")
        return app.response_class(data, mimetype=ct)
    except Exception:
        return "", 404


@app.route("/api/import/mealie/browse")
def browse_mealie():
    base_url = config.get("MEALIE_URL", "").strip()
    token    = config.get("MEALIE_TOKEN", "").strip()
    if not base_url or not token:
        return jsonify({"error": "Mealie URL and token are required. Configure them in Settings."}), 400
    page = int(request.args.get("page", 1))
    try:
        return jsonify(mealie_importer.browse(base_url, token, page))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Mealie error: {exc}"}), 500


@app.route("/api/import/mealie", methods=["POST"])
def import_from_mealie():
    base_url = config.get("MEALIE_URL", "").strip()
    token    = config.get("MEALIE_TOKEN", "").strip()
    if not base_url or not token:
        return jsonify({"error": "Mealie URL and token are required. Configure them in Settings."}), 400
    data = request.get_json()
    slugs = data.get("slugs", [])
    if not slugs:
        return jsonify({"error": "No recipes selected"}), 400
    try:
        result = mealie_importer.import_recipes(base_url, token, slugs)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Import failed: {exc}"}), 500


@app.route("/api/import/nostr", methods=["POST"])
def import_from_nostr():
    data = request.get_json()
    events = data.get("events", [])
    if not events:
        return jsonify({"error": "No events provided"}), 400
    try:
        result = nostr_importer.import_events(events)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": f"Import failed: {exc}"}), 500


# ── Pantry ────────────────────────────────────────────────────────────────────

@app.route("/api/pantry")
def list_pantry_items():
    return jsonify(pantry.list_pantry())


@app.route("/api/pantry", methods=["POST"])
def add_pantry_item():
    data = request.get_json()
    item = pantry.add_item(
        food=data.get("food", ""),
        quantity=data.get("quantity"),
        unit=data.get("unit"),
        notes=data.get("notes")
    )
    return jsonify(item), 201


@app.route("/api/pantry/<int:item_id>", methods=["PUT"])
def update_pantry_item(item_id):
    data = request.get_json() or {}
    ok = pantry.update_item(item_id,
        **{k: data[k] for k in ("food", "quantity", "unit", "notes") if k in data}
    )
    return jsonify({"ok": ok})


@app.route("/api/pantry/<int:item_id>", methods=["DELETE"])
def delete_pantry_item(item_id):
    ok = pantry.delete_item(item_id)
    return jsonify({"ok": ok})


# ── Nutrition ────────────────────────────────────────────────────────────────

@app.route("/api/recipes/<slug>/nutrition", methods=["POST"])
def estimate_nutrition(slug):
    api_key  = config.get("PPQ_API_KEY", "")
    base_url = config.get("PPQ_BASE_URL", "https://api.ppq.ai/v1")
    model    = config.get("PPQ_MODEL", "gpt-4o-mini")
    if not api_key:
        return jsonify({"error": "No API key configured"}), 400
    recipe = importer.get_recipe(slug)
    if not recipe:
        return jsonify({"error": "Recipe not found"}), 404
    full = recipe.get("full", {})
    ingredients = full.get("recipeIngredient", [])
    servings_raw = full.get("recipeYield", "")
    servings = 1
    import re
    m = re.search(r"\d+", str(servings_raw))
    if m:
        servings = int(m.group(0))
    if not ingredients:
        return jsonify({"error": "Recipe has no ingredients"}), 400
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        recipe_name = full.get("name") or recipe.get("name", slug)
        resp = client.chat.completions.create(
            model=model,
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
        import re as _re
        m2 = _re.search(r'\{[\s\S]*\}', text)
        if not m2:
            return jsonify({"error": "AI returned unexpected format"}), 500
        nutrition = json.loads(m2.group(0))
        nutrition["@type"] = "NutritionInformation"
        importer.update_recipe(slug, {"nutrition": nutrition})
        return jsonify({"ok": True, "nutrition": nutrition})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Cook Log ─────────────────────────────────────────────────────────────────

@app.route("/api/cooklog/<slug>", methods=["POST"])
def log_cook(slug):
    recipe = importer.get_recipe(slug)
    if not recipe or recipe.get("status") != "active":
        return jsonify({"error": "Recipe not found"}), 404
    data = request.get_json() or {}
    entry = cook_log.add_entry(
        slug=slug,
        servings=data.get("servings"),
        notes=data.get("notes")
    )
    return jsonify(entry), 201


@app.route("/api/cooklog/<slug>")
def get_cook_log(slug):
    return jsonify(cook_log.get_history(slug))


# ── Meal Plan ─────────────────────────────────────────────────────────────────

@app.route("/api/mealplan")
def get_meal_plan():
    week = request.args.get("week")
    if not week:
        d = date.today()
        week = str(d - timedelta(days=d.weekday()))
    return jsonify(meal_planner.get_week(week))


@app.route("/api/mealplan", methods=["POST"])
def add_meal_plan():
    data = request.get_json()
    entry = meal_planner.add_to_plan(
        date=data["date"],
        meal_type=data["meal_type"],
        recipe_slug=data["recipe_slug"],
        servings=data.get("servings", 1)
    )
    return jsonify(entry), 201


@app.route("/api/mealplan/<int:plan_id>", methods=["DELETE"])
def delete_meal_plan(plan_id):
    ok = meal_planner.remove_from_plan(plan_id)
    return jsonify({"ok": ok})


@app.route("/api/mealplan/ingredients")
def plan_ingredients():
    start = request.args.get("start")
    end = request.args.get("end")
    if not start or not end:
        return jsonify({"error": "start and end dates required"}), 400
    ingredients = meal_planner.get_aggregate_ingredients(start, end)
    return jsonify(ingredients)


@app.route("/api/mealplan/generate", methods=["POST"])
def ai_generate_week_plan():
    data = request.get_json() or {}
    try:
        result = meal_plan_ai.generate_week_plan(
            week_start=data.get("week_start", ""),
            meals=data.get("meals", ["dinner"]),
            people=data.get("people"),
            max_weeknight_mins=data.get("max_weeknight_mins"),
            dietary=data.get("dietary", []),
            use_pantry=data.get("use_pantry", False),
            prompt=data.get("prompt", ""),
        )
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Generation failed: {e}"}), 500


@app.route("/api/mealplan/templates")
def list_templates():
    from core.db import db, rows_to_list
    with db() as conn:
        rows = conn.execute("SELECT * FROM meal_plan_templates ORDER BY created_at DESC").fetchall()
    return jsonify(rows_to_list(rows))


@app.route("/api/mealplan/templates", methods=["POST"])
def save_template():
    from core.db import db, row_to_dict
    data = request.get_json() or {}
    name  = (data.get("name") or "").strip()
    slots = data.get("slots", [])
    if not name:
        return jsonify({"error": "name required"}), 400
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO meal_plan_templates (name, slots) VALUES (?,?)",
            (name, json.dumps(slots, ensure_ascii=False))
        )
        row = conn.execute("SELECT * FROM meal_plan_templates WHERE id=?", (cur.lastrowid,)).fetchone()
    r = row_to_dict(row)
    r["slots"] = json.loads(r["slots"])
    return jsonify(r), 201


@app.route("/api/mealplan/templates/<int:tmpl_id>", methods=["DELETE"])
def delete_template(tmpl_id):
    from core.db import db
    with db() as conn:
        conn.execute("DELETE FROM meal_plan_templates WHERE id=?", (tmpl_id,))
    return jsonify({"ok": True})


# ── Grocery ───────────────────────────────────────────────────────────────────

@app.route("/api/grocery")
def get_grocery():
    list_date = request.args.get("date")
    return jsonify({
        "items":        grocery.get_shopping_list(list_date),
        "pantry_items": grocery.get_pantry_covered(list_date),
    })


@app.route("/api/grocery/generate", methods=["POST"])
def generate_grocery():
    data = request.get_json()
    result = grocery.generate_shopping_list(
        start_date=data["start"],
        end_date=data["end"],
        list_date=data.get("list_date")
    )
    return jsonify(result)


@app.route("/api/grocery", methods=["POST"])
def add_grocery_item():
    data = request.get_json()
    item = grocery.add_manual_item(
        food=data.get("food", ""),
        quantity=data.get("quantity"),
        unit=data.get("unit"),
        list_date=data.get("list_date")
    )
    return jsonify(item), 201


@app.route("/api/grocery/<int:item_id>", methods=["PUT"])
def update_grocery_item(item_id):
    data = request.get_json()
    ok = grocery.check_item(item_id, checked=data.get("checked", True))
    return jsonify({"ok": ok})


@app.route("/api/grocery/clear", methods=["DELETE"])
def clear_grocery():
    grocery.clear_checked()
    return jsonify({"ok": True})


@app.route("/api/grocery/clear-all", methods=["DELETE"])
def clear_grocery_all():
    list_date = request.args.get("date")
    grocery.clear_list(list_date)
    return jsonify({"ok": True})


# ── Settings ──────────────────────────────────────────────────────────────────

@app.route("/api/settings")
def get_settings():
    return jsonify({
        "ppq_api_key":      config.get("PPQ_API_KEY", ""),
        "ppq_base_url":     config.get("PPQ_BASE_URL", "https://api.ppq.ai/v1"),
        "ppq_model":        config.get("PPQ_MODEL", "gpt-4o-mini"),
        "ppq_image_model":  config.get("PPQ_IMAGE_MODEL", "dall-e-3"),
        "ppq_vision_model": config.get("PPQ_VISION_MODEL", "gpt-4o"),
        "mealie_url":       config.get("MEALIE_URL", ""),
        "mealie_token":     config.get("MEALIE_TOKEN", ""),
        "nostr_relay":      config.get("NOSTR_RELAY", ""),
        "nostr_nsec":       config.get("NOSTR_NSEC", ""),
        "rss_feeds":           config.get("RSS_FEEDS", ""),
        "rss_auto_fetch_hours": config.get("RSS_AUTO_FETCH_HOURS", "0"),
        "equipment":           config.get("EQUIPMENT", ""),
    })


@app.route("/api/settings", methods=["POST"])
def save_settings():
    data = request.get_json()
    updates = {}
    field_map = {
        "ppq_api_key":      "PPQ_API_KEY",
        "ppq_base_url":     "PPQ_BASE_URL",
        "ppq_model":        "PPQ_MODEL",
        "ppq_image_model":  "PPQ_IMAGE_MODEL",
        "ppq_vision_model": "PPQ_VISION_MODEL",
        "mealie_url":       "MEALIE_URL",
        "mealie_token":     "MEALIE_TOKEN",
        "nostr_relay":      "NOSTR_RELAY",
        "nostr_nsec":       "NOSTR_NSEC",
        "rss_feeds":              "RSS_FEEDS",
        "rss_auto_fetch_hours":   "RSS_AUTO_FETCH_HOURS",
        "equipment":              "EQUIPMENT",
    }
    for field, env_key in field_map.items():
        if field in data and data[field] is not None:
            updates[env_key] = data[field]

    config.save_env(updates)
    return jsonify({"ok": True})


# ── Nostr ────────────────────────────────────────────────────────────────────

@app.route("/api/nostr/known-events")
def nostr_known_events():
    """Return set of nostr_event_ids already in the DB (non-trashed)."""
    from core.db import db
    with db() as conn:
        rows = conn.execute(
            "SELECT nostr_event_id FROM recipes WHERE nostr_event_id IS NOT NULL AND nostr_event_id != '' AND status != 'trashed'"
        ).fetchall()
    return jsonify({"ids": [r["nostr_event_id"] for r in rows]})


@app.route("/api/nostr/generate-key", methods=["POST"])
def nostr_generate_key():
    try:
        keypair = nostr_publisher.generate_keypair()
        config.save_env({"NOSTR_NSEC": keypair["nsec"]})
        return jsonify({"npub": keypair["npub"], "nsec": keypair["nsec"]})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/nostr/pubkey")
def nostr_pubkey():
    nsec = config.get("NOSTR_NSEC", "").strip()
    if not nsec:
        return jsonify({"npub": None})
    try:
        return jsonify({"npub": nostr_publisher.get_pubkey(nsec)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/export/nostr/<slug>", methods=["POST"])
def export_to_nostr(slug):
    nsec = config.get("NOSTR_NSEC", "").strip()
    if not nsec:
        return jsonify({"error": "No Nostr private key configured. Set one in Settings."}), 400
    recipe = importer.get_recipe(slug)
    if not recipe:
        return jsonify({"error": "Recipe not found"}), 404
    try:
        # Upload local image to nostr.build before signing
        image_url = None
        image_warning = None
        local_img = recipe.get("image_url", "")
        if local_img and not local_img.startswith("http"):
            try:
                image_url = nostr_publisher.upload_image(local_img, nsec)
            except Exception as img_exc:
                image_warning = str(img_exc)
                print(f"nostr.build upload failed for {slug}: {img_exc}")
        elif local_img.startswith("http"):
            image_url = local_img

        event = nostr_publisher.sign_recipe_event_full(
            recipe, recipe.get("full", {}), nsec, image_url=image_url
        )
        return jsonify({"event": event, "image_uploaded": bool(image_url), "image_warning": image_warning})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/export/nostr/<slug>/save-event-id", methods=["POST"])
def nostr_save_event_id(slug):
    """Called after client successfully publishes to relay."""
    data = request.get_json()
    event_id = data.get("event_id", "")
    if not event_id:
        return jsonify({"error": "event_id required"}), 400
    with __import__("core.db", fromlist=["db"]).db() as conn:
        conn.execute(
            "UPDATE recipes SET nostr_event_id=?, updated_at=datetime('now') WHERE slug=?",
            (event_id, slug)
        )
    # Also write to JSON file
    recipe = importer.get_recipe(slug)
    if recipe and recipe.get("json_path"):
        from pathlib import Path
        import json as _json
        p = Path(recipe["json_path"])
        if p.exists():
            with open(p) as f:
                data_json = _json.load(f)
            data_json["nostr_event_id"] = event_id
            with open(p, "w") as f:
                _json.dump(data_json, f, indent=2, ensure_ascii=False)
    return jsonify({"ok": True})


# ── Version ───────────────────────────────────────────────────────────────────

_version_cache = {"latest": None, "checked_at": 0}
_VERSION_FILE = Path(__file__).parent / "VERSION"
_GITHUB_API = "https://api.github.com/repos/sette7blo/feedme/releases/latest"
_CACHE_TTL = 3600  # 1 hour


def _read_local_version() -> str:
    try:
        return _VERSION_FILE.read_text().strip()
    except OSError:
        return "unknown"


def _do_fetch_latest_version():
    try:
        req = urllib.request.Request(
            _GITHUB_API,
            headers={"User-Agent": "Feedme/1.0", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        tag = data.get("tag_name", "").lstrip("v")
        _version_cache["latest"] = tag
        _version_cache["checked_at"] = time.time()
    except Exception:
        pass


def _fetch_latest_version() -> str | None:
    now = time.time()
    if _version_cache["latest"] and now - _version_cache["checked_at"] < _CACHE_TTL:
        return _version_cache["latest"]
    # Fetch in background — return stale/None immediately
    threading.Thread(target=_do_fetch_latest_version, daemon=True).start()
    return _version_cache["latest"]


@app.route("/api/version")
def get_version():
    current = _read_local_version()
    latest = _fetch_latest_version()
    update_available = False
    if latest and current != "unknown":
        try:
            def _parse(v):
                return tuple(int(x) for x in v.split("."))
            update_available = _parse(latest) > _parse(current)
        except Exception:
            update_available = latest != current
    return jsonify({
        "current": current,
        "latest": latest,
        "update_available": update_available,
        "release_url": "https://github.com/sette7blo/feedme/releases/latest",
    })


# ── Export ────────────────────────────────────────────────────────────────────

@app.route("/api/export/json/<slug>")
def export_json(slug):
    recipe = importer.get_recipe(slug)
    if not recipe:
        return jsonify({"error": "Not found"}), 404
    full = recipe.get("full", recipe)
    return app.response_class(
        json.dumps(full, indent=2, ensure_ascii=False),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={slug}.json"}
    )


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    host = config.get("FLASK_HOST", "0.0.0.0")
    port = int(config.get("FLASK_PORT", 5000))
    debug = config.get("FLASK_DEBUG", "false").lower() == "true"
    print(f"Feedme running at http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)
