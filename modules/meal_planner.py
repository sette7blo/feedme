"""
modules/meal_planner.py — Assign recipes to meal plan + aggregate ingredients
"""
import json
import re
from core.db import db, rows_to_list, row_to_dict

# ── Unit conversion ──────────────────────────────────────────────────────────
# Single base: mass → grams, volume → ml. All summing happens in base units.
# Display conversion picks the best human-friendly unit based on magnitude
# and the user's preferred system (metric / imperial / auto).

_TO_GRAMS = {'mg': 0.001, 'g': 1, 'kg': 1000, 'lb': 453.59, 'lbs': 453.59, 'pound': 453.59, 'pounds': 453.59}
_TO_ML    = {
    'ml': 1, 'cl': 10, 'dl': 100, 'l': 1000,
    'oz': 29.57, 'ounce': 29.57, 'ounces': 29.57,
    'fl': 29.57,
    'tsp': 4.93, 'teaspoon': 4.93, 'teaspoons': 4.93,
    'tbsp': 14.79, 'tablespoon': 14.79, 'tablespoons': 14.79,
    'cup': 240, 'cups': 240,
    'pt': 473, 'pint': 473,
    'qt': 946, 'quart': 946,
    'gal': 3785, 'gallon': 3785,
}


def _to_base(qty: float, unit: str) -> tuple[float, str]:
    """Convert any known unit to base (g or ml). Unknown units pass through."""
    u = (unit or '').lower().strip()
    if u in _TO_GRAMS:
        return round(qty * _TO_GRAMS[u], 4), 'g'
    if u in _TO_ML:
        return round(qty * _TO_ML[u], 4), 'ml'
    return qty, unit


_OZ_UNITS = {'oz', 'ounce', 'ounces', 'fl'}
_CUP_UNITS = {'cup', 'cups'}


def _display(qty: float, unit: str, system: str = '', orig_unit: str = '') -> tuple[float, str]:
    """
    Convert base units (g/ml) to the best human-friendly display unit.
    system: 'metric', 'imperial', or '' (auto — picks the most natural).
    orig_unit: the original recipe unit, used as a hint to prefer oz vs cups.
    """
    _LB_UNITS = {'lb', 'lbs', 'pound', 'pounds'}
    if unit == 'g':
        orig_low = orig_unit.lower().rstrip('.') if orig_unit else ''
        prefer_lb = orig_low in _LB_UNITS
        if system == 'imperial' or prefer_lb:
            lb = qty / 453.59
            if lb >= 1:
                return round(lb, 2), 'lb'
            return round(lb * 16, 1), 'oz'
        # metric / auto
        if qty >= 1000:
            return round(qty / 1000, 2), 'kg'
        return round(qty, 1), 'g'

    if unit == 'ml':
        if system == 'imperial':
            fl_oz = qty / 29.57
            if fl_oz >= 32:
                return round(fl_oz / 32, 2), 'qt'
            if fl_oz >= 8:
                return round(fl_oz, 1), 'oz'
            if fl_oz >= 1:
                return round(fl_oz, 1), 'oz'
            tbsp = qty / 14.79
            if tbsp >= 1:
                return round(tbsp, 1), 'tbsp'
            return round(qty / 4.93, 1), 'tsp'
        # metric / auto
        if qty >= 1000:
            return round(qty / 1000, 2), 'L'
        if system == 'metric':
            return round(qty, 1), 'ml'
        # auto: respect original unit family, then pick most natural
        orig_low = orig_unit.lower().rstrip('.') if orig_unit else ''
        prefer_oz = orig_low in _OZ_UNITS
        prefer_cups = orig_low in _CUP_UNITS
        cups = qty / 240
        fl_oz = qty / 29.57
        if cups >= 4:
            return round(cups / 4, 2), 'qt'
        if prefer_oz and fl_oz >= 1:
            return round(fl_oz, 1), 'oz'
        if prefer_cups and cups > 0:
            return round(cups, 2), 'cups'
        if cups >= 0.5:
            return round(cups, 2), 'cups'
        if fl_oz >= 1:
            return round(fl_oz, 1), 'oz'
        tbsp = qty / 14.79
        if tbsp >= 1:
            return round(tbsp, 1), 'tbsp'
        if qty > 10:
            return round(qty, 1), 'ml'
        return round(qty / 4.93, 1), 'tsp'

    return qty, unit


# ── Ingredient parsing ───────────────────────────────────────────────────────

_UNITS = {
    'g', 'kg', 'mg',
    'ml', 'l', 'dl', 'cl',
    'oz', 'ounce', 'ounces', 'lb', 'lbs', 'pound', 'pounds',
    'tsp', 'tbsp', 'teaspoon', 'teaspoons', 'tablespoon', 'tablespoons',
    'cup', 'cups',
    'pt', 'qt', 'pint', 'quart', 'gallon', 'gal',
    'pinch', 'dash', 'handful',
    'slice', 'slices', 'piece', 'pieces',
    'clove', 'cloves', 'can', 'cans',
    'package', 'packages', 'pack', 'packs',
    'bunch', 'bunches', 'sprig', 'sprigs',
    'stalk', 'stalks', 'head', 'heads',
    'jar', 'jars', 'bottle', 'bottles',
    'large', 'medium', 'small',
}


def _parse_quantity(qty_str: str) -> float | None:
    """Parse '1', '1/2', '1 1/2', '0.5' into a float."""
    qty_str = qty_str.strip()
    try:
        if ' ' in qty_str:
            whole, frac = qty_str.split(None, 1)
            num, den = frac.split('/')
            return float(whole) + float(num) / float(den)
        elif '/' in qty_str:
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
      "200g pasta"        -> name="pasta",       qty=200,  unit="g"
      "2 cups flour"      -> name="flour",        qty=2,    unit="cups"
      "3 eggs"            -> name="eggs",         qty=3,    unit=None
      "1/2 tsp salt"      -> name="salt",         qty=0.5,  unit="tsp"
      "salt to taste"     -> name="salt to taste",qty=None, unit=None
    """
    text = text.strip()
    for uni, rep in [('\u00bd','1/2'),('\u00bc','1/4'),('\u00be','3/4'),('\u2153','1/3'),('\u2154','2/3')]:
        text = re.sub(r'(\d)' + re.escape(uni), r'\1 ' + rep, text)
        text = text.replace(uni, rep)

    num_re = r'^(\d+(?:\s+\d+/\d+|\.\d+|/\d+)?)\s*'
    m = re.match(num_re, text)
    if not m:
        return {'name': text, 'quantity': None, 'unit': None}

    quantity = _parse_quantity(m.group(1))
    remainder = text[m.end():].strip()

    # Handle parenthetical size: "1 (24 ounce) jar marinara sauce"
    # When inner measurement exists, prefer it over the container count
    paren_re = r'^\((\d+(?:\.\d+|/\d+)?)\s*([a-zA-Z.]+)\)\s*'
    pm = re.match(paren_re, remainder)
    if pm:
        inner_qty = _parse_quantity(pm.group(1))
        inner_unit_raw = pm.group(2).lower().rstrip('.')
        if inner_unit_raw in _UNITS and (inner_unit_raw in _TO_GRAMS or inner_unit_raw in _TO_ML):
            # Use the precise measurement instead of container count
            quantity = (quantity or 1) * (inner_qty or 1)
            remainder = remainder[pm.end():].strip()
            # Skip the container word (jar, can, etc.)
            words = remainder.split(None, 1)
            if words and words[0].lower().rstrip('.') in _UNITS:
                remainder = words[1].strip() if len(words) > 1 else ''
            return {
                'name': remainder or text,
                'quantity': quantity,
                'unit': pm.group(2),
            }

    unit = None
    name = remainder or text
    if remainder:
        words = remainder.split(None, 1)
        first = words[0].lower().rstrip('.')
        if first in _UNITS:
            unit = words[0]
            name = words[1].strip() if len(words) > 1 else ''
        if not name:
            name = text

    return {'name': name, 'quantity': quantity, 'unit': unit}


# ── Fuzzy ingredient dedup ───────────────────────────────────────────────────

_MODIFIERS = frozenset({
    'fresh', 'dried', 'frozen', 'canned', 'cooked', 'raw', 'whole',
    'chopped', 'sliced', 'diced', 'minced', 'ground', 'grated', 'shredded',
    'peeled', 'pitted', 'rinsed', 'drained', 'softened', 'melted', 'crushed',
    'boneless', 'skinless', 'lean',
    'large', 'medium', 'small', 'extra', 'big',
    'organic', 'unsalted', 'salted', 'sweetened', 'unsweetened',
    'low', 'high', 'reduced', 'full', 'fat', 'free',
    'packed', 'heaping', 'level', 'plain', 'regular',
})


def _core(text: str) -> str:
    """Strip modifier words and normalise plurals for dedup keying."""
    words = re.sub(r'[^a-z\s]', '', text.lower()).split()
    result = []
    for w in words:
        if w in _MODIFIERS:
            continue
        if len(w) > 4 and w.endswith('ies'):
            w = w[:-3] + 'y'
        elif len(w) > 3 and w.endswith('s'):
            w = w[:-1]
        result.append(w)
    return ' '.join(result)


# ── Meal plan CRUD ───────────────────────────────────────────────────────────

def get_week(start_date: str) -> list:
    with db() as conn:
        rows = conn.execute("""
            SELECT mp.*, r.name as recipe_name, r.image_url, r.cook_time, r.servings as recipe_servings
            FROM meal_plan mp
            JOIN recipes r ON r.slug = mp.recipe_slug
            WHERE mp.date >= ? AND mp.date < date(?, '+7 days')
            ORDER BY mp.date, mp.meal_type
        """, (start_date, start_date)).fetchall()
    return rows_to_list(rows)


def add_to_plan(date: str, meal_type: str, recipe_slug: str, servings: int = None) -> dict:
    with db() as conn:
        if servings is None:
            row = conn.execute("SELECT servings FROM recipes WHERE slug=?", (recipe_slug,)).fetchone()
            servings = (row["servings"] if row and row["servings"] else 1)
        cur = conn.execute(
            "INSERT INTO meal_plan (date, meal_type, recipe_slug, servings) VALUES (?,?,?,?)",
            (date, meal_type, recipe_slug, servings)
        )
        row = conn.execute("""
            SELECT mp.*, r.name as recipe_name, r.image_url, r.cook_time, r.servings as recipe_servings
            FROM meal_plan mp JOIN recipes r ON r.slug = mp.recipe_slug
            WHERE mp.id=?
        """, (cur.lastrowid,)).fetchone()
    return row_to_dict(row)


def update_plan_servings(plan_id: int, servings: int) -> dict | None:
    with db() as conn:
        conn.execute("UPDATE meal_plan SET servings=? WHERE id=?", (servings, plan_id))
        row = conn.execute("""
            SELECT mp.*, r.name as recipe_name, r.image_url, r.cook_time, r.servings as recipe_servings
            FROM meal_plan mp JOIN recipes r ON r.slug = mp.recipe_slug
            WHERE mp.id=?
        """, (plan_id,)).fetchone()
    return row_to_dict(row) if row else None


def remove_from_plan(plan_id: int) -> bool:
    with db() as conn:
        cur = conn.execute("DELETE FROM meal_plan WHERE id=?", (plan_id,))
    return cur.rowcount > 0


# ── Ingredient aggregation ───────────────────────────────────────────────────

def get_aggregate_ingredients(start_date: str, end_date: str) -> list[dict]:
    """
    Aggregate ingredients across planned meals in a date range.
    All quantities normalised to base units (g / ml) for summing,
    then converted back to friendly display units at the end.
    Returns list of {food, quantity, unit, raw}.
    """
    with db() as conn:
        rows = conn.execute("""
            SELECT mp.servings, r.ingredients, r.servings as base_servings,
                   r.name as recipe_name, r.slug as recipe_slug
            FROM meal_plan mp
            JOIN recipes r ON r.slug = mp.recipe_slug
            WHERE mp.date >= ? AND mp.date <= ?
        """, (start_date, end_date)).fetchall()

    aggregated = {}
    for row in rows:
        ingredients = json.loads(row["ingredients"] or "[]")
        scale = (row["servings"] or 1) / max(row["base_servings"] or 1, 1)
        recipe_ref = {'name': row['recipe_name'], 'slug': row['recipe_slug']}

        for raw in ingredients:
            if not raw or not raw.strip():
                continue
            parsed = parse_ingredient(raw.strip())
            name_key = _core(parsed['name']) or parsed['name'].lower().strip()
            if not name_key:
                continue

            qty = (parsed['quantity'] * scale) if parsed['quantity'] is not None else None

            if qty is not None and parsed['unit']:
                base_qty, base_unit = _to_base(qty, parsed['unit'])
            else:
                base_qty, base_unit = qty, parsed['unit']

            if name_key not in aggregated:
                aggregated[name_key] = {
                    'food':     parsed['name'],
                    'quantity': base_qty,
                    'unit':     base_unit,
                    'orig_unit': parsed['unit'] or '',
                    'raw':      raw.strip(),
                    'recipes':  [recipe_ref],
                }
            else:
                existing = aggregated[name_key]
                if recipe_ref not in existing['recipes']:
                    existing['recipes'].append(recipe_ref)
                if base_qty is not None and existing['quantity'] is not None:
                    if existing['unit'] == base_unit:
                        existing['quantity'] = round(existing['quantity'] + base_qty, 3)
                    else:
                        ex_qty, ex_unit = _to_base(existing['quantity'], existing['unit'])
                        if ex_unit == base_unit:
                            existing['quantity'] = round(ex_qty + base_qty, 3)
                            existing['unit'] = base_unit
                elif base_qty is not None and existing['quantity'] is None:
                    existing['quantity'] = base_qty
                    existing['unit'] = base_unit

    # Convert base units to friendly display, preserving orig_unit for downstream
    result = []
    for item in aggregated.values():
        if item['quantity'] is not None and item['unit'] in ('g', 'ml'):
            item['quantity'], item['unit'] = _display(
                item['quantity'], item['unit'], orig_unit=item.get('orig_unit', ''))
        result.append(item)

    return result
