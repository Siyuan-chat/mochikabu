"""Executable invariants for filing-driven valuation; no external case fixture."""
from datetime import date
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fixed_model import dividend_bridge, run_model


URL = "https://example.test/public-filing"


def filing():
    return {
        "model":"expansion_fcff_v1","ticker":"sample","market_date":"2026-11-16",
        "fiscal_end_anchor":"2027-03-31","first_forecast_fy":2027,
        "history":[dict(fy=y,sales=100+y-2023,ebit=12,capex=6,da=5,nwc=18,roic=.12,source=URL)
                   for y in (2023,2024,2025)],
        "segments":[dict(name="product and others",role="product_pool",values=[10,11],source=URL),
                    dict(name="other businesses after consolidation",role="other",values=[2,1],source=URL)],
        "normalized_group":[12,12],"periods":[2025,2026],"base_period":2025,
        "product_sales":20,"peer_margins":[dict(company=c,sales=100,ebit=m,source=URL) for c,m in (("A",10),("B",17))],
        "growth_targets":[dict(fy=2028,multiple=2),dict(fy=2030,multiple=3)],
        "project":dict(equipment=12,building=4,land=2,start_fy=2029,end_fy=2030),
        "plan":dict(maintenance_total=12,maintenance_years=3,realized_maintenance_total=9,realized_years=3),
        "current":dict(sales=110,ebit=14,da=5,net_debt=12,shares_million=30,dividend=2,
                       dividend_ex_date="2027-03-30",dividend_record_date="2027-03-31",dividend_pay_date=None),
        "sources":{k:URL for k in ("project","plan","current","product_sales","growth_targets","normalized_group")}}


class FixedPolicyTests(unittest.TestCase):
    def test_replay_and_project_reconciliation(self):
        f=filing();model=run_model(f)
        self.assertEqual(model,run_model(f))
        for case in model["cases"].values():
            rows=case["annual"]
            self.assertAlmostEqual(sum(r["project_capex"] for r in rows),18)
            self.assertEqual(rows[0]["ebit"],12+(case["profit_bridge"]["ebit"]-12)*.25)
            for row in rows:
                self.assertAlmostEqual(row["fcff"],row["ebit"]-row["cash_tax"]+row["depreciation"]-row["capex"]-row["change_nwc"])
            bridge=case["profit_bridge"]
            self.assertAlmostEqual(bridge["product_pool_base"],bridge["other_products_residual"]+bridge["product_base_ebit_proxy"])
            self.assertAlmostEqual(bridge["ebit"],bridge["non_product_ebit"]+bridge["product_endpoint_ebit"])
        self.assertNotIn("base",model["fair_value_range_per_share"])

    def test_unreconciled_segment_and_policy_override(self):
        f=filing();f["wacc"]=.02
        with self.assertRaises(ValueError):
            run_model(f)
        del f["wacc"];f["normalized_group"][0]+=1
        with self.assertRaisesRegex(ValueError,"reconcile"):
            run_model(f)

    def test_post_ex_anchor_liability_and_record_ambiguity(self):
        c=filing()["current"];anchor=date(2027,3,31)
        before=dividend_bridge(c,date(2026,11,16),anchor)
        after=dividend_bridge(c,date(2027,3,30),anchor)
        self.assertEqual((before[0],before[1]),(.06,2))
        self.assertEqual((after[0],after[1]),(.06,0))
        c["dividend_ex_date"]=None
        with self.assertRaisesRegex(ValueError,"exchange ex-date"):
            dividend_bridge(c,date(2027,3,29),anchor)


if __name__=="__main__":
    unittest.main()
