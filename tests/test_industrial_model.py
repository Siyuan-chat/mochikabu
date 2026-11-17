from datetime import date
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from industrial_model import run_model
from review_contribution import build_review, peer_table
from fixed_model import run_model as run_archived_model


def industrial_fixture():
    tables=[]
    def table(year, rows, kind="actual", unit="JPY million", scope="consolidated"):
        tables.append(dict(source_url="https://example.test/statement",published="2026-05-01",
            period_start=f"{year-1}-04-01",period_end=f"{year}-03-31",kind=kind,scope=scope,
            page="consolidated results, p.2",column="current annual column",unit=unit,
            rows={k:[k,v] for k,v in rows.items()}))
    for year in (2024,2025,2026):
        table(year,dict(sales=10000,ebit=1000,da=300,receivables=1000,inventory=750,
                        payables=500,ppe_cash=-280,intangible_cash=-20))
    table(2026,dict(cash=1000,debt=500,lease_debt=50,nci=10))
    table(2026,dict(issued_shares=900000,treasury_shares=100000),unit="shares")
    table(2027,dict(sales=12000,ebit_low=1000,ebit_high=1400),kind="forecast")
    table(2030,dict(project_budget=1500),kind="plan",scope="project")
    return dict(model="industrial_project_fcff_v1",ticker="SYN",market_date="2026-11-16",tables=tables,
                guidance_check={f:dict(status="not_disclosed",source_url="https://example.test/ir",locator="annual forecast") for f in ("da","capex_cash")},
                project=dict(name="Plant",start_fy_end="2028-03-31",operation_fy_end="2030-03-31",start_month="2027-05"))


class IndustrialProjectTest(unittest.TestCase):
    def test_project_cash_conserved_and_interval_guidance_retained(self):
        facts=industrial_fixture()
        r=run_model(facts)
        for c in r["cases"].values():
            self.assertAlmostEqual(sum(y["project_capex"] for y in c["annual"]),1.5)
            self.assertAlmostEqual(c["date_bridge"]["shares_million"],.8)
            self.assertAlmostEqual(c["date_bridge"]["noncontrolling_interests"],.01)
            self.assertLess(c["annual"][0]["fraction"],1)
        self.assertEqual({round(c["profit_bridge"]["guided_ebit"],8) for c in r["cases"].values()},{1.,1.4})
        reverse=copy.deepcopy(facts)
        reverse["tables"].reverse()
        self.assertEqual(run_model(reverse)["fair_value_range_per_share"],r["fair_value_range_per_share"])

    def test_ambiguous_or_mismatched_evidence_rejected(self):
        for patch in (dict(scope="parent"),dict(published="2027-01-01"),dict(unit="shares"),
                      dict(period_start="2023-10-01"),dict(column="")):
            f=industrial_fixture()
            f["tables"][0].update(patch)
            with self.subTest(patch=patch),self.assertRaises(ValueError):
                run_model(f)
        f=industrial_fixture()
        f["tables"].append(dict(f["tables"][0],rows={"sales":["sales",5000]}))
        with self.assertRaisesRegex(ValueError,"Ambiguous"):
            run_model(f)

    def test_full_runner_range_eps_and_prior_regression(self):
        saved=ROOT/"tests/fixtures/5706"
        market=json.loads((saved/"2026-11-16-market.json").read_text(encoding="utf-8-sig"))
        old=json.loads((saved/"2026-11-16-financial.json").read_text(encoding="utf-8-sig"))
        self.assertAlmostEqual(run_archived_model(old)["fair_value_range_per_share"]["low"],685.6431685953962)
        self.assertAlmostEqual(run_archived_model(old)["fair_value_range_per_share"]["high"],2436.1852950636953)
        market["target"].update(ticker="SYN",eps={"low":50,"high":100},close=1200)
        market["peers"][0]["eps"]={"low":100,"high":150}
        for p in market["peers"]:
            p["core_sales"]=dict(product_sales=60,group_sales=100,source_url="https://example.test/ir",locator="annual segment table")
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp)
            (d/"financial.json").write_text(json.dumps(industrial_fixture()))
            (d/"market.json").write_text(json.dumps(market))
            req=dict(ticker="SYN",model_id="industrial_project_fcff_v1",market_date="2026-11-16",
                     facts_file="financial.json",market_file="market.json",personal=dict(monthly=15000,bonus_multiplier=3,
                     bonus_count=2,incentive_rate=.1,employer_stock_share=.1,cash_sufficient=True))
            answer=build_review(req,d,True)
            self.assertEqual(answer["status"],"review_ready")
            self.assertEqual(answer["pe_comparison"][0]["calculated_pe"],{"low":12,"high":24})
            self.assertIn("low",answer["peer_implied_price"])
            for patch in (dict(dcf={}),dict(model_id="unsupported"),dict(ticker="wrong")):
                with self.subTest(patch=patch),self.assertRaises(ValueError):
                    build_review(dict(req,**patch),d,True)

