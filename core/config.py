"""
core/config.py — Environment and settings loader
"""
import os
from pathlib import Path

ENV_PATH = Path(__file__).parent.parent / ".env"


def load_env():
    """Load .env file into os.environ (no external dependency)."""
    if not ENV_PATH.exists():
        return
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def save_env(updates: dict):
    """Write/update keys in .env file."""
    existing = {}
    if ENV_PATH.exists():
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                existing[key.strip()] = value.strip()

    existing.update(updates)
    # Update os.environ too
    for k, v in updates.items():
        os.environ[k] = v

    with open(ENV_PATH, "w") as f:
        for key, value in existing.items():
            f.write(f"{key}={value}\n")


def get(key, default=None):
    return os.environ.get(key, default)


# Load on import
load_env()
