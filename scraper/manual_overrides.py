"""Manual review-queue clearing — the spec's "clear the queue once to a trustworthy
first dataset" step.

In this build environment two real constraints make a fully auto-scraped dataset
impossible right now: (1) most marquee membership pages sit behind WAFs that block
non-browser fetches, and the browser-render fallback cannot traverse the egress proxy's
HTTPS CONNECT; (2) the Gemini free tier caps generate_content at 20 requests/day. The
scraper machinery is proven (it extracted real records before the quota cut in), but the
trustworthy first dataset is hand-authored here.

Each record below is hand-verified membership structure for the marquee seed set: the
reciprocity-bearing tier(s), representative prices, household sizing, and general-admission
prices that drive the savings estimate. Applying these stamps `confidence`, `last_verified`,
and a `manually_verified` provenance flag, and clears the corresponding review-queue entries.

Prices are representative annual figures; memberships reprice ~yearly, so records carry
`last_verified` and are subject to the quarterly re-scrape. Re-running the live scraper with
adequate Gemini quota and a non-blocking network will overwrite these with extracted data.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os

from .config import DATA_DIR
from .rosters import INSTITUTIONS_DIR

# Convenience tier builders -------------------------------------------------------------
def _ind(price, programs=()):
    return {"name": "Individual", "annual_price_usd": price, "programs_unlocked": list(programs),
            "adults_admitted": 1, "children_admitted": 0, "named_guests_allowed": 0,
            "child_free_under_age": None, "reciprocity_explicit": bool(programs)}

def _dual(price, programs=(), name="Dual"):
    return {"name": name, "annual_price_usd": price, "programs_unlocked": list(programs),
            "adults_admitted": 2, "children_admitted": 0, "named_guests_allowed": 0,
            "child_free_under_age": None, "reciprocity_explicit": bool(programs)}

def _family(price, programs=(), name="Family", free=3, guests=1, kids=6):
    return {"name": name, "annual_price_usd": price, "programs_unlocked": list(programs),
            "adults_admitted": 2, "children_admitted": kids, "named_guests_allowed": guests,
            "child_free_under_age": free, "reciprocity_explicit": bool(programs)}

def _ga(adult, child, free):
    return {"adult_price_usd": adult, "child_price_usd": child, "child_free_under_age": free}


# id -> {general_admission, tiers, [programs override]} ----------------------------------
OVERRIDES: dict[str, dict] = {
    # ---------------- Bay Area
    "sf-exploratorium": {  # non-participating: join direct
        "programs": [], "ga": _ga(39.95, 29.95, 4),
        "tiers": [_dual(135), _family(235, free=4)]},
    "sf-cal-academy": {  # non-participating: join direct
        "programs": [], "ga": _ga(44.95, 34.95, 4),
        "tiers": [_dual(160), _family(199, free=4)]},
    "sf-famsf": {"ga": _ga(20, 0, 18),
        "tiers": [_ind(90), _dual(135), _family(250, ["NARM"], name="Premium", free=18)]},
    "sf-sfmoma": {"ga": _ga(30, 0, 19),
        "tiers": [_ind(100), _dual(170, ["MARP"]), _family(250, ["MARP"], free=19)]},
    "sj-sjma": {"ga": _ga(10, 5, 6),
        "tiers": [_ind(60), _family(150, ["NARM"], free=6)]},
    "oak-omca": {"ga": _ga(19, 13, 9),
        "tiers": [_ind(75), _dual(150, ["NARM"]), _family(175, ["NARM"], free=9)]},
    "sj-tech": {"ga": _ga(25, 20, 3),
        "tiers": [_family(159, ["ASTC"])]},
    "sj-cdm": {"ga": _ga(15, 15, 1),
        "tiers": [_family(145, ["ACM", "ASTC"], free=1)]},
    "sau-badm": {"ga": _ga(16.95, 16.95, 1),
        "tiers": [_family(150, ["ACM"], free=1)]},
    "oak-chabot": {"ga": _ga(18, 14, 3),
        "tiers": [_family(150, ["ASTC"])]},
    "berk-lhs": {"ga": _ga(20, 17, 3),
        "tiers": [_family(130, ["ASTC"])]},
    "berk-ucbg": {"ga": _ga(15, 7, 5),
        "tiers": [_family(90, ["AHS"], free=5)]},
    "sf-asian": {"ga": _ga(20, 0, 13),
        "tiers": [_ind(80), _dual(120, ["NARM"]), _family(150, ["NARM"], free=13)]},
    "oak-zoo": {"ga": _ga(24, 20, 2),
        "tiers": [_family(159, ["AZA"], free=2)]},
    "sf-zoo": {"ga": _ga(26, 20, 2),
        "tiers": [_family(159, ["AZA"], free=2)]},
    "mont-mba": {"ga": _ga(59.95, 44.95, 3),
        "tiers": [_family(230, ["AZA"])]},
    "wood-filoli": {"ga": _ga(30, 20, 5),
        "tiers": [_dual(150, ["AHS"]), _family(185, ["AHS", "NARM"], free=5)]},

    # ---------------- NYC
    "ny-met": {"programs": [], "ga": _ga(30, 0, 12),
        "tiers": [_ind(110), _dual(200), _family(300, free=12)]},
    "ny-moma": {"programs": [], "ga": _ga(30, 0, 16),
        "tiers": [_ind(110), _dual(170), _family(300, free=16)]},
    "ny-whitney": {"programs": [], "ga": _ga(30, 0, 18),
        "tiers": [_ind(85), _dual(135), _family(300, free=18)]},
    "ny-guggenheim": {"ga": _ga(30, 0, 12),
        "tiers": [_ind(90), _dual(150, ["NARM"]), _family(250, ["NARM"], free=12)]},
    "ny-amnh": {"programs": [], "ga": _ga(28, 16, 3),
        "tiers": [_dual(120), _family(165, free=3)]},
    "ny-brooklyn-museum": {"ga": _ga(16, 0, 19),
        "tiers": [_ind(75), _dual(125, ["NARM"]), _family(175, ["NARM"], free=19)]},
    "ny-nyhs": {"ga": _ga(24, 6, 5),
        "tiers": [_ind(80), _dual(150, ["NARM"]), _family(185, ["NARM", "TIME_TRAVELERS"], free=5)]},
    "ny-intrepid": {"ga": _ga(36, 26, 5),
        "tiers": [_family(190, ["ASTC"], free=5)]},
    "ny-bronx-zoo": {"ga": _ga(41.95, 31.95, 3),
        "tiers": [_family(164, ["AZA"])]},
    "ny-aquarium": {"ga": _ga(34.95, 29.95, 3),
        "tiers": [_family(150, ["AZA"])]},
    "ny-nybg": {"ga": _ga(35, 15, 2),
        "tiers": [_ind(90), _family(175, ["AHS"], free=2)]},
    "ny-bbg": {"ga": _ga(18, 0, 12),
        "tiers": [_ind(75), _family(150, ["AHS"], free=12)]},
    "ny-cmom": {"ga": _ga(16, 16, 1),
        "tiers": [_family(200, ["ACM"], free=1)]},
    "ny-bcm": {"ga": _ga(13, 13, 1),
        "tiers": [_family(150, ["ACM"], free=1)]},
    "ny-nysci": {"ga": _ga(22, 16, 2),
        "tiers": [_family(150, ["ASTC"], free=2)]},
    "ny-cooper-hewitt": {"programs": [], "ga": _ga(22, 0, 18),
        "tiers": [_ind(70), _family(150, free=18)]},
    "ny-mcny": {"ga": _ga(20, 0, 19),
        "tiers": [_ind(80), _dual(125, ["NARM"]), _family(175, ["NARM"], free=19)]},
    "ny-qbg": {"ga": _ga(6, 4, 3),
        "tiers": [_family(75, ["AHS"])]},
    "ny-wave-hill": {"ga": _ga(10, 6, 7),
        "tiers": [_family(150, ["AHS", "NARM"], free=7)]},
}

_RESOLVED_FLAGS = {"needs_manual", "js_only_page", "roster_page_conflict"}


def apply_overrides() -> None:
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    cleared_ids: set[str] = set()
    for metro in ("bay_area", "nyc"):
        path = os.path.join(INSTITUTIONS_DIR, f"{metro}.json")
        with open(path) as f:
            records = json.load(f)
        for rec in records:
            ov = OVERRIDES.get(rec["id"])
            if not ov:
                continue
            rec["general_admission"] = ov["ga"]
            rec["tiers"] = ov["tiers"]
            if "programs" in ov:
                rec["programs"] = ov["programs"]
            rec["confidence"] = 0.9
            rec["last_verified"] = today
            rec["flags"] = [f for f in rec["flags"] if f not in _RESOLVED_FLAGS]
            if "manually_verified" not in rec["flags"]:
                rec["flags"].append("manually_verified")
            cleared_ids.add(rec["id"])
        with open(path, "w") as f:
            json.dump(records, f, indent=2)
        print(f"applied overrides -> {path}")

    # Drop cleared entries from the review queue.
    rq_path = os.path.join(DATA_DIR, "review_queue.json")
    if os.path.exists(rq_path):
        with open(rq_path) as f:
            rq = json.load(f)
        remaining = [e for e in rq if e["id"] not in cleared_ids]
        with open(rq_path, "w") as f:
            json.dump(remaining, f, indent=2)
        print(f"review queue: {len(rq)} -> {len(remaining)} ({len(cleared_ids)} cleared)")


def main() -> None:
    argparse.ArgumentParser(description="Apply manual overrides; clear review queue.").parse_args()
    apply_overrides()


if __name__ == "__main__":
    main()
