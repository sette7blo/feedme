"""
modules/grocery.py — Pantry diff → shopping list generation
"""
import re
from core.db import db, rows_to_list, row_to_dict
import core.config as config
from modules.meal_planner import get_aggregate_ingredients, _to_base, _display
from modules.pantry import list_pantry

# Keyword rules — first match wins. Order matters: specific before generic.
_CATEGORY_RULES = [
    # Meat & Fish (before generic terms like "pepper")
    ('chicken', 'Meat & Fish'), ('beef', 'Meat & Fish'), ('pork', 'Meat & Fish'),
    ('lamb', 'Meat & Fish'), ('turkey', 'Meat & Fish'), ('duck', 'Meat & Fish'),
    ('veal', 'Meat & Fish'), ('bacon', 'Meat & Fish'), ('ham', 'Meat & Fish'),
    ('sausage', 'Meat & Fish'), ('salami', 'Meat & Fish'), ('pepperoni', 'Meat & Fish'),
    ('steak', 'Meat & Fish'), ('brisket', 'Meat & Fish'),
    ('salmon', 'Meat & Fish'), ('tuna', 'Meat & Fish'), ('shrimp', 'Meat & Fish'),
    ('prawn', 'Meat & Fish'), ('cod', 'Meat & Fish'), ('tilapia', 'Meat & Fish'),
    ('halibut', 'Meat & Fish'), ('crab', 'Meat & Fish'), ('lobster', 'Meat & Fish'),
    ('scallop', 'Meat & Fish'), ('anchovy', 'Meat & Fish'), ('sardine', 'Meat & Fish'),
    ('trout', 'Meat & Fish'), ('snapper', 'Meat & Fish'), ('mussels', 'Meat & Fish'),
    # Dairy & Eggs
    ('buttermilk', 'Dairy & Eggs'), ('mozzarella', 'Dairy & Eggs'), ('parmesan', 'Dairy & Eggs'),
    ('cheddar', 'Dairy & Eggs'), ('ricotta', 'Dairy & Eggs'), ('feta', 'Dairy & Eggs'),
    ('brie', 'Dairy & Eggs'), ('gouda', 'Dairy & Eggs'), ('gruyere', 'Dairy & Eggs'),
    ('cream cheese', 'Dairy & Eggs'), ('sour cream', 'Dairy & Eggs'), ('cottage cheese', 'Dairy & Eggs'),
    ('whipping cream', 'Dairy & Eggs'), ('heavy cream', 'Dairy & Eggs'),
    ('milk', 'Dairy & Eggs'), ('cream', 'Dairy & Eggs'), ('butter', 'Dairy & Eggs'),
    ('cheese', 'Dairy & Eggs'), ('egg', 'Dairy & Eggs'), ('yogurt', 'Dairy & Eggs'),
    ('yoghurt', 'Dairy & Eggs'),
    # Canned & Jarred (specific phrases before generic words)
    ('tomato paste', 'Canned & Jarred'), ('tomato sauce', 'Canned & Jarred'),
    ('diced tomato', 'Canned & Jarred'), ('crushed tomato', 'Canned & Jarred'),
    ('coconut milk', 'Canned & Jarred'), ('chicken broth', 'Canned & Jarred'),
    ('beef broth', 'Canned & Jarred'), ('vegetable broth', 'Canned & Jarred'),
    ('broth', 'Canned & Jarred'), ('stock', 'Canned & Jarred'),
    ('capers', 'Canned & Jarred'), ('passata', 'Canned & Jarred'),
    ('peanut butter', 'Canned & Jarred'), ('tahini', 'Canned & Jarred'),
    ('jam', 'Canned & Jarred'), ('olive', 'Canned & Jarred'),
    # Condiments & Spices (oils before generic terms)
    ('olive oil', 'Condiments & Spices'), ('vegetable oil', 'Condiments & Spices'),
    ('coconut oil', 'Condiments & Spices'), ('sesame oil', 'Condiments & Spices'),
    ('canola oil', 'Condiments & Spices'), ('oil', 'Condiments & Spices'),
    ('soy sauce', 'Condiments & Spices'), ('fish sauce', 'Condiments & Spices'),
    ('oyster sauce', 'Condiments & Spices'), ('hoisin', 'Condiments & Spices'),
    ('worcestershire', 'Condiments & Spices'), ('sriracha', 'Condiments & Spices'),
    ('hot sauce', 'Condiments & Spices'), ('tabasco', 'Condiments & Spices'),
    ('vinegar', 'Condiments & Spices'), ('mustard', 'Condiments & Spices'),
    ('ketchup', 'Condiments & Spices'), ('mayonnaise', 'Condiments & Spices'),
    ('mayo', 'Condiments & Spices'), ('honey', 'Condiments & Spices'),
    ('maple syrup', 'Condiments & Spices'), ('vanilla', 'Condiments & Spices'),
    ('paprika', 'Condiments & Spices'), ('cumin', 'Condiments & Spices'),
    ('turmeric', 'Condiments & Spices'), ('cinnamon', 'Condiments & Spices'),
    ('nutmeg', 'Condiments & Spices'), ('oregano', 'Condiments & Spices'),
    ('cayenne', 'Condiments & Spices'), ('chilli', 'Condiments & Spices'),
    ('chili', 'Condiments & Spices'), ('curry powder', 'Condiments & Spices'),
    ('curry', 'Condiments & Spices'), ('cardamom', 'Condiments & Spices'),
    ('bay leaf', 'Condiments & Spices'), ('allspice', 'Condiments & Spices'),
    ('star anise', 'Condiments & Spices'), ('sesame', 'Condiments & Spices'),
    ('saffron', 'Condiments & Spices'), ('coriander', 'Condiments & Spices'),
    ('salt', 'Condiments & Spices'), ('pepper', 'Condiments & Spices'),
    # Bakery
    ('sourdough', 'Bakery'), ('ciabatta', 'Bakery'), ('baguette', 'Bakery'),
    ('tortilla', 'Bakery'), ('pita', 'Bakery'), ('bagel', 'Bakery'),
    ('cracker', 'Bakery'), ('bread', 'Bakery'), ('bun', 'Bakery'), ('roll', 'Bakery'),
    # Produce — herbs
    ('basil', 'Produce'), ('parsley', 'Produce'), ('cilantro', 'Produce'),
    ('thyme', 'Produce'), ('rosemary', 'Produce'), ('mint', 'Produce'),
    ('chive', 'Produce'), ('dill', 'Produce'), ('tarragon', 'Produce'),
    ('sage', 'Produce'), ('bay', 'Produce'),
    # Produce — fruits
    ('apple', 'Produce'), ('banana', 'Produce'), ('lemon', 'Produce'),
    ('lime', 'Produce'), ('orange', 'Produce'), ('grape', 'Produce'),
    ('strawberr', 'Produce'), ('blueberr', 'Produce'), ('raspberr', 'Produce'),
    ('mango', 'Produce'), ('pineapple', 'Produce'), ('peach', 'Produce'),
    ('pear', 'Produce'), ('cherry', 'Produce'), ('watermelon', 'Produce'),
    ('avocado', 'Produce'), ('fig', 'Produce'), ('plum', 'Produce'),
    # Produce — vegetables
    ('tomato', 'Produce'), ('onion', 'Produce'), ('garlic', 'Produce'),
    ('potato', 'Produce'), ('carrot', 'Produce'), ('celery', 'Produce'),
    ('lettuce', 'Produce'), ('spinach', 'Produce'), ('kale', 'Produce'),
    ('broccoli', 'Produce'), ('cauliflower', 'Produce'), ('capsicum', 'Produce'),
    ('zucchini', 'Produce'), ('courgette', 'Produce'), ('cucumber', 'Produce'),
    ('mushroom', 'Produce'), ('ginger', 'Produce'), ('corn', 'Produce'),
    ('asparagus', 'Produce'), ('beetroot', 'Produce'), ('beet', 'Produce'),
    ('cabbage', 'Produce'), ('eggplant', 'Produce'), ('aubergine', 'Produce'),
    ('fennel', 'Produce'), ('leek', 'Produce'), ('pea', 'Produce'),
    ('shallot', 'Produce'), ('squash', 'Produce'), ('pumpkin', 'Produce'),
    ('sweet potato', 'Produce'), ('yam', 'Produce'), ('arugula', 'Produce'),
    ('rocket', 'Produce'), ('bok choy', 'Produce'), ('spring onion', 'Produce'),
    ('scallion', 'Produce'), ('radish', 'Produce'), ('turnip', 'Produce'),
    ('artichoke', 'Produce'), ('endive', 'Produce'), ('watercress', 'Produce'),
    # Dry Goods
    ('spaghetti', 'Dry Goods'), ('fettuccine', 'Dry Goods'), ('penne', 'Dry Goods'),
    ('rigatoni', 'Dry Goods'), ('lasagna', 'Dry Goods'), ('fusilli', 'Dry Goods'),
    ('pasta', 'Dry Goods'), ('noodle', 'Dry Goods'), ('rice', 'Dry Goods'),
    ('quinoa', 'Dry Goods'), ('barley', 'Dry Goods'), ('couscous', 'Dry Goods'),
    ('polenta', 'Dry Goods'), ('lentil', 'Dry Goods'), ('chickpea', 'Dry Goods'),
    ('black bean', 'Dry Goods'), ('kidney bean', 'Dry Goods'), ('white bean', 'Dry Goods'),
    ('flour', 'Dry Goods'), ('sugar', 'Dry Goods'), ('brown sugar', 'Dry Goods'),
    ('oat', 'Dry Goods'), ('breadcrumb', 'Dry Goods'), ('panko', 'Dry Goods'),
    ('cornstarch', 'Dry Goods'), ('cornflour', 'Dry Goods'), ('cocoa', 'Dry Goods'),
    ('chocolate', 'Dry Goods'), ('baking powder', 'Dry Goods'), ('baking soda', 'Dry Goods'),
    ('yeast', 'Dry Goods'), ('almond', 'Dry Goods'), ('walnut', 'Dry Goods'),
    ('cashew', 'Dry Goods'), ('pecan', 'Dry Goods'), ('pistachio', 'Dry Goods'),
    ('pine nut', 'Dry Goods'), ('chia', 'Dry Goods'), ('flax', 'Dry Goods'),
    ('sunflower seed', 'Dry Goods'), ('pumpkin seed', 'Dry Goods'),
    # Frozen
    ('frozen', 'Frozen'),
    # Beverages
    ('wine', 'Beverages'), ('beer', 'Beverages'), ('juice', 'Beverages'),
]


def _categorize(food: str) -> str:
    """Return a grocery category for the given food name, or 'Other'."""
    f = food.lower().strip()
    for keyword, category in _CATEGORY_RULES:
        if keyword in f:
            return category
    return 'Other'

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
            p_qty, p_unit = _to_base(p_qty, p_unit)
            n_qty, n_unit = _to_base(n_qty, n_unit)
            if p_unit != n_unit:
                to_buy.append(item)
                continue

        deficit = round(n_qty - p_qty, 3)
        if deficit <= 0:
            from_pantry.append(item)
        else:
            to_buy.append({**item, 'quantity': deficit, 'unit': n_unit})
            from_pantry.append({**item, 'quantity': p_qty, 'unit': p_unit})

    # Convert all quantities to preferred display units
    preferred = config.get("PREFERRED_UNITS", "")
    for lst in (to_buy, from_pantry):
        for item in lst:
            if item.get("quantity") is not None and item.get("unit") in ("g", "ml"):
                item["quantity"], item["unit"] = _display(
                    item["quantity"], item["unit"], preferred)

    date_val = list_date or end_date

    with db() as conn:
        # Preserve manually added items (no matching meal plan entry)
        manual = conn.execute(
            "SELECT food, quantity, unit FROM shopping_list WHERE list_date=? AND covered=0",
            (date_val,)
        ).fetchall()
        manual_keep = [dict(r) for r in manual if r["food"].lower().strip() not in
                       {i["food"].lower().strip() for i in to_buy}]

        conn.execute("DELETE FROM shopping_list WHERE list_date=?", (date_val,))
        for item in to_buy:
            conn.execute(
                "INSERT INTO shopping_list (food, quantity, unit, list_date, covered, category) VALUES (?,?,?,?,0,?)",
                (item["food"], item.get("quantity"), item.get("unit"), date_val, _categorize(item["food"]))
            )
        for item in from_pantry:
            conn.execute(
                "INSERT INTO shopping_list (food, quantity, unit, list_date, covered, category) VALUES (?,?,?,?,1,?)",
                (item["food"], item.get("quantity"), item.get("unit"), date_val, _categorize(item["food"]))
            )
        for item in manual_keep:
            conn.execute(
                "INSERT INTO shopping_list (food, quantity, unit, list_date, covered, category) VALUES (?,?,?,?,0,?)",
                (item["food"], item.get("quantity"), item.get("unit"), date_val, _categorize(item["food"]))
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
            "INSERT INTO shopping_list (food, quantity, unit, list_date, covered, category) VALUES (?,?,?,?,0,?)",
            (food, quantity, unit, list_date, _categorize(food))
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
