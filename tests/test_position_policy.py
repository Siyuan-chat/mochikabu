import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from position_policy import decide, residency


class PositionTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "position": {"lifecycle_state": "employee", "thesis_status": "intact"},
            "valuation_policy": {"accumulation_bands": {"extreme": .6, "strong": .75, "normal": .9},
                                 "trim_bands": {"watch": 1.1, "partial": 1.4, "major": 1.7}},
            "margin_of_safety": .2, "incentive_rate": .2, "incentive_tax_rate": .5}
        self.fv = {"fair_value_per_share": 100, "bear_fv": 80}

    def test_lifecycle_and_boundary(self):
        employee = decide(self.config, self.fv, 88, "consider_increase")
        self.assertAlmostEqual(employee["effective_price"], 80)
        self.assertEqual(employee["contribution_state"], "ACCUMULATE")
        self.config["position"]["lifecycle_state"] = "former_employee"
        former = decide(self.config, self.fv, 88)
        self.assertEqual(former["holding_state"], "LONG_TERM_HOLD")
        self.assertIsNone(former["contribution_state"])
        self.assertEqual(former["effective_price"], 88)
        self.assertEqual(decide(self.config, self.fv, 140)["holding_state"], "PARTIAL_TRIM")
        self.config["position"]["thesis_status"] = "broken"
        self.assertEqual(decide(self.config, self.fv, 180)["holding_state"], "THESIS_REVIEW")

    def test_residency_vintages_and_actual_fills(self):
        history = {"company_id": "sample", "currency": "JPY", "thresholds": [.8, 1],
                   "valuations": [{"date": "2025-01-01", "base_fv": 100},
                                  {"date": "2025-02-01", "base_fv": 200}],
                   "closes": [{"date": "2025-01-02", "price": 80}, {"date": "2025-02-03", "price": 100}],
                   "purchases": [{"date": "2025-01-02", "price": 90, "shares": 2, "personal_cash": 170},
                                 {"date": "2025-02-03", "price": 100, "shares": 6, "personal_cash": 550}]}
        out = residency(history, "sample", "2025-02-03")
        self.assertEqual([b["days"] for b in out["days_below"]], [1, 2])
        self.assertEqual(out["bands"][0]["personal_cash"], 550)
        self.assertAlmostEqual(out["weighted_average_purchase_p_to_fv"], .6)
        history["closes"][0]["date"] = "2024-12-31"
        with self.assertRaises(ValueError):
            residency(history, "sample", "2025-02-03")
