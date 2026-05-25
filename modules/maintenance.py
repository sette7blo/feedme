"""Maintenance helpers for Feedme routes.

Keeps backup/restore, version, and admin-style utilities out of server.py while
preserving the existing Flask route contract.
"""
from __future__ import annotations

import io
import json
import threading
import time
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable

import core.config as config
from core.db import db
from modules import importer

BASE_DIR = Path(__file__).resolve().parent.parent
VERSION_FILE = BASE_DIR / "VERSION"
GITHUB_API = "https://api.github.com/repos/sette7blo/feedme/releases/latest"
CACHE_TTL = 3600  # 1 hour
SECRET_BACKUP_KEYS = {"FLASK_SECRET"}
_version_cache = {"latest": None, "checked_at": 0.0}


def rss_feed_stats(feeds_raw: str | None = None) -> dict[str, int]:
    """Count staged/imported RSS recipes by configured feed domain."""
    from urllib.parse import urlparse

    feeds_raw = config.get("RSS_FEEDS", "") if feeds_raw is None else feeds_raw
    feeds = [f.strip() for f in feeds_raw.split(",") if f.strip()]
    result: dict[str, int] = {}
    with db() as conn:
        for feed_url in feeds:
            domain = urlparse(feed_url).netloc
            if not domain:
                continue
            count = conn.execute(
                "SELECT COUNT(*) FROM recipes WHERE source_type='rss' AND source_url LIKE ?",
                (f"%{domain}%",),
            ).fetchone()[0]
            result[feed_url] = count
    return result


def read_local_version(version_file: Path | None = None) -> str:
    """Read the installed app version, returning 'unknown' if unavailable."""
    version_file = version_file or VERSION_FILE
    try:
        return version_file.read_text().strip()
    except OSError:
        return "unknown"


def _do_fetch_latest_version() -> None:
    try:
        req = urllib.request.Request(
            GITHUB_API,
            headers={"User-Agent": "Feedme/1.0", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        tag = data.get("tag_name", "").lstrip("v")
        _version_cache["latest"] = tag
        _version_cache["checked_at"] = time.time()
    except Exception:
        pass


def fetch_latest_version() -> str | None:
    """Return cached latest release, refreshing in the background when stale."""
    now = time.time()
    if _version_cache["latest"] and now - _version_cache["checked_at"] < CACHE_TTL:
        return _version_cache["latest"]
    threading.Thread(target=_do_fetch_latest_version, daemon=True).start()
    return _version_cache["latest"]


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in version.split("."))


def version_info() -> dict[str, object]:
    current = read_local_version()
    latest = fetch_latest_version()
    update_available = False
    if latest and current != "unknown":
        try:
            update_available = _version_tuple(latest) > _version_tuple(current)
        except Exception:
            update_available = latest != current
    return {
        "current": current,
        "latest": latest,
        "update_available": update_available,
        "release_url": "https://github.com/sette7blo/feedme/releases/latest",
    }


def _backup_settings(base: Path) -> dict[str, str]:
    settings: dict[str, str] = {}
    env_path = base / ".env"
    if not env_path.exists():
        return settings
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key in SECRET_BACKUP_KEYS:
                continue
            settings[key] = value.strip()
    return settings


def create_backup(base_dir: Path | str | None = None) -> tuple[bytes, str]:
    """Return backup zip bytes and a timestamped filename."""
    base = Path(base_dir) if base_dir is not None else BASE_DIR
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder in ("recipes", "images"):
            folder_path = base / folder
            if not folder_path.exists():
                continue
            for f in folder_path.iterdir():
                if f.is_file():
                    zf.write(f, f"{folder}/{f.name}")
        settings = _backup_settings(base)
        if settings:
            zf.writestr("settings.json", json.dumps(settings, indent=2))
    filename = f"feedme-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    return buf.getvalue(), filename


def restore_backup(
    file_storage,
    base_dir: Path | str | None = None,
    *,
    save_env: Callable[[dict], None] = config.save_env,
    sync_all: Callable[[], object] = importer.sync_all,
) -> tuple[dict[str, object], int]:
    """Restore a backup upload and return (payload, http_status)."""
    if not file_storage:
        return {"error": "No file uploaded"}, 400
    if not file_storage.filename.endswith(".zip"):
        return {"error": "File must be a .zip"}, 400

    buf = io.BytesIO(file_storage.read())
    try:
        zf = zipfile.ZipFile(buf, "r")
    except zipfile.BadZipFile:
        return {"error": "Invalid zip file"}, 400

    base = Path(base_dir) if base_dir is not None else BASE_DIR
    recipes_restored = 0
    images_restored = 0
    for name in zf.namelist():
        if name.startswith("recipes/") and not name.endswith("/"):
            target = base / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(name))
            recipes_restored += 1
        elif name.startswith("images/") and not name.endswith("/"):
            target = base / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(name))
            images_restored += 1
        elif name == "settings.json":
            restored_settings = json.loads(zf.read(name))
            save_env(restored_settings)
    zf.close()
    sync_all()
    return {"ok": True, "recipes": recipes_restored, "images": images_restored}, 200
