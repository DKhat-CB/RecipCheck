"""Web-sourced data clearing of the review queue — the spec's "clear the queue once to a
trustworthy first dataset" step, refreshed with real museum-site data.

In this build environment the automated crawl could not extract cleanly: marquee membership
pages WAF-block non-browser fetches, the browser-render fallback cannot traverse the egress
proxy's HTTPS CONNECT, and the Gemini free tier caps at 20 requests/day. The scraper
machinery is proven, but the trustworthy first dataset is sourced here via web search of the
institutions' own membership/admission pages plus document review.

Each record carries `src` (the official pages the figures came from). Applying these stamps
`confidence`, `last_verified`, `source_urls`, and a `web_sourced` provenance flag. Where a
specific membership price could not be pinned to an exact current figure, the record uses a
best-estimate value and is additionally flagged `price_approximate` (and keeps a lower
confidence) rather than implying false precision. Memberships reprice ~yearly; the quarterly
re-scrape (or a future crawl with adequate quota + open network) overwrites these.

Per-tier program mapping is preserved: a program is listed on the specific tier the page ties
it to (reciprocity usually rides on a higher donor tier), not the institution as a whole.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os

from .config import DATA_DIR
from .rosters import INSTITUTIONS_DIR


def tier(name, price, programs=(), adults=1, kids=0, guests=0, free=None):
    return {"name": name, "annual_price_usd": price, "programs_unlocked": list(programs),
            "adults_admitted": adults, "children_admitted": kids, "named_guests_allowed": guests,
            "child_free_under_age": free, "reciprocity_explicit": bool(programs)}


def ga(adult, child, free):
    return {"adult_price_usd": adult, "child_price_usd": child, "child_free_under_age": free}


# id -> {ga, tiers, [programs override], src:[urls], [approx:bool]} ----------------------
OVERRIDES: dict[str, dict] = {
    # ============================================================ Bay Area
    "sf-exploratorium": {  # ASTC member but treated non_participating per spec edge case
        "programs": [], "ga": ga(39.95, 29.95, 4),
        "tiers": [tier("Dual Explorers", 159, adults=2, free=4),
                  tier("Curious Family", 239, adults=2, kids=4, free=4)],
        "src": ["https://www.exploratorium.edu/membership", "https://www.exploratorium.edu/tickets"]},
    "sf-cal-academy": {  # ASTC member but treated non_participating per spec edge case
        "programs": [], "ga": ga(49.00, 39.00, 3),
        "tiers": [tier("Community Value", 199, adults=2, kids=4, free=3),
                  tier("Family", 299, adults=2, kids=4, free=3)],
        "src": ["https://www.calacademy.org/membership/compare-membership-levels",
                "https://www.calacademy.org/hours-admission"]},
    "sf-famsf": {"ga": ga(20, 0, 18),
        "tiers": [tier("Individual", 110, adults=1, free=18),
                  tier("Dual", 175, adults=2, free=18),
                  tier("Contributor", 299, ["NARM"], adults=2, kids=4, guests=1, free=18)],
        "src": ["https://www.famsf.org/join"]},
    "sf-sfmoma": {"ga": ga(30, 0, 19),
        "tiers": [tier("Individual", 130, adults=1, free=19),
                  tier("Dual", 185, adults=2, free=19),
                  tier("Supporter", 300, ["MARP"], adults=2, kids=4, guests=2, free=19)],
        "src": ["https://www.sfmoma.org/membership/", "https://www.sfmoma.org/membership/reciprocal-benefits/"]},
    "sj-sjma": {"ga": ga(20, 0, 18),
        "tiers": [tier("Individual", 60, adults=1, free=18),
                  tier("Dual", 90, ["NARM"], adults=2, guests=2, free=18)],
        "src": ["https://sjmusart.org/membership", "https://sjmusart.org/hours-and-admissions"]},
    "oak-omca": {"ga": ga(19, 12, 13),
        "tiers": [tier("Individual", 75, ["NARM"], adults=2, free=13),  # cardholder + guest
                  tier("Dual", 150, ["NARM"], adults=2, kids=4, guests=1, free=13)],
        "src": ["https://museumca.org/", "https://buy.acmeticketing.com/membership/492/join"]},
    "sf-asian": {"ga": ga(20, 0, 18),
        "tiers": [tier("Member", 89, adults=2, free=18),
                  tier("Member Premium", 249, ["NARM", "ROAM"], adults=2, kids=4, guests=2, free=18)],
        "src": ["https://give.asianart.org/membership/", "https://give.asianart.org/membership/reciprocal-membership/"]},
    "sj-tech": {"ga": ga(38, 28, 3),
        "tiers": [tier("Family", 159, ["ASTC"], adults=2, kids=4, free=3)],
        "src": ["https://www.thetech.org/support/membership-options/"], "approx": True},
    "sj-cdm": {"ga": ga(18, 18, 1),
        "tiers": [tier("Family", 150, ["ACM", "ASTC"], adults=2, kids=4, free=1)],
        "src": ["https://www.cdm.org/membership-faq/", "https://www.cdm.org/hours-pricing/"], "approx": True},
    "sau-badm": {"ga": ga(20, 20, 1),
        "tiers": [tier("Family", 229, ["ACM"], adults=2, kids=4, free=1)],
        "src": ["https://bayareadiscoverymuseum.org/membership/"]},
    "oak-chabot": {"ga": ga(24, 19, 2),
        "tiers": [tier("Family", 99, ["ASTC"], adults=2, kids=4, free=2)],
        "src": ["https://chabotspace.org/join-and-give/membership/"]},
    "berk-lhs": {"ga": ga(25, 25, 3),
        "tiers": [tier("Family", 200, ["ASTC", "ACM"], adults=2, kids=4, guests=2, free=3)],
        "src": ["https://lawrencehallofscience.org/support/membership/"]},
    "berk-ucbg": {"ga": ga(18, 8, 5),
        "tiers": [tier("Family Plus", 125, ["AHS"], adults=2, kids=4, guests=4, free=5)],
        "src": ["https://botanicalgarden.berkeley.edu/support/join/"]},
    "oak-zoo": {"ga": ga(24, 20, 2),
        "tiers": [tier("Family & Friends", 229, ["AZA"], adults=2, kids=4, free=2)],
        "src": ["https://www.oaklandzoo.org/membership", "https://www.oaklandzoo.org/admission"]},
    "sf-zoo": {"ga": ga(29, 20, 2),
        "tiers": [tier("Family", 159, ["AZA"], adults=2, kids=4, free=2)],
        "src": ["https://www.sfzoo.org/become-a-member/"], "approx": True},
    "mont-mba": {"ga": ga(65, 50, 5),
        "tiers": [tier("Individual", 125, ["AZA"], adults=1, free=5),
                  tier("Family", 180, ["AZA"], adults=2, kids=4, free=5),
                  tier("Premium", 250, ["AZA"], adults=2, guests=2, free=5)],
        "src": ["https://www.montereybayaquarium.org/support-us/become-a-member"]},
    # Reciprocal participation could NOT be confirmed from Filoli's own page (the prices were
    # sourced; the AHS/NARM tags were an unverified Tier-1 guess and are dropped). Treated as
    # join-direct until a primary source confirms otherwise.
    "wood-filoli": {"programs": [], "ga": ga(45, 35, 5),
        "tiers": [tier("Household", 140, adults=2, kids=4, free=5),
                  tier("Premium", 275, adults=2, kids=4, guests=2, free=5)],
        "src": ["https://filoli.org/support/membership/"]},

    # ============================================================ NYC
    "ny-met": {"programs": [], "ga": ga(30, 0, 12),
        "tiers": [tier("Individual", 110, adults=1, free=12),
                  tier("Dual", 175, adults=2, free=12),
                  tier("Family/Friend", 225, adults=2, kids=4, free=12)],
        "src": ["https://www.metmuseum.org/support/membership"]},
    "ny-moma": {"programs": [], "ga": ga(30, 0, 17),
        "tiers": [tier("Annual Pass", 75, adults=1, free=17),
                  tier("Individual", 110, adults=1, free=17),
                  tier("Family", 250, adults=2, kids=4, free=17)],
        "src": ["https://membership.moma.org/", "https://visit.moma.org/select"]},
    "ny-whitney": {"programs": [], "ga": ga(30, 0, 19),
        "tiers": [tier("Individual", 120, adults=1, free=19),
                  tier("Family", 200, adults=2, kids=4, free=19)],
        "src": ["https://whitney.org/support/membership"]},
    "ny-guggenheim": {"ga": ga(30, 0, 13),
        "tiers": [tier("Individual", 85, adults=1, free=13),
                  tier("Dual", 150, adults=2, free=13),
                  tier("Supporter", 300, ["NARM"], adults=2, kids=4, guests=2, free=13)],
        "src": ["https://www.guggenheim.org/membership"], "approx": True},
    "ny-amnh": {"programs": [], "ga": ga(28, 16, 3),
        "tiers": [tier("Individual", 110, adults=1, free=3),
                  tier("Family/Associate", 220, adults=2, kids=4, free=3)],
        "src": ["https://www.amnh.org/join-support"]},
    "ny-brooklyn-museum": {"ga": ga(18, 0, 19),
        "tiers": [tier("Individual", 90, adults=1, free=19),
                  tier("Dual", 150, adults=2, free=19),
                  tier("Enthusiast", 300, ["NARM"], adults=2, kids=4, guests=2, free=19)],
        "src": ["https://www.brooklynmuseum.org/support/membership",
                "https://www.brooklynmuseum.org/support/reciprocal"]},
    "ny-nyhs": {"ga": ga(24, 6, 5),
        "tiers": [tier("Individual", 85, adults=1, free=5),
                  tier("Family", 150, adults=2, kids=4, free=5),
                  tier("Patron", 300, ["NARM"], adults=2, kids=4, guests=2, free=5)],
        "src": ["https://www.nyhistory.org/join-and-give"], "approx": True},
    "ny-intrepid": {"ga": ga(38, 28, 5),
        "tiers": [tier("Family", 200, ["ASTC"], adults=2, kids=4, free=5)],
        "src": ["https://intrepidmuseum.org/plan-your-visit/visitor-information/tickets"], "approx": True},
    "ny-bronx-zoo": {"ga": ga(41.95, 31.95, 3),
        "tiers": [tier("Family Limited", 180, ["AZA"], adults=2, kids=4, free=3)],
        "src": ["https://bronxzoo.com/membership"]},
    "ny-aquarium": {"ga": ga(29.95, 25.95, 3),
        "tiers": [tier("Family", 120, ["AZA"], adults=2, kids=4, free=3)],
        "src": ["https://nyaquarium.com/membership", "https://nyaquarium.com/plan-your-visit/hours-and-rates"]},
    "ny-nybg": {"ga": ga(35, 15, 2),
        "tiers": [tier("Individual", 99, ["AHS"], adults=1, free=2),
                  tier("Family", 175, ["AHS"], adults=2, kids=4, free=2)],
        "src": ["https://www.nybg.org/join-support/membership/", "https://www.nybg.org/visit/admission/"]},
    "ny-bbg": {"ga": ga(22, 0, 12),
        "tiers": [tier("Individual", 75, ["AHS"], adults=1, free=12),
                  tier("Dual", 115, ["AHS"], adults=2, kids=4, free=12)],
        "src": ["https://www.bbg.org/support/join", "https://www.bbg.org/visit/hours"]},
    "ny-cmom": {"ga": ga(18, 18, 1),
        "tiers": [tier("Family", 225, ["ACM"], adults=2, kids=4, free=1)],
        "src": ["https://cmom.org/membership/"]},
    "ny-bcm": {"ga": ga(15, 15, 1),
        "tiers": [tier("Family", 150, ["ACM"], adults=2, kids=4, free=1)],
        "src": ["https://www.brooklynkids.org/join/"], "approx": True},
    "ny-nysci": {"ga": ga(22, 19, 2),
        "tiers": [tier("Satellite", 200, ["ASTC"], adults=2, kids=4, free=2)],
        "src": ["https://nysci.org/membership", "https://nysci.org/tickets"]},
    "ny-cooper-hewitt": {"programs": [], "ga": ga(22, 0, 19),
        "tiers": [tier("Individual", 90, adults=1, free=19),
                  tier("Design Insider", 350, adults=2, kids=4, free=19)],
        "src": ["https://www.cooperhewitt.org/membership/"]},
    "ny-mcny": {"ga": ga(20, 0, 20),
        "tiers": [tier("Individual", 80, adults=1, free=20),
                  tier("Dual", 125, ["NARM"], adults=2, free=20),
                  tier("Family", 175, ["NARM"], adults=2, kids=4, guests=2, free=20)],
        "src": ["https://www.mcny.org/membership"]},
    "ny-qbg": {"ga": ga(6, 2, 4),
        "tiers": [tier("Family", 60, ["AHS"], adults=2, kids=4, free=4)],
        "src": ["https://queensbotanical.org/membership/"], "approx": True},
    "ny-wave-hill": {"ga": ga(10, 4, 6),
        "tiers": [tier("Individual", 60, ["AHS"], adults=1, free=6),
                  tier("Family", 150, ["AHS"], adults=2, kids=4, guests=2, free=6)],
        "src": ["https://www.wavehill.org/support/membership"], "approx": True},
}

_RESOLVED_FLAGS = {"needs_manual", "js_only_page", "roster_page_conflict", "manually_verified"}


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
            approx = ov.get("approx", False)
            rec["general_admission"] = ov["ga"]
            rec["tiers"] = ov["tiers"]
            if "programs" in ov:
                rec["programs"] = ov["programs"]
            rec["source_urls"] = ov["src"]
            rec["confidence"] = 0.78 if approx else 0.9
            rec["last_verified"] = today
            rec["flags"] = [f for f in rec["flags"] if f not in _RESOLVED_FLAGS]
            for flag in (["web_sourced"] + (["price_approximate"] if approx else [])):
                if flag not in rec["flags"]:
                    rec["flags"].append(flag)
            cleared_ids.add(rec["id"])
        with open(path, "w") as f:
            json.dump(records, f, indent=2)
        print(f"applied web-sourced overrides -> {path}")

    rq_path = os.path.join(DATA_DIR, "review_queue.json")
    if os.path.exists(rq_path):
        with open(rq_path) as f:
            rq = json.load(f)
        remaining = [e for e in rq if e["id"] not in cleared_ids]
        with open(rq_path, "w") as f:
            json.dump(remaining, f, indent=2)
        print(f"review queue: {len(rq)} -> {len(remaining)} ({len(cleared_ids)} cleared)")


def main() -> None:
    argparse.ArgumentParser(description="Apply web-sourced overrides; clear review queue.").parse_args()
    apply_overrides()


if __name__ == "__main__":
    main()
