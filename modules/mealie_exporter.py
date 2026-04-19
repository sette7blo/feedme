"""
modules/mealie_exporter.py — Export recipes to a Mealie instance
Browses local Feedme recipes with Mealie sync status,
pushes selected recipes via Mealie REST API.
"""
import json
import urllib.request
import urllib.error
from pathlib import Path

from core.db import db, rows_to_list

IMAGES_DIR = Path(__file__).parent.parent / "images"


def _headers(token: str, content_type: str = "application/json") -> dict:
    h = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if content_type:
        h["Content-Type"] = content_type
    return h


def _get(base_url: str, token: str, path: str) -> dict | None:
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(url, headers=_headers(token))
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        if exc.code == 401:
            raise ValueError("Invalid Mealie token.") from exc
        raise ValueError(f"Mealie HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Could not reach Mealie: {exc.reason}") from exc


def _post(base_url: str, token: str, path: str, payload: dict) -> dict:
    url = base_url.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_headers(token), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code == 401:
            raise ValueError("Invalid Mealie token.") from exc
        raise ValueError(f"Mealie HTTP {exc.code}: {body[:200]}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Could not reach Mealie: {exc.reason}") from exc


def _patch(base_url: str, token: str, path: str, payload: dict) -> dict:
    url = base_url.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_headers(token), method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"Mealie HTTP {exc.code}: {body[:200]}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Could not reach Mealie: {exc.reason}") from exc


def _upload_image(base_url: str, token: str, mealie_slug: str, image_path: Path):
    """Upload recipe image to Mealie."""
    if not image_path.exists():
        return
    url = base_url.rstrip("/") + f"/api/recipes/{mealie_slug}/image"
    boundary = "----FeedmeUpload"
    filename = image_path.name
    ct_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
              ".webp": "image/webp", ".gif": "image/gif"}
    content_type = ct_map.get(image_path.suffix.lower(), "application/octet-stream")

    img_data = image_path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8") + img_data + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(url, data=body, method="PUT")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req, timeout=20):
            pass
    except Exception:
        pass  # image upload is best-effort


def browse_for_export(page: int = 1, per_page: int = 50) -> dict:
    """
    Return a page of active Feedme recipes with mealie_id status.
    """
    offset = (page - 1) * per_page
    with db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM recipes WHERE status='active'"
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT slug, name, image_url, category, cuisine, cook_time, servings, mealie_id "
            "FROM recipes WHERE status='active' ORDER BY name COLLATE NOCASE "
            "LIMIT ? OFFSET ?",
            (per_page, offset)
        ).fetchall()

    items = []
    for r in rows:
        items.append({
            "slug": r["slug"],
            "name": r["name"],
            "image": r["image_url"] or "",
            "category": r["category"] or "",
            "cook_time": r["cook_time"] or "",
            "servings": r["servings"],
            "already_exported": bool(r["mealie_id"]),
        })

    pages = max(1, -(-total // per_page))
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


def _parse_servings(val) -> str:
    if not val:
        return ""
    s = str(val)
    if s.isdigit():
        return f"{s} servings"
    return s


def export_recipes(base_url: str, token: str, slugs: list[str]) -> dict:
    """
    Push selected Feedme recipes to Mealie.
    Returns { exported: [...], skipped: [...], errors: [...] }
    """
    exported, skipped, errors = [], [], []

    with db() as conn:
        for slug in slugs:
            row = conn.execute(
                "SELECT * FROM recipes WHERE slug=? AND status='active'", (slug,)
            ).fetchone()
            if not row:
                errors.append({"slug": slug, "error": "Recipe not found"})
                continue

            name = row["name"]
            ingredients = json.loads(row["ingredients"] or "[]")

            # Build Mealie-compatible recipe payload
            # Mealie's create endpoint only needs the URL, then we update with full data
            try:
                # Step 1: Create recipe stub in Mealie, or find existing
                mealie_slug = None
                try:
                    create_resp = _post(base_url, token, "/api/recipes", {"name": name})
                    mealie_slug = create_resp  # Mealie returns the slug as a string
                except ValueError as ce:
                    if "already exists" in str(ce):
                        # Recipe exists — find it by slug lookup
                        existing = _get(base_url, token, f"/api/recipes/{slug}")
                        if existing:
                            mealie_slug = existing.get("slug", slug)
                        else:
                            # Slug mismatch — skip as already exists
                            skipped.append(name)
                            continue
                    else:
                        raise

                # Step 2: Read the JSON file for full recipe data
                json_path = Path(row["json_path"])
                if json_path.exists():
                    recipe_data = json.loads(json_path.read_text("utf-8"))
                else:
                    recipe_data = {}

                instructions = recipe_data.get("recipeInstructions", [])
                mealie_instructions = []
                for i, step in enumerate(instructions):
                    text = step.get("text", step) if isinstance(step, dict) else str(step)
                    mealie_instructions.append({"text": text})

                # Step 3: Update with full data
                # Note: recipeInstructions and recipeCategory are excluded —
                # Mealie's PATCH rejects them (500 / 400 respectively)
                update_payload = {
                    "name": name,
                    "description": row["description"] or "",
                    "prepTime": recipe_data.get("prepTime", row["prep_time"] or ""),
                    "cookTime": recipe_data.get("cookTime", row["cook_time"] or ""),
                    "totalTime": recipe_data.get("totalTime", row["total_time"] or ""),
                    "recipeYield": _parse_servings(row["servings"]),
                    "recipeIngredient": [{"note": ing} for ing in ingredients],
                    "nutrition": recipe_data.get("nutrition", {}),
                }

                _patch(base_url, token, f"/api/recipes/{mealie_slug}", update_payload)

                # Step 4: Upload image if available
                image_rel = row["image_url"] or recipe_data.get("image", "")
                if image_rel:
                    img_path = Path(__file__).parent.parent / image_rel
                    _upload_image(base_url, token, mealie_slug, img_path)

                # Step 5: Store mealie_id locally
                conn.execute(
                    "UPDATE recipes SET mealie_id=? WHERE slug=?",
                    (mealie_slug, slug)
                )

                exported.append(name)

            except ValueError as exc:
                errors.append({"slug": slug, "error": str(exc)})
            except Exception as exc:
                errors.append({"slug": slug, "error": str(exc)})

    return {"exported": exported, "skipped": skipped, "errors": errors}
