"""Shared config + path helpers and .env loading for the scraper package."""
from __future__ import annotations

import os
from functools import lru_cache

import yaml

ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(ROOT, "data")
CONFIG_PATH = os.path.join(ROOT, "config.yaml")


@lru_cache(maxsize=1)
def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_dotenv(path: str | None = None) -> None:
    """Minimal .env loader (no dependency). Does not overwrite existing env vars."""
    path = path or os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)
