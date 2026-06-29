"""Integration tests for the optimizer against the shared fixture dataset."""
import json
import os

from optimizer import model

FIX = os.path.join(os.path.dirname(__file__), "fixture_dataset.json")
with open(FIX) as f:
    DATASET = json.load(f)
HOME_SF = [37.7749, -122.4194]


def base_inputs(**over):
    inp = {
        "ages": [40, 38, 8],
        "home": HOME_SF,
        "guests": 0,
        "targets": [],
        "objective": "must_cover_all",
        "membership_cap": 2,
        "anchor": {"mode": "cheapest"},
        "existing": [],
        "value_unplanned": False,
        "visit_window_months": 12,
    }
    inp.update(over)
    return inp


def rec_ids(out):
    return {r["institution_id"] for r in out["recommendation"]}


def test_local_science_center_is_90mi_blocked_and_must_be_joined_directly():
    out = model.optimize(DATASET, base_inputs(targets=[{"id": "sf-sci", "visits_per_year": 4}]))
    assert out["covered_all"] is True
    assert rec_ids(out) == {"sf-sci"}          # only its own membership reaches it
    assert out["total_cost"] == 140
    cov = {c["id"]: c for c in out["coverage"]}
    assert cov["sf-sci"]["status"] == "own"


def test_two_cards_when_targets_span_programs():
    out = model.optimize(DATASET, base_inputs(
        targets=[{"id": "sac-art-b", "visits_per_year": 3},
                 {"id": "sf-moma2", "visits_per_year": 3}]))
    assert out["covered_all"] is True
    assert len(out["recommendation"]) == 2
    assert "sf-moma2" in rec_ids(out)          # only MARP source for sf-moma2
    assert out["total_cost"] == 280            # sac-art-b $120 + sf-moma2 $160


def test_guests_force_tier_escalation():
    # 2 adults + 2 guests = 4 adult slots; sac-art-b own (2+1) and sf-art-a (2+0) cannot seat
    # them, so a NARM card with enough guest capacity must be chosen instead.
    out = model.optimize(DATASET, base_inputs(
        ages=[40, 38], guests=2,
        targets=[{"id": "sac-art-b", "visits_per_year": 2}]))
    assert out["covered_all"] is True
    rec = out["recommendation"][0]
    assert rec["institution_id"] == "small-tier-art"
    assert rec["tier_name"] == "Household"     # escalated past the cheaper Dual (seats no guests/kids)


def test_fifty_percent_only_target_breaks_full_coverage():
    # Two AZA targets, one card: AZA is 50%, so neither can be *fully* covered via the other.
    out = model.optimize(DATASET, base_inputs(
        membership_cap=1,
        targets=[{"id": "sf-zoo", "visits_per_year": 3},
                 {"id": "far-zoo", "visits_per_year": 3}]))
    assert out["covered_all"] is False
    statuses = {c["id"]: c["status"] for c in out["coverage"]}
    # the unbought zoo is reachable only at 50% (partial) or is its own — never both full
    assert "partial" in statuses.values()


def test_prioritize_frequency_drops_low_frequency_target():
    out = model.optimize(DATASET, base_inputs(
        objective="prioritize_frequency", membership_cap=1,
        targets=[{"id": "sac-art-b", "visits_per_year": 10},
                 {"id": "sf-sci", "visits_per_year": 1}]))
    statuses = {c["id"]: c["status"] for c in out["coverage"]}
    # the high-frequency NARM target wins the single card; the local science center is dropped
    assert statuses["sac-art-b"] in ("full", "own")
    assert statuses["sf-sci"] not in ("full", "own")


def test_existing_membership_pre_covers_residual():
    out = model.optimize(DATASET, base_inputs(
        existing=["sf-art-a"],
        targets=[{"id": "sac-art-b", "visits_per_year": 2}]))
    assert out["covered_all"] is True
    assert "sac-art-b" in out["pre_covered"]
    assert out["total_cost"] == 0              # nothing new needs buying


def test_savings_math_nets_membership_cost():
    out = model.optimize(DATASET, base_inputs(
        targets=[{"id": "sac-art-b", "visits_per_year": 4}]))
    s = out["savings"]
    # admission for 2 adults + 1 child (age 8) at sac-art-b: 20+20+12 = 52; x4 visits = 208
    assert s["total_avoided"] == 208.0
    assert s["net_savings"] == round(208.0 - out["total_cost"], 2)
