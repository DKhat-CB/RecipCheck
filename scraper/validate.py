"""Validation — cross-checks and confidence routing (how the dataset earns trust)."""
from __future__ import annotations

from typing import Any

AUTO_COMMIT_CONFIDENCE = 0.8


def page_programs(tiers: list[dict]) -> set[str]:
    progs: set[str] = set()
    for t in tiers:
        progs.update(t.get("programs_unlocked", []) or [])
    return progs


def cross_check(record: dict, extraction: dict) -> list[str]:
    """Compare Tier-1 believed programs against Tier-2 page extraction.

    Returns a list of flag strings. `roster_page_conflict` when a roster claims a program
    that no tier on the page surfaces (the page may gate it, or the roster may lag reality).
    `non_participating` records are exempt — they are expected to show no reciprocity.
    """
    flags: list[str] = []
    if "non_participating" in record.get("flags", []):
        return flags
    believed = set(record.get("programs", []))
    found = page_programs(extraction.get("tiers", []))
    missing = believed - found
    if missing:
        flags.append("roster_page_conflict")
    return flags


def route(record: dict, extraction: dict, fetch_status: str) -> tuple[bool, str]:
    """Decide auto-commit vs. review. Returns (auto_commit, reason)."""
    conf = float(extraction.get("confidence", 0.0))
    needs_manual = bool(extraction.get("needs_manual", False))
    if fetch_status in ("blocked", "js_only", "error"):
        return False, f"fetch {fetch_status}"
    if needs_manual:
        return False, "model set needs_manual"
    if conf < AUTO_COMMIT_CONFIDENCE:
        return False, f"confidence {conf:.2f} < {AUTO_COMMIT_CONFIDENCE}"
    if "roster_page_conflict" in record.get("flags", []):
        return False, "roster_page_conflict"
    return True, "auto-commit"


def review_entry(record: dict, extraction: dict | None, reason: str,
                 snippet: str, fetch_status: str) -> dict[str, Any]:
    return {
        "id": record["id"],
        "name": record["name"],
        "metro": record["metro"],
        "membership_url": record["membership_url"],
        "reason": reason,
        "fetch_status": fetch_status,
        "model_output": extraction,
        "page_snippet": (snippet or "")[:1500],
    }
