from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from review_contribution import compare_amounts


class ContributionCompletionTest(unittest.TestCase):
    def test_personal_facts_determine_both_choices(self):
        personal = dict(monthly=15000, bonus_multiplier=3, bonus_count=2, incentive_rate=.1,
                        employer_stock_share=.1, cash_sufficient=True)
        bounds = {"low": 1000, "high": 1500}
        result = compare_amounts(personal, 1409.5, bounds)
        self.assertEqual(result["decision"], "reduce")
        self.assertEqual(result["decision_if_regularly_diversifying"], "maintain")
        self.assertEqual(result["cash_released"], 90000)
        self.assertEqual(result["gross_reward_forgone"], 9000)
        self.assertEqual(result["adjusted_cost_position"], "inside_range")
        personal["regular_diversification"] = True
        self.assertEqual(compare_amounts(personal, 1409.5, bounds)["decision"], "maintain")
        self.assertEqual(compare_amounts(personal, 1700, bounds)["decision"], "reduce")
        personal["cash_sufficient"] = False
        self.assertEqual(compare_amounts(personal, 900, bounds)["decision"], "reduce")
