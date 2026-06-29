"""Tier 1 — roster ingestion / institution-to-program edges.

The reciprocal-program rosters (NARM/ROAM/ASTC/AZA/AHS/ACM/Time Travelers) are published
as ugly PDFs and JS map widgets with no common structure. For the Phase-1 marquee seed set
the reliable path is a hand-verified program mapping (see scraper/seed.py
`believed_programs`), cross-checked against each institution's own page in Tier 2
(scraper/validate.py emits `roster_page_conflict` on disagreement).

This module turns the seed list into per-metro institution *skeletons*: it filters each
seed to its declared metro frontier (haversine against the config center/radius) and writes
records with program edges attached and empty `tiers` / `general_admission` for Tier 2 to
fill.

`fetch_roster_urls()` documents where to find current rosters at build time; live roster
parsing is intentionally out of scope for Phase 1 (the seed mapping is authoritative for the
marquee set, and the cross-check guards it).
"""
from __future__ import annotations

import argparse
import json
import os

from .config import load_config, DATA_DIR
from .geocode import haversine
from .seed import SEED_INSTITUTIONS

INSTITUTIONS_DIR = os.path.join(DATA_DIR, "institutions")


def _skeleton(seed: dict) -> dict:
    """Build an institution record with Tier-1 edges; Tier-2 fields left empty."""
    return {
        "id": seed["id"],
        "name": seed["name"],
        "metro": seed["metro"],
        "address": seed["address"],
        "lat": seed["lat"],
        "lng": seed["lng"],
        "membership_url": seed["membership_url"],
        "programs": list(seed.get("believed_programs", [])),
        "reciprocity_overrides": dict(seed.get("reciprocity_overrides", {})),
        # Tier 2 fills these:
        "tiers": [],
        "general_admission": None,
        "source_urls": [seed["membership_url"]],
        "last_verified": None,
        "confidence": 0.0,
        "flags": list(seed.get("flags", [])),
        "notes": seed.get("notes", ""),
    }


def build_skeletons(config: dict) -> dict[str, list[dict]]:
    """Filter seeds into their metro frontier and return {metro: [records]}."""
    by_metro: dict[str, list[dict]] = {m: [] for m in config["metros"]}
    for seed in SEED_INSTITUTIONS:
        metro = seed["metro"]
        mcfg = config["metros"][metro]
        center = mcfg["center"]
        dist = haversine(center["lat"], center["lng"], seed["lat"], seed["lng"])
        if dist > mcfg["radius_miles"]:
            # Outside the declared frontier — flag rather than silently drop.
            rec = _skeleton(seed)
            rec["flags"].append("outside_metro_frontier")
            rec["notes"] = (rec["notes"] + f" [{dist:.0f}mi from {metro} center]").strip()
            by_metro[metro].append(rec)
            continue
        by_metro[metro].append(_skeleton(seed))
    return by_metro


def write_skeletons(by_metro: dict[str, list[dict]]) -> None:
    os.makedirs(INSTITUTIONS_DIR, exist_ok=True)
    for metro, records in by_metro.items():
        path = os.path.join(INSTITUTIONS_DIR, f"{metro}.json")
        # If a dataset already exists (Tier 2 ran), preserve filled fields by id.
        existing = {}
        if os.path.exists(path):
            with open(path) as f:
                for r in json.load(f):
                    existing[r["id"]] = r
        merged = []
        for rec in records:
            prior = existing.get(rec["id"])
            if prior:
                # keep Tier-2 output, refresh Tier-1 edges
                prior["programs"] = rec["programs"]
                prior["reciprocity_overrides"] = rec["reciprocity_overrides"]
                merged.append(prior)
            else:
                merged.append(rec)
        with open(path, "w") as f:
            json.dump(merged, f, indent=2)
        print(f"wrote {len(merged):2d} institutions -> {path}")


def fetch_roster_urls() -> dict[str, str]:
    """Current roster locations (find at build time; do not hardcode stale data)."""
    with open(os.path.join(DATA_DIR, "programs.json")) as f:
        programs = json.load(f)
    return {k: v.get("roster_url", "") for k, v in programs.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description="Tier 1: build institution skeletons.")
    ap.parse_args()
    config = load_config()
    by_metro = build_skeletons(config)
    write_skeletons(by_metro)


if __name__ == "__main__":
    main()
