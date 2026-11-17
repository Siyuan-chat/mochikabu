import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from product_filing_model import run_model
from review_contribution import build_review

FILES = ROOT / "tests/fixtures/5706"
FINANCIAL = "2026-11-16-product-tables.json"


class ProductFilingTest(unittest.TestCase):
    def test_official_review_matches_archived_close_date_range(self):
        request = dict(ticker="5706", model_id="expansion_fcff_v1", market_date="2026-11-16",
                       facts_file=FINANCIAL, market_file="2026-11-16-market.json",
                       personal=dict(monthly=15000, bonus_multiplier=3, bonus_count=2,
                                     incentive_rate=.10, employer_stock_share=.10, cash_sufficient=True))
        answer = build_review(request, FILES, True)
        self.assertEqual(answer["status"], "review_ready")
        bounds = answer["decision_fair_value_range_per_share"]
        self.assertAlmostEqual(bounds["low"], 685.6431685953962)
        self.assertAlmostEqual(bounds["high"], 2436.1852950636953)
        audit = answer["stable_cash_flow_review"]
        self.assertEqual(len(audit["rows"]), 7)
        self.assertAlmostEqual(sum(r["cash_flow_effect"] for r in audit["rows"]), audit["high"]-audit["low"])
        self.assertAlmostEqual(audit["after_tax_operating_effect"]+audit["net_reinvestment_effect"], audit["difference"])
        self.assertEqual({r["origin"] for r in audit["evidence"]}, {"同业代理", "公司披露"})
        self.assertIn("估值不足以支持下调", answer["answer_zh"])
        self.assertEqual(answer["contribution_comparison"]["decision"], "reduce")
        request["personal"]["regular_diversification"]=True
        diversified = build_review(request, FILES, True)
        self.assertEqual(diversified["contribution_comparison"]["decision"], "maintain")
        self.assertEqual(diversified["valuation_assessment_zh"], answer["valuation_assessment_zh"])

    def test_comparable_period_and_segment_completeness(self):
        facts = json.loads((FILES / FINANCIAL).read_text(encoding="utf-8"))
        for error in ("whole year","segment","inventory","source column","unsupported exclusion"):
            f=copy.deepcopy(facts)
            columns=f["segment_coverage"]["columns"]
            selected=columns[1]
            if error in ("whole year","segment"):
                f["product_tables"]=[t for t in f["product_tables"] if not (
                    t["period_end"]==selected["period_end"] and "normalized_ebit" in t["rows"]
                    and (error=="whole year" or t["scope"]=="segment/金属"))]
            elif error=="inventory":
                columns.pop(1)
            elif error=="source column":
                selected["control_cells"]["group"][1]+=1
            else:
                columns[0]["checked_sources"]=[]
            with self.subTest(error=error),self.assertRaises(ValueError):
                run_model(f)

    def test_misclassified_product_inputs_fail_before_valuation(self):
        facts = json.loads((FILES / FINANCIAL).read_text(encoding="utf-8"))
        for scope, field, mutation in (
            ("project", "equipment", {"unit": "JPY million"}),
            ("peer/5016", "sales", {"unit": "percent"}),
            ("segment/機能材料", "normalized_ebit", {"column": ""}),
            ("product", "profit_multiple", {"period_end": "2034-12-31"}),
        ):
            altered = copy.deepcopy(facts)
            row = next(t for t in altered["product_tables"] if t["scope"] == scope and field in t["rows"])
            row.update(mutation)
            with self.subTest(scope=scope, field=field), self.assertRaises(ValueError):
                run_model(altered)
