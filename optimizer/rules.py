"""Optimizer rules — pure functions shared in spirit with web/app.js.

Keep this logic deterministic and free of I/O so the Python reference and the client-side JS
can be checked for parity against a shared fixture.

Distance is haversine great-circle (the reciprocal-program rules are explicitly linear
radius, not driving distance).
"""
from __future__ import annotations

import math
from typing import Optional

ADULT_AGE = 18
EARTH_RADIUS_MILES = 3958.7613

FULL = "full_free"
PARTIAL_TYPES = {"fifty_percent", "discount_varies"}


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def split_household(ages: list[int], child_free_under_age: Optional[int]) -> tuple[int, int]:
    """Return (adults, paying_children) given a tier's free-child age."""
    free = child_free_under_age or 0
    adults = sum(1 for a in ages if a >= ADULT_AGE)
    children = sum(1 for a in ages if free <= a < ADULT_AGE)
    return adults, children


def tier_fits(tier: dict, ages: list[int], guests: int) -> bool:
    """Does this tier admit the whole household plus guests?

    Reciprocal headcount is bounded by the home tier, so the tier must seat everyone.
    Unknown (None) admit counts are treated permissively — we cannot prove they don't fit.
    Guests are charged against adult capacity (incl. named guest slots).
    """
    adults, children = split_household(ages, tier.get("child_free_under_age"))
    cap_adults = tier.get("adults_admitted")
    cap_children = tier.get("children_admitted")
    named = tier.get("named_guests_allowed") or 0
    ok = True
    if cap_adults is not None:
        ok = ok and (cap_adults + named) >= (adults + guests)
    if cap_children is not None:
        ok = ok and cap_children >= children
    return ok


def distance_clears(program: dict, home: tuple[float, float],
                    cand: tuple[float, float], target: tuple[float, float]) -> bool:
    """True if target clears the program's linear-radius exclusion.

    `distance_basis`: none -> always clears; residence -> vs home ZIP; home_institution ->
    vs purchasing institution; both -> must clear vs BOTH. (Blocked if within radius of any
    applicable point.)
    """
    d = program.get("distance_miles") or 0
    basis = program.get("distance_basis", "none")
    if d <= 0 or basis == "none":
        return True
    checks = []
    if basis in ("residence", "both"):
        checks.append(haversine(home[0], home[1], target[0], target[1]))
    if basis in ("home_institution", "both"):
        checks.append(haversine(cand[0], cand[1], target[0], target[1]))
    return all(dist >= d for dist in checks)


def resolved_reciprocity(target: dict, program_code: str, programs: dict) -> str:
    """The reciprocity_type the target grants for a program (per-institution override wins)."""
    override = (target.get("reciprocity_overrides") or {}).get(program_code)
    if override:
        return override
    return programs.get(program_code, {}).get("reciprocity_type", "varies")


def coverage_for(target: dict, cand_inst: dict, tier: dict, home: tuple[float, float],
                 programs: dict) -> dict:
    """Best coverage a (cand_inst, tier) gives for `target`.

    Returns {status, program, reason}. status in:
      own | full | partial | blocked_distance | no_program
    """
    home_ll = home
    cand_ll = (cand_inst["lat"], cand_inst["lng"])
    tgt_ll = (target["lat"], target["lng"])

    if cand_inst["id"] == target["id"]:
        return {"status": "own", "program": None, "reason": "own membership"}

    if "non_participating" in (target.get("flags") or []):
        return {"status": "no_program", "program": None, "reason": "target non-participating"}

    shared = set(tier.get("programs_unlocked") or []) & set(target.get("programs") or [])
    if not shared:
        return {"status": "no_program", "program": None, "reason": "no shared program"}

    best = {"status": "no_program", "program": None, "reason": "no shared program"}
    for p in shared:
        prog = programs.get(p, {})
        if not distance_clears(prog, home_ll, cand_ll, tgt_ll):
            if best["status"] in ("no_program",):
                best = {"status": "blocked_distance", "program": p,
                        "reason": f"within {prog.get('distance_miles')}mi exclusion ({p})"}
            continue
        rtype = resolved_reciprocity(target, p, programs)
        if rtype == FULL:
            return {"status": "full", "program": p, "reason": f"free via {p}"}
        if rtype in PARTIAL_TYPES and best["status"] not in ("full",):
            best = {"status": "partial", "program": p, "reason": f"{rtype} via {p}"}
    return best


def admission_cost(target: dict, ages: list[int], guests: int) -> float:
    """Full per-visit admission cost for the household + guests at a target."""
    ga = target.get("general_admission") or {}
    adult = ga.get("adult_price_usd")
    child = ga.get("child_price_usd")
    free = ga.get("child_free_under_age") or 0
    if adult is None:
        return 0.0
    child = child if child is not None else adult
    total = 0.0
    for a in ages:
        if a >= ADULT_AGE:
            total += adult
        elif a >= free:
            total += child
    total += guests * adult
    return total
