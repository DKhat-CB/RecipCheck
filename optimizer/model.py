"""Optimizer model — candidate generation, coverage, objectives, savings.

Reference Python implementation. With <=5 targets and a membership cap of 2, brute force over
singles + pairs is a few thousand evaluations, so no ILP is needed (the client-side JS in
web/app.js mirrors this logic; optimizer/tests checks parity on a shared fixture).

`optimize(dataset, inputs)` is the single entry point. `inputs` keys:
  ages: list[int]
  home: [lat, lng]                 (resolved from ZIP centroid by the caller)
  guests: int
  targets: [{id, visits_per_year}]
  objective: "must_cover_all" | "prioritize_frequency"
  membership_cap: int
  anchor: {mode: "anchor"|"cheapest", institution_id?}
  existing: [institution_id, ...]
  value_unplanned: bool
  visit_window_months: int
"""
from __future__ import annotations

from itertools import combinations
from typing import Optional

from . import rules


# --------------------------------------------------------------------------- helpers
def _index(dataset: dict) -> dict[str, dict]:
    return {i["id"]: i for i in dataset["institutions"]}


def _reciprocity_bearing_tiers(inst: dict) -> list[dict]:
    return [t for t in (inst.get("tiers") or []) if t.get("programs_unlocked")]


def _candidate_tiers(inst: dict, ages: list[int], guests: int) -> list[dict]:
    """Tiers of `inst` that seat the whole household (escalation handled by filtering)."""
    return [t for t in (inst.get("tiers") or [])
            if t.get("annual_price_usd") is not None and rules.tier_fits(t, ages, guests)]


class Candidate:
    __slots__ = ("inst", "tier")

    def __init__(self, inst: dict, tier: dict):
        self.inst = inst
        self.tier = tier

    @property
    def price(self) -> float:
        return float(self.tier["annual_price_usd"])

    @property
    def id(self) -> str:
        return self.inst["id"]

    def __repr__(self) -> str:
        return f"<{self.inst['id']}:{self.tier['name']} ${self.price:.0f}>"


def build_candidates(dataset: dict, inputs: dict, targets: list[dict]) -> list[Candidate]:
    """Reciprocity-bearing tiers across the dataset + every target's own fitting tiers."""
    ages, guests = inputs["ages"], inputs.get("guests", 0)
    cands: dict[tuple[str, str], Candidate] = {}
    # reciprocity-bearing tiers anywhere
    for inst in dataset["institutions"]:
        for tier in _reciprocity_bearing_tiers(inst):
            if tier.get("annual_price_usd") is None or not rules.tier_fits(tier, ages, guests):
                continue
            cands[(inst["id"], tier["name"])] = Candidate(inst, tier)
    # each target's own membership (sometimes you just buy the target)
    for tgt in targets:
        for tier in _candidate_tiers(tgt, ages, guests):
            cands[(tgt["id"], tier["name"])] = Candidate(tgt, tier)
    return list(cands.values())


# --------------------------------------------------------------------------- coverage
def covers(cand: Candidate, target: dict, home: tuple[float, float], programs: dict) -> dict:
    return rules.coverage_for(target, cand.inst, cand.tier, home, programs)


def _set_coverage(cset: list[Candidate], targets: list[dict], home, programs,
                  pre_covered: set[str]) -> dict[str, dict]:
    """Best coverage per target id across a candidate set (+ pre-covered existing memberships)."""
    rank = {"own": 3, "full": 3, "partial": 2, "blocked_distance": 1, "no_program": 0}
    result: dict[str, dict] = {}
    for tgt in targets:
        if tgt["id"] in pre_covered:
            result[tgt["id"]] = {"status": "full", "program": None, "reason": "already held"}
            continue
        best = {"status": "no_program", "program": None, "reason": "no coverage"}
        for cand in cset:
            cov = covers(cand, tgt, home, programs)
            if rank[cov["status"]] > rank[best["status"]]:
                best = cov
        result[tgt["id"]] = best
    return result


def _is_covered_free(status: str) -> bool:
    return status in ("full", "own")


# --------------------------------------------------------------------------- breadth (tiebreak)
def _breadth(cset: list[Candidate], dataset: dict, home, programs) -> int:
    """Distinct institutions in the dataset reachable free by this set (unplanned-visit value)."""
    reach: set[str] = set()
    for inst in dataset["institutions"]:
        for cand in cset:
            cov = rules.coverage_for(inst, cand.inst, cand.tier, home, programs)
            if _is_covered_free(cov["status"]):
                reach.add(inst["id"])
                break
    return len(reach)


# --------------------------------------------------------------------------- savings
def compute_savings(cset: list[Candidate], targets: list[dict], coverage: dict[str, dict],
                    inputs: dict, idx: dict) -> dict:
    ages, guests = inputs["ages"], inputs.get("guests", 0)
    window = inputs.get("visit_window_months", 12)
    factor = window / 12.0
    per_target = []
    total_avoided = 0.0
    for tgt in targets:
        cov = coverage[tgt["id"]]
        visits = tgt.get("visits_per_year", 0) * factor
        full = rules.admission_cost(idx[tgt["id"]], ages, guests)
        if cov["status"] in ("full", "own"):
            value = visits * full
        elif cov["status"] == "partial":
            value = visits * full * 0.5
        else:
            value = 0.0
        total_avoided += value
        per_target.append({
            "id": tgt["id"], "name": idx[tgt["id"]]["name"],
            "visits_per_year": tgt.get("visits_per_year", 0),
            "per_visit_admission": round(full, 2),
            "status": cov["status"], "avoided_value": round(value, 2),
        })
    cost = sum(c.price for c in cset)
    return {
        "per_target": per_target,
        "total_avoided": round(total_avoided, 2),
        "membership_cost": round(cost, 2),
        "net_savings": round(total_avoided - cost, 2),
    }


# --------------------------------------------------------------------------- main
def optimize(dataset: dict, inputs: dict) -> dict:
    programs = dataset["programs"]
    idx = _index(dataset)
    home = tuple(inputs["home"])
    cap = max(1, inputs.get("membership_cap", 2))
    objective = inputs.get("objective", "must_cover_all")
    anchor = inputs.get("anchor", {"mode": "cheapest"})
    value_unplanned = inputs.get("value_unplanned", False)

    targets = [idx[t["id"]] for t in inputs["targets"] if t["id"] in idx]
    for t in inputs["targets"]:
        targets_lookup = next((x for x in targets if x["id"] == t["id"]), None)
        if targets_lookup is not None:
            targets_lookup["visits_per_year"] = t.get("visits_per_year", 0)

    # pre-cover existing memberships (their own institution + reciprocal reach)
    existing_ids = set(inputs.get("existing", []))
    pre_covered: set[str] = set()
    for tgt in targets:
        for eid in existing_ids:
            einst = idx.get(eid)
            if not einst:
                continue
            for tier in _reciprocity_bearing_tiers(einst) or [{}]:
                cov = rules.coverage_for(tgt, einst, tier or {}, home, programs)
                if _is_covered_free(cov["status"]) or tgt["id"] == eid:
                    pre_covered.add(tgt["id"])

    candidates = build_candidates(dataset, inputs, targets)

    # enumerate the empty set (buy nothing — valid when existing memberships pre-cover
    # everything), singles, and pairs up to the cap
    sets: list[list[Candidate]] = [[]]
    sets += [[c] for c in candidates]
    if cap >= 2:
        seen_ids = set()
        for a, b in combinations(candidates, 2):
            if a.id == b.id:
                continue
            key = tuple(sorted((f"{a.id}:{a.tier['name']}", f"{b.id}:{b.tier['name']}")))
            if key in seen_ids:
                continue
            seen_ids.add(key)
            sets.append([a, b])

    def evaluate(cset):
        coverage = _set_coverage(cset, targets, home, programs, pre_covered)
        covered_free = [t for t in targets if _is_covered_free(coverage[t["id"]]["status"])]
        visit_value = sum(t.get("visits_per_year", 0) for t in covered_free)
        cost = sum(c.price for c in cset)
        return coverage, covered_free, visit_value, cost

    scored = []
    for cset in sets:
        coverage, covered_free, visit_value, cost = evaluate(cset)
        scored.append((cset, coverage, covered_free, visit_value, cost))

    n_targets = len(targets)

    def anchor_hit(cset):
        if anchor.get("mode") == "anchor" and anchor.get("institution_id"):
            return any(c.id == anchor["institution_id"] for c in cset)
        return False

    if objective == "must_cover_all":
        full_sets = [s for s in scored if len(s[2]) == n_targets and n_targets > 0]
        pool = full_sets if full_sets else []
        if pool:
            # primary: min cost; tiebreakers: breadth (opt-in), anchor, fewer cards
            def key(s):
                cset, _, _, _, cost = s
                breadth = _breadth(cset, dataset, home, programs) if value_unplanned else 0
                return (cost, -breadth, 0 if anchor_hit(cset) else 1, len(cset))
            pool.sort(key=key)
            best = pool[0]
            alternatives = pool[1:4]
        else:
            # no full-coverage set; fall back to max visit-value then min cost
            scored.sort(key=lambda s: (-s[3], s[4]))
            best = scored[0] if scored else (None,) * 5
            alternatives = scored[1:4]
    else:  # prioritize_frequency
        def key(s):
            cset, _, _, visit_value, cost = s
            breadth = _breadth(cset, dataset, home, programs) if value_unplanned else 0
            return (-visit_value, cost, -breadth, 0 if anchor_hit(cset) else 1, len(cset))
        scored.sort(key=key)
        best = scored[0] if scored else (None,) * 5
        alternatives = scored[1:4]

    return _format_output(best, alternatives, targets, idx, inputs, programs, dataset, pre_covered)


def _coverage_rows(coverage, targets, idx, home, programs, best_set):
    rows = []
    for tgt in targets:
        cov = coverage[tgt["id"]]
        rows.append({
            "id": tgt["id"], "name": idx[tgt["id"]]["name"],
            "status": cov["status"], "program": cov.get("program"),
            "reason": cov.get("reason"),
            "flags": idx[tgt["id"]].get("flags", []),
        })
    return rows


def _format_output(best, alternatives, targets, idx, inputs, programs, dataset, pre_covered):
    if not best or best[0] is None:
        return {"feasible": False, "reason": "no candidates", "coverage": [], "recommendation": []}
    cset, coverage, covered_free, visit_value, cost = best
    home = tuple(inputs["home"])
    savings = compute_savings(cset, targets, coverage, inputs, idx)
    rec = [{
        "institution_id": c.id, "institution_name": c.inst["name"],
        "tier_name": c.tier["name"], "annual_price_usd": c.price,
        "programs_unlocked": c.tier.get("programs_unlocked", []),
        "flags": c.inst.get("flags", []),
    } for c in cset]

    n_targets = len(targets)
    covered_all = len(covered_free) == n_targets and n_targets > 0
    uncovered = [
        {"id": t["id"], "name": idx[t["id"]]["name"],
         "status": coverage[t["id"]]["status"], "reason": coverage[t["id"]]["reason"]}
        for t in targets if not _is_covered_free(coverage[t["id"]]["status"])
    ]

    alt_out = []
    for a in alternatives:
        acset, acov, acovered, avv, acost = a
        alt_out.append({
            "recommendation": [{"institution_name": c.inst["name"], "tier_name": c.tier["name"],
                                "annual_price_usd": c.price} for c in acset],
            "total_cost": round(acost, 2),
            "covered_count": len(acovered),
        })

    recommended_flags = sorted({f for c in cset for f in c.inst.get("flags", [])
                                if f in ("stale", "needs_manual", "non_participating",
                                         "possibly_closed", "js_only_page")})
    return {
        "feasible": True,
        "objective": inputs.get("objective", "must_cover_all"),
        "covered_all": covered_all,
        "recommendation": rec,
        "total_cost": round(cost, 2),
        "coverage": _coverage_rows(coverage, targets, idx, home, programs, cset),
        "uncovered": uncovered,
        "savings": savings,
        "alternatives": alt_out,
        "pre_covered": sorted(pre_covered),
        "flags": recommended_flags,
        "build": dataset.get("build"),
    }
