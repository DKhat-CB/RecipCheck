"""Human-fill lane — turn a REAL membership page into a verified record.

This is the reliability backstop for institutions the automated crawler can't reach (WAF
blocks, JS-only pages) or gets wrong. A person pastes the institution's actual page text
(copied from the live site, or OCR'd from a screenshot) into a file; this runs the SAME
schema-enforced Gemini extractor the crawler uses, shows the result, and — with --apply —
writes it into the metro dataset stamped with provenance (source_url, verified_date,
verified_by=human_page). No hand-typing of numbers, which is where transcription errors
crept in.

Usage:
  python -m scraper.fill_from_page --id mont-mba --page page.txt \
      --source https://www.montereybayaquarium.org/visit/admission-tickets
  # review the printed extraction + diff, then re-run with --apply to commit it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os

from .config import DATA_DIR, load_dotenv
from .extract import extract
from .rosters import INSTITUTIONS_DIR

_RESOLVED_FLAGS = {"needs_manual", "js_only_page", "roster_page_conflict",
                   "manually_verified", "web_sourced", "price_approximate", "stale"}


def _find_record(inst_id: str) -> tuple[str, list, dict]:
    for metro in ("bay_area", "nyc"):
        path = os.path.join(INSTITUTIONS_DIR, f"{metro}.json")
        with open(path) as f:
            records = json.load(f)
        for rec in records:
            if rec["id"] == inst_id:
                return path, records, rec
    raise SystemExit(f"institution id not found: {inst_id}")


def _fmt_tiers(tiers: list) -> str:
    return "\n".join(
        f"    - {t['name']}: ${t['annual_price_usd']}  programs={t['programs_unlocked']}  "
        f"adults={t.get('adults_admitted')} kids={t.get('children_admitted')} "
        f"guests={t.get('named_guests_allowed')} child_free<{t.get('child_free_under_age')}"
        for t in tiers
    ) or "    (none)"


def main() -> None:
    ap = argparse.ArgumentParser(description="Fill an institution record from real page text.")
    ap.add_argument("--id", required=True, help="institution id, e.g. mont-mba")
    ap.add_argument("--page", required=True, help="path to a text file with the page content")
    ap.add_argument("--source", required=True, help="the page URL this came from")
    ap.add_argument("--model", default=None, help="override extraction model")
    ap.add_argument("--apply", action="store_true", help="write the result into the dataset")
    args = ap.parse_args()

    load_dotenv()
    path, records, rec = _find_record(args.id)
    with open(args.page, encoding="utf-8") as f:
        page_text = f.read().strip()
    if not page_text:
        raise SystemExit("page file is empty")

    believed = rec.get("programs", [])
    model = args.model or "gemini-2.5-flash"
    result = extract(page_text, rec["name"], believed, model=model).model_dump()

    print(f"\n=== extracted for {rec['name']} ({args.id}) via {model} ===")
    print(f"confidence: {result['confidence']:.2f}   needs_manual: {result['needs_manual']}")
    print(f"general_admission: {result['general_admission']}")
    print("tiers:")
    print(_fmt_tiers(result["tiers"]))
    if result.get("notes"):
        print(f"notes: {result['notes']}")

    print("\n--- current record (for comparison) ---")
    print(f"general_admission: {rec.get('general_admission')}")
    print("tiers:")
    print(_fmt_tiers(rec.get("tiers", [])))

    if not args.apply:
        print("\n(dry run — re-run with --apply to write this into the dataset)")
        return

    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    rec["tiers"] = result["tiers"]
    rec["general_admission"] = result["general_admission"]
    rec["confidence"] = float(result["confidence"])
    rec["last_verified"] = today
    rec["source_urls"] = [args.source]
    rec["verified_by"] = "human_page"
    rec["flags"] = [fl for fl in rec.get("flags", []) if fl not in _RESOLVED_FLAGS]
    if result["needs_manual"] and "needs_manual" not in rec["flags"]:
        rec["flags"].append("needs_manual")
    if "human_verified" not in rec["flags"]:
        rec["flags"].append("human_verified")
    with open(path, "w") as f:
        json.dump(records, f, indent=2)
    print(f"\napplied -> {path}  (verified_by=human_page, last_verified={today})")
    print("now run:  python -m scraper.orchestrate --compile")


if __name__ == "__main__":
    main()
