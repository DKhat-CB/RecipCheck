"""Orchestration — caching, hashing, politeness, scheduling, compile.

This is how re-scraping stays cheap: raw HTML is cached at data/raw_cache/{id}.html with a
sidecar {id}.meta.json holding {url, fetched_at, membership_section_hash, extraction}. On a
re-run, an unchanged section hash means the Gemini call is skipped and the prior extraction
reused.

CLI:
  python -m scraper.orchestrate --metro bay_area      # scrape one metro
  python -m scraper.orchestrate --metro nyc
  python -m scraper.orchestrate --metro all
  python -m scraper.orchestrate --compile             # merge -> web/dataset.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import time
from urllib.parse import urlparse

from . import membership_pages as mp
from . import validate
from .config import DATA_DIR, ROOT, load_config, load_dotenv
from .extract import extract
from .rosters import INSTITUTIONS_DIR, build_skeletons, write_skeletons

RAW_CACHE = os.path.join(DATA_DIR, "raw_cache")
REVIEW_QUEUE = os.path.join(DATA_DIR, "review_queue.json")
WEB_DATASET = os.path.join(ROOT, "web", "dataset.json")

_last_host_fetch: dict[str, float] = {}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def _polite_wait(url: str, cfg: dict) -> None:
    host = urlparse(url).netloc
    lo, hi = cfg["crawl"]["per_host_delay_seconds"]
    delay = robots_delay = mp.robots_crawl_delay(url, cfg["crawl"]["user_agent"])
    wait = max(robots_delay or 0, random.uniform(lo, hi))
    last = _last_host_fetch.get(host)
    if last is not None:
        elapsed = time.time() - last
        if elapsed < wait:
            time.sleep(wait - elapsed)
    _last_host_fetch[host] = time.time()


def _cache_paths(inst_id: str) -> tuple[str, str]:
    return (os.path.join(RAW_CACHE, f"{inst_id}.html"),
            os.path.join(RAW_CACHE, f"{inst_id}.meta.json"))


def _load_meta(inst_id: str) -> dict | None:
    _, meta_path = _cache_paths(inst_id)
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            return json.load(f)
    return None


def _save_cache(inst_id: str, url: str, html: str, section_hash: str, extraction: dict | None) -> None:
    os.makedirs(RAW_CACHE, exist_ok=True)
    html_path, meta_path = _cache_paths(inst_id)
    with open(html_path, "w") as f:
        f.write(html or "")
    with open(meta_path, "w") as f:
        json.dump({
            "url": url,
            "fetched_at": _now(),
            "membership_section_hash": section_hash,
            "extraction": extraction,
        }, f, indent=2)


def _apply_extraction(record: dict, extraction: dict, fetch_status: str) -> None:
    record["tiers"] = extraction.get("tiers", [])
    record["general_admission"] = extraction.get("general_admission")
    record["confidence"] = float(extraction.get("confidence", 0.0))
    record["last_verified"] = _now()
    if extraction.get("needs_manual"):
        if "needs_manual" not in record["flags"]:
            record["flags"].append("needs_manual")
    if fetch_status == "js_only" and "js_only_page" not in record["flags"]:
        record["flags"].append("js_only_page")
    # roster vs page cross-check
    for flag in validate.cross_check(record, extraction):
        if flag not in record["flags"]:
            record["flags"].append(flag)


def scrape_metro(metro: str, cfg: dict, force: bool = False) -> dict:
    """Scrape one metro. Returns {committed, review, skipped} counts."""
    load_dotenv()
    path = os.path.join(INSTITUTIONS_DIR, f"{metro}.json")
    with open(path) as f:
        records = json.load(f)

    review: list[dict] = []
    committed = skipped = extracted = failed = 0
    model = cfg["extraction"]["default_model"]
    retry_model = cfg["extraction"]["retry_model"]

    for rec in records:
        url = rec["membership_url"]
        believed = rec.get("programs", [])
        print(f"  · {rec['id']:<20} ", end="", flush=True)

        if not mp.robots_allows(url, cfg["crawl"]["user_agent"]):
            print("robots-disallowed -> review")
            review.append(validate.review_entry(rec, None, "robots disallowed", "", "blocked"))
            if "needs_manual" not in rec["flags"]:
                rec["flags"].append("needs_manual")
            continue

        _polite_wait(url, cfg)
        fr = mp.fetch(url, timeout=cfg["crawl"]["timeout_seconds"])
        section_text = mp.isolate_membership_text(fr.html) if fr.html else ""
        new_hash = mp.section_hash(section_text) if section_text else ""

        meta = _load_meta(rec["id"])
        if (not force and meta and meta.get("membership_section_hash") == new_hash
                and new_hash and meta.get("extraction")):
            extraction = meta["extraction"]
            print(f"unchanged hash -> reuse ({fr.method})")
            skipped += 1
        elif fr.status in ("blocked", "js_only", "error") or not section_text:
            print(f"{fr.status} ({fr.method}) {fr.note} -> review")
            review.append(validate.review_entry(rec, None, f"fetch {fr.status}: {fr.note}",
                                                 section_text, fr.status))
            if fr.status == "js_only" and "js_only_page" not in rec["flags"]:
                rec["flags"].append("js_only_page")
            if "needs_manual" not in rec["flags"]:
                rec["flags"].append("needs_manual")
            _save_cache(rec["id"], url, fr.html, new_hash, None)
            failed += 1
            continue
        else:
            try:
                result = extract(section_text, rec["name"], believed, model=model)
                extraction = result.model_dump()
                # low-confidence retry with stronger free model
                if (extraction.get("confidence", 0.0) < cfg["extraction"]["confidence_auto_commit"]
                        or extraction.get("needs_manual")):
                    retry = extract(section_text, rec["name"], believed, model=retry_model)
                    if retry.confidence > extraction["confidence"]:
                        extraction = retry.model_dump()
                extracted += 1
                print(f"extracted conf={extraction['confidence']:.2f} ({fr.method})")
            except Exception as e:  # noqa: BLE001
                print(f"extract-error -> review: {e}")
                review.append(validate.review_entry(rec, None, f"extraction error: {e}",
                                                     section_text, fr.status))
                if "needs_manual" not in rec["flags"]:
                    rec["flags"].append("needs_manual")
                _save_cache(rec["id"], url, fr.html, new_hash, None)
                failed += 1
                continue
            _save_cache(rec["id"], url, fr.html, new_hash, extraction)

        _apply_extraction(rec, extraction, fr.status)
        auto, reason = validate.route(rec, extraction, fr.status)
        if auto:
            committed += 1
        else:
            review.append(validate.review_entry(rec, extraction, reason, section_text, fr.status))

    with open(path, "w") as f:
        json.dump(records, f, indent=2)
    _merge_review_queue(metro, review)
    print(f"  {metro}: committed={committed} review={len(review)} reuse={skipped} "
          f"extracted={extracted} failed={failed}")
    return {"committed": committed, "review": len(review), "skipped": skipped}


def _merge_review_queue(metro: str, entries: list[dict]) -> None:
    existing = []
    if os.path.exists(REVIEW_QUEUE):
        with open(REVIEW_QUEUE) as f:
            existing = [e for e in json.load(f) if e.get("metro") != metro]
    with open(REVIEW_QUEUE, "w") as f:
        json.dump(existing + entries, f, indent=2)


def compile_dataset(cfg: dict) -> None:
    """Merge per-metro institution files into web/dataset.json with a build stamp."""
    with open(os.path.join(DATA_DIR, "programs.json")) as f:
        programs = json.load(f)
    metros = {}
    institutions = []
    for metro in cfg["metros"]:
        path = os.path.join(INSTITUTIONS_DIR, f"{metro}.json")
        with open(path) as f:
            recs = json.load(f)
        institutions.extend(recs)
        metros[metro] = cfg["metros"][metro]
    build = {
        "build_id": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S"),
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stale_after_days": cfg["maintenance"]["stale_after_days"],
    }
    os.makedirs(os.path.dirname(WEB_DATASET), exist_ok=True)
    with open(WEB_DATASET, "w") as f:
        json.dump({"build": build, "programs": programs, "metros": metros,
                   "institutions": institutions}, f, indent=2)
    print(f"compiled {len(institutions)} institutions -> {WEB_DATASET} (build {build['build_id']})")


def main() -> None:
    ap = argparse.ArgumentParser(description="RecipCheck scraper orchestrator.")
    ap.add_argument("--metro", choices=["bay_area", "nyc", "all"], help="scrape a metro")
    ap.add_argument("--compile", action="store_true", help="compile web/dataset.json")
    ap.add_argument("--force", action="store_true", help="ignore cache, re-extract")
    ap.add_argument("--skeletons", action="store_true", help="(re)build Tier-1 skeletons first")
    args = ap.parse_args()
    cfg = load_config()

    if args.skeletons:
        write_skeletons(build_skeletons(cfg))
    if args.metro:
        metros = list(cfg["metros"]) if args.metro == "all" else [args.metro]
        for m in metros:
            print(f"== scraping {m} ==")
            scrape_metro(m, cfg, force=args.force)
    if args.compile:
        compile_dataset(cfg)
    if not (args.metro or args.compile or args.skeletons):
        ap.print_help()


if __name__ == "__main__":
    main()
