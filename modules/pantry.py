"""
modules/pantry.py — Pantry CRUD operations
"""
from core.db import db, rows_to_list, row_to_dict


def list_pantry() -> list:
    with db() as conn:
        rows = conn.execute("SELECT * FROM pantry ORDER BY food ASC").fetchall()
    return rows_to_list(rows)


def add_item(food: str, quantity: float = None, unit: str = None, notes: str = None) -> dict:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO pantry (food, quantity, unit, notes) VALUES (?,?,?,?)",
            (food, quantity, unit, notes)
        )
        row = conn.execute("SELECT * FROM pantry WHERE id=?", (cur.lastrowid,)).fetchone()
    return row_to_dict(row)


def update_item(item_id: int, **kwargs) -> bool:
    fields = {k: v for k, v in kwargs.items() if k in ("food", "quantity", "unit", "notes")}
    if not fields:
        return False
    set_clause = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [item_id]
    with db() as conn:
        cur = conn.execute(
            f"UPDATE pantry SET {set_clause}, updated_at=datetime('now') WHERE id=?",
            values
        )
    return cur.rowcount > 0


def delete_item(item_id: int) -> bool:
    with db() as conn:
        cur = conn.execute("DELETE FROM pantry WHERE id=?", (item_id,))
    return cur.rowcount > 0
