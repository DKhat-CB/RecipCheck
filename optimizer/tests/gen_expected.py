"""Emit the Python reference outputs (canonical projection) for the parity scenarios as JSON.

Used by parity.mjs; also importable. Run: python3 optimizer/tests/gen_expected.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from optimizer import model  # noqa: E402

HERE = os.path.dirname(__file__)


def project(out: dict) -> dict:
    return {
        "feasible": out.get("feasible"),
        "covered_all": out.get("covered_all"),
        "total_cost": out.get("total_cost"),
        "recommendation": sorted(
            f"{r['institution_id']}:{r['tier_name']}:{float(r['annual_price_usd']):g}"
            for r in out.get("recommendation", [])
        ),
        "coverage": {c["id"]: c["status"] for c in out.get("coverage", [])},
        "pre_covered": out.get("pre_covered", []),
        "savings": (
            {
                "total_avoided": out["savings"]["total_avoided"],
                "membership_cost": out["savings"]["membership_cost"],
                "net_savings": out["savings"]["net_savings"],
            }
            if out.get("savings") else None
        ),
    }


def main() -> None:
    with open(os.path.join(HERE, "fixture_dataset.json")) as f:
        dataset = json.load(f)
    with open(os.path.join(HERE, "parity_scenarios.json")) as f:
        scenarios = json.load(f)
    result = {sc["name"]: project(model.optimize(dataset, sc["inputs"])) for sc in scenarios}
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
