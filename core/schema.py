"""
core/schema.py — Database initialization and migrations
Run directly to create/reset the database: python -m core.schema
"""
from core.db import get_connection

SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    description TEXT,
    json_path   TEXT NOT NULL,
    image_url   TEXT,
    prep_time   TEXT,
    cook_time   TEXT,
    total_time  TEXT,
    servings    INTEGER,
    category    TEXT,
    cuisine     TEXT,
    tags        TEXT,
    ingredients TEXT NOT NULL DEFAULT '[]',
    source_url  TEXT,
    source_type TEXT DEFAULT 'manual',
    status      TEXT DEFAULT 'active',
    favorited   INTEGER DEFAULT 0,
    mealie_id   TEXT,
    nostr_event_id TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pantry (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    food        TEXT NOT NULL,
    quantity    REAL,
    unit        TEXT,
    notes       TEXT,
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meal_plan (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    meal_type   TEXT NOT NULL,
    recipe_slug TEXT NOT NULL,
    servings    INTEGER DEFAULT 1,
    FOREIGN KEY (recipe_slug) REFERENCES recipes(slug) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS shopping_list (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    food        TEXT NOT NULL,
    quantity    REAL,
    unit        TEXT,
    checked     INTEGER DEFAULT 0,
    list_date   TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT
);

CREATE INDEX IF NOT EXISTS idx_recipes_status ON recipes(status);
CREATE INDEX IF NOT EXISTS idx_recipes_slug ON recipes(slug);
CREATE INDEX IF NOT EXISTS idx_meal_plan_date ON meal_plan(date);
CREATE INDEX IF NOT EXISTS idx_shopping_list_checked ON shopping_list(checked);
"""


MIGRATIONS = [
    # Add covered column to shopping_list (items already in pantry, shown for reference)
    "ALTER TABLE shopping_list ADD COLUMN covered INTEGER DEFAULT 0",
    # Add favorited flag to recipes
    "ALTER TABLE recipes ADD COLUMN favorited INTEGER DEFAULT 0",
    # Track external platform IDs for sync/export
    "ALTER TABLE recipes ADD COLUMN mealie_id TEXT",
    "ALTER TABLE recipes ADD COLUMN nostr_event_id TEXT",
]


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    # Run migrations idempotently (SQLite has no IF NOT EXISTS for ALTER TABLE)
    for sql in MIGRATIONS:
        try:
            conn.execute(sql)
            conn.commit()
        except Exception:
            pass  # Column already exists — safe to ignore
    conn.close()
    print("Database initialized: chef.db")


if __name__ == "__main__":
    init_db()
