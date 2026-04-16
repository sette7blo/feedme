"""
modules/cook_log.py — Cook history per recipe
"""
from core.db import db, rows_to_list, row_to_dict


def add_entry(slug: str, servings: int = None, notes: str = None) -> dict:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO cook_log (recipe_slug, servings, notes) VALUES (?,?,?)",
            (slug, servings, notes)
        )
        row = conn.execute("SELECT * FROM cook_log WHERE id=?", (cur.lastrowid,)).fetchone()
    return row_to_dict(row)


def get_history(slug: str, limit: int = 10) -> list:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM cook_log WHERE recipe_slug=? ORDER BY cooked_at DESC LIMIT ?",
            (slug, limit)
        ).fetchall()
    return rows_to_list(rows)


def get_last_cooked(slugs: list) -> dict:
    """Returns {slug: last_cooked_iso} for all slugs that have cook log entries."""
    if not slugs:
        return {}
    with db() as conn:
        ph = ','.join('?' * len(slugs))
        rows = conn.execute(
            f"SELECT recipe_slug, MAX(cooked_at) as last_cooked FROM cook_log WHERE recipe_slug IN ({ph}) GROUP BY recipe_slug",
            slugs
        ).fetchall()
    return {r['recipe_slug']: r['last_cooked'] for r in rows}
