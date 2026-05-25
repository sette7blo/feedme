"""
server.py — Feedme Flask application
Run: python server.py
"""
import gzip
import io
import json
import os
import threading
import time
from datetime import date, timedelta
from flask import Flask, jsonify, request, send_from_directory

import core.config as config
from core.ai import get_ai_config
from core.schema import init_db
from modules import importer, ai_chef, rss_fetcher, url_importer, pantry, meal_planner, grocery, camera, cook_log, meal_plan_ai, maintenance, ai_features

app = Flask(__name__, static_folder="frontend", static_url_path="")


@app.after_request
def compress_and_cache(response):
    # Skip non-success or already encoded
    if (response.status_code < 200 or response.status_code >= 300
            or 'Content-Encoding' in response.headers):
        return response

    # Gzip compressible responses if client accepts it
    ct = response.content_type or ''
    if ('gzip' in request.headers.get('Accept-Encoding', '')
            and any(t in ct for t in ('text/', 'application/json', 'application/javascript', 'image/svg'))):
        # For streamed/passthrough responses, read the data first
        if response.direct_passthrough:
            response.direct_passthrough = False
        data = response.get_data()
        if len(data) >= 512:
            buf = io.BytesIO()
            with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=6) as f:
                f.write(data)
            compressed = buf.getvalue()
            if len(compressed) < len(data):
                response.set_data(compressed)
                response.headers['Content-Encoding'] = 'gzip'
                response.headers['Content-Length'] = len(compressed)
                response.headers['Vary'] = 'Accept-Encoding'

    # Cache headers for static assets
    path = request.path
    if path.startswith('/images/'):
        # No cache when a ?t= buster is present (e.g. after regeneration)
        if request.query_string:
            response.headers['Cache-Control'] = 'no-cache'
        else:
            response.headers['Cache-Control'] = 'public, max-age=86400'
    elif path in ('/favicon.svg', '/apple-touch-icon.png'):
        response.headers['Cache-Control'] = 'public, max-age=604800'
    elif path == '/':
        response.headers['Cache-Control'] = 'no-cache'

    return response

# ── Init ──────────────────────────────────────────────────────────────────────

init_db()

# ── RSS auto-fetch scheduler ──────────────────────────────────────────────────

_rss_last_fetch = 0.0


def _rss_auto_fetch_loop():
    global _rss_last_fetch
    import logging
    log = logging.getLogger("rss_auto_fetch")
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
            feeds = [f.strip() for f in feeds_raw.split(",") if f.strip()]
            log.info("Auto-fetching %d RSS feeds", len(feeds))
            for url in feeds:
                try:
                    rss_fetcher.fetch_and_stage(url)
                except Exception as e:
                    log.warning("Auto-fetch failed for %s: %s", url, e)
            _rss_last_fetch = time.time()
            log.info("Auto-fetch complete")
        except Exception as e:
            log.warning("Auto-fetch loop error: %s", e)


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


@app.route("/api/recipes/batch", methods=["POST"])
def batch_recipes():
    data = request.get_json() or {}
    action = data.get("action", "")
    slugs = data.get("slugs", [])
    if not action:
        return jsonify({"error": "action required"}), 400
    if not isinstance(slugs, list) or not slugs:
        return jsonify({"error": "slugs must be a non-empty list"}), 400
    try:
        return jsonify(importer.batch_recipe_action(action, slugs))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


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
    return jsonify(ai_features.test_connection())


@app.route("/api/ai/balance", methods=["GET"])
def ai_balance():
    return jsonify(ai_features.balance())


@app.route("/api/ai/topup", methods=["POST"])
def ai_topup():
    payload, status = ai_features.create_topup(request.get_json())
    return jsonify(payload), status


@app.route("/api/ai/topup/status/<invoice_id>", methods=["GET"])
def ai_topup_status(invoice_id):
    payload, status = ai_features.topup_status(invoice_id)
    return jsonify(payload), status


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
    payload, status = ai_features.regenerate_recipe_image(slug)
    return jsonify(payload), status


# ── Import ────────────────────────────────────────────────────────────────────

@app.route("/api/import/rss/stats")
def rss_feed_stats():
    return jsonify(maintenance.rss_feed_stats())


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
    payload, status = ai_features.estimate_nutrition(slug)
    return jsonify(payload), status


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
        servings=data.get("servings")
    )
    return jsonify(entry), 201


@app.route("/api/mealplan/batch", methods=["POST"])
def add_meal_plan_batch():
    data = request.get_json() or {}
    slots = data.get("slots", [])
    if not isinstance(slots, list) or not slots:
        return jsonify({"error": "slots must be a non-empty list"}), 400
    result = meal_planner.add_slots_batch(slots)
    status = 207 if result["failed"] else 201
    return jsonify(result), status


@app.route("/api/mealplan/<int:plan_id>", methods=["PUT"])
def update_meal_plan(plan_id):
    data = request.get_json()
    servings = data.get("servings")
    if servings is None or servings < 1:
        return jsonify({"error": "servings required (>= 1)"}), 400
    entry = meal_planner.update_plan_servings(plan_id, servings)
    if not entry:
        return jsonify({"error": "Not found"}), 404
    return jsonify(entry)


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
    ai_config = get_ai_config()
    return jsonify({
        "ppq_api_key":      ai_config.api_key,
        "ppq_credit_id":    config.get("PPQ_CREDIT_ID", ""),
        "ppq_base_url":     ai_config.base_url,
        "ppq_model":        ai_config.text_model,
        "ppq_image_model":  ai_config.image_model,
        "ppq_vision_model": ai_config.vision_model,
        "ai_vision_detail": ai_config.vision_detail,
        "generate_images_by_default": ai_config.generate_images,
        "rss_feeds":           config.get("RSS_FEEDS", ""),
        "rss_auto_fetch_hours": config.get("RSS_AUTO_FETCH_HOURS", "0"),
        "equipment":           config.get("EQUIPMENT", ""),
        "preferred_units":     config.get("PREFERRED_UNITS", ""),
    })


@app.route("/api/settings", methods=["POST"])
def save_settings():
    data = request.get_json()
    updates = {}
    field_map = {
        "ppq_api_key":      "PPQ_API_KEY",
        "ppq_credit_id":    "PPQ_CREDIT_ID",
        "ppq_base_url":     "PPQ_BASE_URL",
        "ppq_model":        "PPQ_MODEL",
        "ppq_image_model":  "PPQ_IMAGE_MODEL",
        "ppq_vision_model": "PPQ_VISION_MODEL",
        "ai_vision_detail": "AI_VISION_DETAIL",
        "generate_images_by_default": "GENERATE_IMAGES_BY_DEFAULT",
        "rss_feeds":              "RSS_FEEDS",
        "rss_auto_fetch_hours":   "RSS_AUTO_FETCH_HOURS",
        "equipment":              "EQUIPMENT",
        "preferred_units":        "PREFERRED_UNITS",
    }
    for field, env_key in field_map.items():
        if field in data and data[field] is not None:
            updates[env_key] = data[field]

    config.save_env(updates)
    return jsonify({"ok": True})



# ── Version ───────────────────────────────────────────────────────────────────

@app.route("/api/version")
def get_version():
    return jsonify(maintenance.version_info())


# ── Backup & Restore ─────────────────────────────────────────────────────────

@app.route("/api/backup")
def download_backup():
    backup_bytes, filename = maintenance.create_backup()
    return app.response_class(
        backup_bytes,
        mimetype="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.route("/api/backup/restore", methods=["POST"])
def restore_backup():
    payload, status = maintenance.restore_backup(request.files.get("backup"))
    return jsonify(payload), status


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
