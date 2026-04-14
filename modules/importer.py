"""
modules/importer.py — Sync JSON recipe files → SQLite
Recipes dir is the source of truth. SQLite is rebuilt from it.
"""
import json
import re
from pathlib import Path
from core.db import db, rows_to_list, row_to_dict

RECIPES_DIR = Path(__file__).parent.parent / "recipes"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def parse_recipe_json(path: Path) -> dict | None:
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    name = data.get("name", path.stem)
    slug = data.get("slug") or slugify(name)

    ingredients = data.get("recipeIngredient", [])
    if isinstance(ingredients, list):
        ingredients_json = json.dumps(ingredients)
    else:
        ingredients_json = "[]"

    tags = data.get("keywords", "")
    if isinstance(tags, list):
        tags_json = json.dumps(tags)
    elif isinstance(tags, str):
        tags_json = json.dumps([t.strip() for t in tags.split(",") if t.strip()])
    else:
        tags_json = "[]"

    # Parse duration strings (PT45M → "45 min")
    def parse_duration(val):
        if not val:
            return None
        val = str(val)
        if val.startswith("PT"):
            val = val[2:]
        return val.replace("H", "h ").replace("M", "min").strip()

    image = data.get("image", "")
    if isinstance(image, list):
        image = image[0] if image else ""

    yield_val = data.get("recipeYield", "")
    if isinstance(yield_val, list):
        yield_val = yield_val[0] if yield_val else ""
    import re as _re
    m = _re.search(r'\d+', str(yield_val))
    servings = int(m.group()) if m else None

    def _str_or_first(val):
        """Return a plain string whether val is a str, list, or None."""
        if isinstance(val, list):
            return val[0] if val else ""
        return val or ""

    return {
        "slug": slug,
        "name": name,
        "description": _str_or_first(data.get("description", "")),
        "json_path": str(path.relative_to(RECIPES_DIR.parent)),
        "image_url": image,
        "prep_time": parse_duration(data.get("prepTime")),
        "cook_time": parse_duration(data.get("cookTime")),
        "total_time": parse_duration(data.get("totalTime")),
        "servings": servings,
        "category": _str_or_first(data.get("recipeCategory", "")),
        "cuisine": _str_or_first(data.get("recipeCuisine", "")),
        "tags": tags_json,
        "ingredients": ingredients_json,
        "source_url": data.get("source_url") or data.get("url", ""),
        "source_type": data.get("source_type", "manual"),
        "status": data.get("status", "active"),
        "mealie_id": data.get("mealie_id"),
        "nostr_event_id": data.get("nostr_event_id"),
    }


def sync_all() -> dict:
    """Sync all JSON files in recipes/ to SQLite. Returns summary."""
    RECIPES_DIR.mkdir(exist_ok=True)
    json_files = list(RECIPES_DIR.glob("*.json"))

    synced, errors = 0, 0

    with db() as conn:
        for path in json_files:
            recipe = parse_recipe_json(path)
            if not recipe:
                errors += 1
                continue
            try:
                conn.execute("""
                    INSERT INTO recipes
                        (slug, name, description, json_path, image_url,
                         prep_time, cook_time, total_time, servings,
                         category, cuisine, tags, ingredients,
                         source_url, source_type, status, mealie_id, nostr_event_id)
                    VALUES
                        (:slug, :name, :description, :json_path, :image_url,
                         :prep_time, :cook_time, :total_time, :servings,
                         :category, :cuisine, :tags, :ingredients,
                         :source_url, :source_type, :status, :mealie_id, :nostr_event_id)
                    ON CONFLICT(slug) DO UPDATE SET
                        name=excluded.name,
                        description=excluded.description,
                        image_url=excluded.image_url,
                        prep_time=excluded.prep_time,
                        cook_time=excluded.cook_time,
                        total_time=excluded.total_time,
                        servings=excluded.servings,
                        category=excluded.category,
                        cuisine=excluded.cuisine,
                        tags=excluded.tags,
                        ingredients=excluded.ingredients,
                        source_url=excluded.source_url,
                        source_type=excluded.source_type,
                        status=excluded.status,
                        mealie_id=COALESCE(excluded.mealie_id, recipes.mealie_id),
                        nostr_event_id=COALESCE(excluded.nostr_event_id, recipes.nostr_event_id),
                        updated_at=datetime('now')
                """, recipe)
                synced += 1
            except Exception as e:
                print(f"Error syncing {path.name}: {e}")
                errors += 1

    return {"synced": synced, "errors": errors, "total": len(json_files)}


def save_recipe_json(recipe_data: dict, status: str = "staged") -> Path | None:
    """
    Save a recipe dict as JSON file and insert into SQLite.
    Returns None (and skips) if an active recipe with the same slug already exists.
    """
    RECIPES_DIR.mkdir(exist_ok=True)
    slug = recipe_data.get("slug") or slugify(recipe_data.get("name", "recipe"))
    recipe_data["slug"] = slug
    recipe_data["status"] = status

    # Never overwrite an active recipe during staging imports
    if status == "staged":
        with db() as conn:
            existing = conn.execute(
                "SELECT status FROM recipes WHERE slug=?", (slug,)
            ).fetchone()
            if existing and existing["status"] == "active":
                return None

    path = RECIPES_DIR / f"{slug}.json"
    with open(path, "w") as f:
        json.dump(recipe_data, f, indent=2, ensure_ascii=False)

    # Sync this single recipe to DB
    parsed = parse_recipe_json(path)
    if parsed:
        with db() as conn:
            conn.execute("""
                INSERT INTO recipes
                    (slug, name, description, json_path, image_url,
                     prep_time, cook_time, total_time, servings,
                     category, cuisine, tags, ingredients,
                     source_url, source_type, status, mealie_id, nostr_event_id)
                VALUES
                    (:slug, :name, :description, :json_path, :image_url,
                     :prep_time, :cook_time, :total_time, :servings,
                     :category, :cuisine, :tags, :ingredients,
                     :source_url, :source_type, :status, :mealie_id, :nostr_event_id)
                ON CONFLICT(slug) DO UPDATE SET
                    name=excluded.name,
                    prep_time=excluded.prep_time,
                    cook_time=excluded.cook_time,
                    total_time=excluded.total_time,
                    servings=excluded.servings,
                    category=excluded.category,
                    cuisine=excluded.cuisine,
                    status=excluded.status,
                    mealie_id=COALESCE(excluded.mealie_id, recipes.mealie_id),
                    nostr_event_id=COALESCE(excluded.nostr_event_id, recipes.nostr_event_id),
                    updated_at=datetime('now')
            """, parsed)
    return path


def restore_recipe(slug: str) -> bool:
    """Restore a trashed recipe back to active, rebuilding JSON from DB if missing."""
    with db() as conn:
        row = conn.execute("SELECT * FROM recipes WHERE slug=? AND status='trashed'", (slug,)).fetchone()
        if not row:
            return False

        r = dict(row)
        json_path = Path(__file__).parent.parent / r["json_path"]

        if not json_path.exists():
            # Rebuild JSON from DB metadata (instructions will be empty)
            recipe = {
                "@context": "https://schema.org",
                "@type": "Recipe",
                "name": r["name"],
                "slug": slug,
                "description": r["description"] or "",
                "recipeYield": f"{r['servings']} servings" if r["servings"] else "",
                "recipeCategory": r["category"] or "",
                "recipeCuisine": r["cuisine"] or "",
                "keywords": ", ".join(json.loads(r["tags"] or "[]")),
                "recipeIngredient": json.loads(r["ingredients"] or "[]"),
                "recipeInstructions": [],
                "source_url": r["source_url"] or "",
                "source_type": r["source_type"] or "manual",
                "status": "active",
            }
            if r["image_url"]:
                recipe["image"] = r["image_url"]
            RECIPES_DIR.mkdir(exist_ok=True)
            with open(json_path, "w") as f:
                json.dump(recipe, f, indent=2, ensure_ascii=False)
        else:
            with open(json_path) as f:
                data = json.load(f)
            data["status"] = "active"
            with open(json_path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        conn.execute(
            "UPDATE recipes SET status='active', updated_at=datetime('now') WHERE slug=?",
            (slug,)
        )
        return True


def update_recipe(slug: str, data: dict) -> dict | None:
    """Apply edits to a recipe JSON file and re-sync to DB. Returns updated recipe or None."""
    with db() as conn:
        row = conn.execute("SELECT json_path FROM recipes WHERE slug=?", (slug,)).fetchone()
    if not row:
        return None

    path = Path(__file__).parent.parent / row["json_path"]
    existing = {}
    if path.exists():
        with open(path) as f:
            existing = json.load(f)

    # Apply only the provided fields — preserve slug, source_type, status, etc.
    existing.update(data)

    with open(path, "w") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    parsed = parse_recipe_json(path)
    if parsed:
        with db() as conn:
            conn.execute("""
                UPDATE recipes SET
                    name=:name, description=:description, image_url=:image_url,
                    prep_time=:prep_time, cook_time=:cook_time, total_time=:total_time,
                    servings=:servings, category=:category, cuisine=:cuisine,
                    tags=:tags, ingredients=:ingredients, updated_at=datetime('now')
                WHERE slug=:slug
            """, {**parsed, 'slug': slug})

    return get_recipe(slug)


def get_recipe(slug: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM recipes WHERE slug=?", (slug,)).fetchone()
        if not row:
            return None
        r = row_to_dict(row)
        # Load full JSON from file for complete data
        json_path = Path(__file__).parent.parent / r["json_path"]
        if json_path.exists():
            with open(json_path) as f:
                full = json.load(f)
            r["full"] = full
        return r


def list_recipes(status: str = "active", page: int = 1, per_page: int = 24) -> dict:
    offset = (page - 1) * per_page
    with db() as conn:
        if status == "favorited":
            total = conn.execute(
                "SELECT COUNT(*) FROM recipes WHERE status='active' AND favorited=1"
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM recipes WHERE status='active' AND favorited=1 ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (per_page, offset)
            ).fetchall()
        else:
            total = conn.execute(
                "SELECT COUNT(*) FROM recipes WHERE status=?", (status,)
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM recipes WHERE status=? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (status, per_page, offset)
            ).fetchall()
    return {
        "recipes": rows_to_list(rows),
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page
    }


def toggle_favorite(slug: str) -> dict:
    """Toggle the favorited flag on an active recipe. Returns {favorited: bool}."""
    with db() as conn:
        row = conn.execute(
            "SELECT favorited FROM recipes WHERE slug=? AND status='active'", (slug,)
        ).fetchone()
        if not row:
            return None
        new_val = 0 if row["favorited"] else 1
        conn.execute(
            "UPDATE recipes SET favorited=? WHERE slug=?", (new_val, slug)
        )
    return {"favorited": bool(new_val)}


def approve_recipe(slug: str) -> bool:
    """Move staged recipe to active."""
    with db() as conn:
        cur = conn.execute(
            "UPDATE recipes SET status='active', updated_at=datetime('now') WHERE slug=? AND status='staged'",
            (slug,)
        )
        # Also update JSON file
        row = conn.execute("SELECT json_path FROM recipes WHERE slug=?", (slug,)).fetchone()
        if row:
            path = Path(__file__).parent.parent / row["json_path"]
            if path.exists():
                with open(path) as f:
                    data = json.load(f)
                data["status"] = "active"
                with open(path, "w") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        return cur.rowcount > 0


def permanent_delete_recipe(slug: str) -> bool:
    """Permanently delete a trashed recipe — removes DB row, JSON file, and image."""
    with db() as conn:
        row = conn.execute(
            "SELECT json_path, image_url FROM recipes WHERE slug=? AND status='trashed'", (slug,)
        ).fetchone()
        if not row:
            return False

        base = Path(__file__).parent.parent

        # Delete JSON file
        json_path = base / row["json_path"]
        if json_path.exists():
            json_path.unlink()

        # Delete image (local path only)
        if row["image_url"] and not row["image_url"].startswith("http"):
            img_path = base / row["image_url"]
            if img_path.exists():
                img_path.unlink()
        # Also try slug-based image names
        for ext in ("jpg", "png", "webp"):
            img_path = base / "images" / f"{slug}.{ext}"
            if img_path.exists():
                img_path.unlink()

        cur = conn.execute("DELETE FROM recipes WHERE slug=?", (slug,))
        return cur.rowcount > 0


def trash_recipe(slug: str) -> bool:
    with db() as conn:
        row = conn.execute(
            "SELECT json_path, image_url, status FROM recipes WHERE slug=?", (slug,)
        ).fetchone()
        if not row:
            return False

        if row["status"] == "staged":
            # Hard-delete staged recipes (never approved, safe to remove)
            json_path = Path(__file__).parent.parent / row["json_path"]
            if json_path.exists():
                json_path.unlink()

            base = Path(__file__).parent.parent
            for img_path in {
                base / "images" / f"{slug}.jpg",
                base / "images" / f"{slug}.png",
                base / "images" / f"{slug}.webp",
                *([base / (row["image_url"])] if row["image_url"] and not row["image_url"].startswith("http") else []),
            }:
                if img_path.exists():
                    img_path.unlink()

            cur = conn.execute("DELETE FROM recipes WHERE slug=?", (slug,))
        else:
            # Soft-delete active recipes — keep files, just mark trashed
            cur = conn.execute(
                "UPDATE recipes SET status='trashed', updated_at=datetime('now') WHERE slug=?",
                (slug,)
            )
            json_path = Path(__file__).parent.parent / row["json_path"]
            if json_path.exists():
                with open(json_path) as f:
                    data = json.load(f)
                data["status"] = "trashed"
                with open(json_path, "w") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

        return cur.rowcount > 0
