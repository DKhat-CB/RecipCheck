"""Unit tests for the pure rule functions."""
import json
import os

import pytest

from optimizer import rules

FIX = os.path.join(os.path.dirname(__file__), "fixture_dataset.json")
with open(FIX) as f:
    DATASET = json.load(f)
IDX = {i["id"]: i for i in DATASET["institutions"]}
PROGRAMS = DATASET["programs"]
HOME_SF = (37.7749, -122.4194)


def test_haversine_known_distance():
    # SF -> Sacramento ~ 75 mi
    d = rules.haversine(37.7749, -122.4194, 38.5816, -121.4944)
    assert 70 < d < 90


def test_split_household_free_age():
    adults, kids = rules.split_household([40, 38, 5, 2], child_free_under_age=3)
    assert adults == 2
    assert kids == 1  # age 5 counts; age 2 is free


def test_tier_fits_escalates_on_guests():
    dual = IDX["small-tier-art"]["tiers"][0]      # adults 2, children 0, no guests
    household = IDX["small-tier-art"]["tiers"][1]  # adults 2, children 4, 2 guests
    ages = [40, 38, 8]
    assert not rules.tier_fits(dual, ages, guests=0)       # a child present, dual seats 0 kids
    assert rules.tier_fits(household, ages, guests=0)
    # guests push past adult capacity of the dual tier
    assert not rules.tier_fits(dual, [40, 38], guests=2)
    assert rules.tier_fits(household, [40, 38], guests=2)


def test_astc_90_mile_blocks_local_science_center():
    # A far ASTC card cannot reach a science center within 90mi of home (both-basis rule).
    far = IDX["far-sci"]
    sf_sci = IDX["sf-sci"]
    cov = rules.coverage_for(sf_sci, far, far["tiers"][0], HOME_SF, PROGRAMS)
    assert cov["status"] == "blocked_distance"
    assert cov["program"] == "ASTC"


def test_narm_has_no_distance_rule():
    a = IDX["sf-art-a"]
    b = IDX["sac-art-b"]
    cov = rules.coverage_for(b, a, a["tiers"][1], HOME_SF, PROGRAMS)
    assert cov["status"] == "full"
    assert cov["program"] == "NARM"


def test_aza_resolves_partial():
    far_zoo = IDX["far-zoo"]
    sf_zoo = IDX["sf-zoo"]
    cov = rules.coverage_for(sf_zoo, far_zoo, far_zoo["tiers"][0], HOME_SF, PROGRAMS)
    assert cov["status"] == "partial"  # AZA override = fifty_percent


def test_own_membership_trivially_covers():
    a = IDX["sf-art-a"]
    cov = rules.coverage_for(a, a, a["tiers"][1], HOME_SF, PROGRAMS)
    assert cov["status"] == "own"


def test_admission_cost_counts_free_children():
    a = IDX["sf-art-a"]  # adult 25, child 15, free under 3
    cost = rules.admission_cost(a, ages=[40, 38, 5, 2], guests=0)
    assert cost == pytest.approx(25 + 25 + 15)  # two adults + one paying child; toddler free
