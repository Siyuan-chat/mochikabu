import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("analyze", ROOT / "scripts" / "analyze.py")
analyze = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analyze)

class PlanTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((ROOT / "examples/config.example.json").read_text())
        self.raw = json.loads((ROOT / "examples/holdings_snapshot.example.json").read_text())

    def test_holdings_normalization(self):
        out = analyze.normalize_holdings(self.raw)
        self.assertAlmostEqual(out["shares_current_basis"], 21)
        self.assertAlmostEqual(out["personal_cash_cost_per_share"], 20000 / 21)
        self.assertEqual(out["validation_warnings"], [])

    def test_dcf_units(self):
        out = analyze.dcf_value({"fcf_billion": [1], "wacc": .1, "terminal_growth": 0, "net_debt_billion": 0, "shares_million_post_split": 10})
        self.assertAlmostEqual(out["fair_value_per_share"], 1000)

    def test_different_plan_schedule(self):
        cfg = dict(self.cfg, currency="JPY", contribution_start_date="2026-11-01", target_date="2027-01-31", incentive_rate=0.2, bonus_months=[1], dividend_reinvest=False)
        out = analyze.simulate_plan({"shares_current_basis": 0, "personal_contribution": 0, "company_incentive": 0}, cfg, 10, 100, 50)
        self.assertEqual(out["months"], 3)
        self.assertEqual(out["bonus_count"], 1)
        self.assertAlmostEqual(out["final_shares"], 42)
        self.assertAlmostEqual(out["final_personal_cash"], 350)

    def test_jpy_only(self):
        analyze.validate_currency({})
        analyze.validate_currency({"currency": "JPY"})
        with self.assertRaisesRegex(ValueError, "requires JPY"):
            analyze.validate_currency({"currency": "USD"})

    def test_optional_increase_cap(self):
        rows = [{"monthly": 100, "minimum_share_goal": False, "cost_goal": True, "soft_band": False}, {"monthly": 300, "minimum_share_goal": True, "cost_goal": True, "soft_band": True}]
        self.assertEqual(analyze.recommend_candidate(rows, 100, float("inf"))["selected_monthly"], 300)
        self.assertEqual(analyze.recommend_candidate(rows, 100, 0)["selected_monthly"], 100)

if __name__ == "__main__":
    unittest.main()
