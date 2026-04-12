"""
modules/meal_planner.py — Assign recipes to meal plan + aggregate ingredients
"""
import json
import re
from core.db import db, rows_to_list, row_to_dict

# Unit conversion tables — base units are grams (mass) and ml (volume)
_TO_GRAMS = {'mg': 0.001, 'g': 1, 'kg': 1000, 'oz': 28.35, 'lb': 453.59, 'lbs': 453.59}
_TO_ML    = {
    'ml': 1, 'cl': 10, 'dl': 100, 'l': 1000,
    'tsp': 4.93, 'teaspoon': 4.93, 'teaspoons': 4.93,
    'tbsp': 14.79, 'tablespoon': 14.79, 'tablespoons': 14.79,
    'cup': 240, 'cups': 240,
    'pt': 473, 'pint': 473,
    'qt': 946, 'quart': 946,
    'gal': 3785, 'gallon': 3785,
}


def _to_base(qty: float, unit: str) -> tuple[float, str]:
    """
    Convert (qty, unit) to a canonical base unit for comparison.
    Mass → grams, Volume → ml. Unknown units returned unchanged.
    """
    u = (unit or '').lower().strip()
    if u in _TO_GRAMS:
        return round(qty * _TO_GRAMS[u], 4), 'g'
    if u in _TO_ML:
        return round(qty * _TO_ML[u], 4), 'ml'
    return qty, unit


# Known units for ingredient parsing
_UNITS = {
    'g', 'kg', 'mg',
    'ml', 'l', 'dl', 'cl',
    'oz', 'lb', 'lbs',
    'tsp', 'tbsp', 'teaspoon', 'teaspoons', 'tablespoon', 'tablespoons',
    'cup', 'cups',
    'pt', 'qt', 'pint', 'quart', 'gallon', 'gal',
    'pinch', 'dash', 'handful',
    'slice', 'slices', 'piece', 'pieces',
    'clove', 'cloves', 'can', 'cans',
    'package', 'packages', 'pack', 'packs',
    'bunch', 'bunches', 'sprig', 'sprigs',
    'stalk', 'stalks', 'head', 'heads',
    'large', 'medium', 'small',
}


def _parse_quantity(qty_str: str) -> float | None:
    """Parse '1', '1/2', '1 1/2', '0.5' into a float."""
    qty_str = qty_str.strip()
    try:
        if ' ' in qty_str:          # mixed number: "1 1/2"
            whole, frac = qty_str.split(None, 1)
            num, den = frac.split('/')
            return float(whole) + float(num) / float(den)
        elif '/' in qty_str:        # simple fraction: "1/2"
            num, den = qty_str.split('/')
            return float(num) / float(den)
        else:
            return float(qty_str)
    except (ValueError, ZeroDivisionError):
        return None


def parse_ingredient(text: str) -> dict:
    """
    Parse a raw ingredient string into {name, quantity, unit}.
    Examples:
      "200g pasta"        → name="pasta",       qty=200,  unit="g"
      "2 cups flour"      → name="flour",        qty=2,    unit="cups"
      "3 eggs"            → name="eggs",         qty=3,    unit=None
      "1/2 tsp salt"      → name="salt",         qty=0.5,  unit="tsp"
      "salt to taste"     → name="salt to taste",qty=None, unit=None
    """
    text = text.strip()
    # Normalise unicode fractions
    for uni, rep in [('½','1/2'),('¼','1/4'),('¾','3/4'),('⅓','1/3'),('⅔','2/3')]:
        text = text.replace(uni, rep)

    # Match optional leading number (integer / fraction / mixed / decimal)
    num_re = r'^(\d+(?:\s+\d+/\d+|\.\d+|/\d+)?)\s*'
    m = re.match(num_re, text)
    if not m:
        return {'name': text, 'quantity': None, 'unit': None}

    quantity = _parse_quantity(m.group(1))
    remainder = text[m.end():].strip()

    unit = None
    name = remainder or text
    if remainder:
        words = remainder.split(None, 1)
        first = words[0].lower().rstrip('.')
        if first in _UNITS:
            unit = words[0]
            name = words[1].strip() if len(words) > 1 else ''
        if not name:
            name = text  # fallback to full string

    return {'name': name, 'quantity': quantity, 'unit': unit}


def get_week(start_date: str) -> list:
    """Get all meal plan entries for a 7-day window starting at start_date."""
    with db() as conn:
        rows = conn.execute("""
            SELECT mp.*, r.name as recipe_name, r.image_url, r.cook_time, r.servings as recipe_servings
            FROM meal_plan mp
            JOIN recipes r ON r.slug = mp.recipe_slug
            WHERE mp.date >= ? AND mp.date < date(?, '+7 days')
            ORDER BY mp.date, mp.meal_type
        """, (start_date, start_date)).fetchall()
    return rows_to_list(rows)


def add_to_plan(date: str, meal_type: str, recipe_slug: str, servings: int = 1) -> dict:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO meal_plan (date, meal_type, recipe_slug, servings) VALUES (?,?,?,?)",
            (date, meal_type, recipe_slug, servings)
        )
        row = conn.execute("SELECT * FROM meal_plan WHERE id=?", (cur.lastrowid,)).fetchone()
    return row_to_dict(row)


def remove_from_plan(plan_id: int) -> bool:
    with db() as conn:
        cur = conn.execute("DELETE FROM meal_plan WHERE id=?", (plan_id,))
    return cur.rowcount > 0


def get_aggregate_ingredients(start_date: str, end_date: str) -> list[dict]:
    """
    Get all ingredients needed for planned meals in date range.
    Parses raw ingredient strings into {food, quantity, unit} and sums
    quantities when the same ingredient appears across multiple recipes.
    Returns list of {food, quantity, unit, raw}.
    """
    with db() as conn:
        rows = conn.execute("""
            SELECT mp.servings, r.ingredients, r.servings as base_servings
            FROM meal_plan mp
            JOIN recipes r ON r.slug = mp.recipe_slug
            WHERE mp.date >= ? AND mp.date <= ?
        """, (start_date, end_date)).fetchall()

    # aggregated[name_key] = {food, quantity, unit, raw}
    aggregated = {}
    for row in rows:
        ingredients = json.loads(row["ingredients"] or "[]")
        scale = (row["servings"] or 1) / max(row["base_servings"] or 1, 1)

        for raw in ingredients:
            if not raw or not raw.strip():
                continue
            parsed = parse_ingredient(raw.strip())
            name_key = parsed['name'].lower().strip()
            if not name_key:
                continue

            qty = (parsed['quantity'] * scale) if parsed['quantity'] is not None else None

            # Normalise to base unit before storing/summing
            if qty is not None:
                qty, unit = _to_base(qty, parsed['unit'])
            else:
                unit = parsed['unit']

            if name_key not in aggregated:
                aggregated[name_key] = {
                    'food':     parsed['name'],
                    'quantity': qty,
                    'unit':     unit,
                    'raw':      raw.strip(),
                }
            else:
                existing = aggregated[name_key]
                if qty is not None and existing['quantity'] is not None:
                    ex_qty, ex_unit = _to_base(existing['quantity'], existing['unit'])
                    if ex_unit == unit:
                        existing['quantity'] = round(ex_qty + qty, 3)
                        existing['unit'] = unit
                elif qty is not None and existing['quantity'] is None:
                    existing['quantity'] = qty
                    existing['unit'] = unit

    return list(aggregated.values())
