"""
modules/grocery.py — Pantry diff → shopping list generation
"""
import re
from core.db import db, rows_to_list, row_to_dict
from modules.meal_planner import get_aggregate_ingredients, _to_base
from modules.pantry import list_pantry

# Words that describe how an ingredient is prepared or sized, not what it is.
# Stripped before matching so "large eggs" matches pantry "eggs", etc.
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
    """
    Strip modifier words and normalise plurals from an ingredient name.
    "large boneless chicken breasts" → "chicken breast"
    "fresh eggs" → "egg"
    """
    words = re.sub(r'[^a-z\s]', '', text.lower()).split()
    result = []
    for w in words:
        if w in _MODIFIERS:
            continue
        # Simple plural normalisation
        if len(w) > 4 and w.endswith('ies'):
            w = w[:-3] + 'y'        # berries → berry
        elif len(w) > 3 and w.endswith('s'):
            w = w[:-1]              # eggs → egg, carrots → carrot
        result.append(w)
    return ' '.join(result)


def _find_pantry_match(food_key: str, pantry_map: dict):
    """
    Find the best pantry match for a needed ingredient using progressive fuzzy logic.

    Pass order:
    1. Exact match on original name
    2. Exact match after stripping modifiers from the recipe side
       ("large eggs" → "egg" matches pantry "egg")
    3. Substring on originals — covers partial names ("chicken" ↔ "chicken breast")
    4. Substring after stripping both sides
       ("boneless chicken breast" → "chicken breast" ↔ pantry "chicken breast")
    """
    # 1. Exact
    if food_key in pantry_map:
        return pantry_map[food_key]

    stripped_need = _core(food_key)

    # 2. Stripped recipe vs original pantry
    if stripped_need in pantry_map:
        return pantry_map[stripped_need]

    # 3. Substring on originals
    for pk, p in pantry_map.items():
        if pk in food_key or food_key in pk:
            return p

    # 4. Substring after stripping both sides
    if stripped_need:
        for pk, p in pantry_map.items():
            stripped_pk = _core(pk)
            if not stripped_pk:
                continue
            if stripped_pk == stripped_need:
                return p
            if stripped_pk in stripped_need or stripped_need in stripped_pk:
                return p

    return None


def generate_shopping_list(start_date: str, end_date: str, list_date: str = None) -> dict:
    """
    Compare meal plan ingredients vs pantry → insert into shopping_list.
    - covered=0 items: need to buy
    - covered=1 items: already in pantry (shown for reference)
    Returns {items, pantry_items, added, covered}.
    """
    needed = get_aggregate_ingredients(start_date, end_date)
    pantry = list_pantry()

    pantry_map = {p["food"].lower().strip(): p for p in pantry}

    to_buy      = []
    from_pantry = []

    for item in needed:
        food_key = item["food"].lower().strip()
        match    = _find_pantry_match(food_key, pantry_map)

        if match is None:
            to_buy.append(item)
            continue

        p_qty  = match.get("quantity")
        n_qty  = item.get("quantity")
        p_unit = (match.get("unit") or "").lower().strip()
        n_unit = (item.get("unit") or "").lower().strip()

        if n_qty is None or p_qty is None:
            # No quantity on either side — assume pantry covers it
            from_pantry.append(item)
            continue

        if p_unit != n_unit:
            # Try normalising both to a base unit before giving up
            p_qty, p_unit = _to_base(p_qty, p_unit)
            n_qty, n_unit = _to_base(n_qty, n_unit)
            if p_unit != n_unit:
                # Still incompatible (e.g. g vs ml) — flag as needed
                to_buy.append(item)
                continue

        deficit = round(n_qty - p_qty, 3)
        if deficit <= 0:
            from_pantry.append(item)
        else:
            # Partial coverage — buy only the deficit
            to_buy.append({**item, 'quantity': deficit})
            from_pantry.append({**item, 'quantity': p_qty})

    date_val = list_date or end_date

    with db() as conn:
        conn.execute("DELETE FROM shopping_list WHERE list_date=?", (date_val,))
        for item in to_buy:
            conn.execute(
                "INSERT INTO shopping_list (food, quantity, unit, list_date, covered) VALUES (?,?,?,?,0)",
                (item["food"], item.get("quantity"), item.get("unit"), date_val)
            )
        for item in from_pantry:
            conn.execute(
                "INSERT INTO shopping_list (food, quantity, unit, list_date, covered) VALUES (?,?,?,?,1)",
                (item["food"], item.get("quantity"), item.get("unit"), date_val)
            )

    return {
        "items":        get_shopping_list(date_val),
        "pantry_items": get_pantry_covered(date_val),
        "added":        len(to_buy),
        "covered":      len(from_pantry),
    }


def get_shopping_list(list_date: str = None) -> list[dict]:
    """Items to buy (covered=0)."""
    with db() as conn:
        if list_date:
            rows = conn.execute(
                "SELECT * FROM shopping_list WHERE list_date=? AND covered=0 ORDER BY checked, food",
                (list_date,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM shopping_list WHERE covered=0 ORDER BY checked, food"
            ).fetchall()
    return rows_to_list(rows)


def get_pantry_covered(list_date: str = None) -> list[dict]:
    """Items already in pantry (covered=1), shown for reference."""
    with db() as conn:
        if list_date:
            rows = conn.execute(
                "SELECT * FROM shopping_list WHERE list_date=? AND covered=1 ORDER BY food",
                (list_date,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM shopping_list WHERE covered=1 ORDER BY food"
            ).fetchall()
    return rows_to_list(rows)


def check_item(item_id: int, checked: bool = True) -> bool:
    with db() as conn:
        cur = conn.execute(
            "UPDATE shopping_list SET checked=? WHERE id=?",
            (1 if checked else 0, item_id)
        )
    return cur.rowcount > 0


def add_manual_item(food: str, quantity: float = None, unit: str = None, list_date: str = None) -> dict:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO shopping_list (food, quantity, unit, list_date, covered) VALUES (?,?,?,?,0)",
            (food, quantity, unit, list_date)
        )
        row = conn.execute("SELECT * FROM shopping_list WHERE id=?", (cur.lastrowid,)).fetchone()
    return row_to_dict(row)


def clear_checked():
    with db() as conn:
        conn.execute("DELETE FROM shopping_list WHERE checked=1 AND covered=0")


def clear_list(list_date: str = None) -> None:
    """Clear the entire list for a date — buy items and pantry coverage."""
    with db() as conn:
        if list_date:
            conn.execute("DELETE FROM shopping_list WHERE list_date=?", (list_date,))
        else:
            conn.execute("DELETE FROM shopping_list")
