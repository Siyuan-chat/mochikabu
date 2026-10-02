import copy
import datetime as dt
import json
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fetch_public
import value_public

NOW = dt.datetime(2026, 10, 2, 2, 0, tzinfo=dt.timezone.utc)


def fixtures():
    def company(identifier):
        fields = {"eps": 100, "bps": 500, "ebitda": 2e9, "net_debt": 0, "shares": 1e7, "base_fcf": 1e9}
        return {"id": identifier, "name": identifier, "selection_reason": "same business and accounting basis",
                "financials": fields,
                "evidence": {field: {"source_url": "https://example.test/report", "locator": "p.1", "period": "fixture FY2026", "status": "PUBLIC"} for field in fields},
                "metric_basis": {"pe": "TTM consolidated adjusted", "pb": "latest consolidated equity", "ev_ebitda": "TTM consolidated adjusted"},
                "dcf_comparison_basis": "five-year normalized FCFF, same macro assumptions",
                "dcf": {"fcf_billion": [1], "wacc": .1, "terminal_growth": 0, "net_debt_billion": 0, "shares_million_post_split": 10},
                "dcf_assumption_note": "Synthetic constant FCFF fixture"}
    target = company("target")
    peers = [company(f"peer{i}") for i in range(3)]
    request = {"currency": "JPY", "company": target, "peers": peers,
               "policy": {"margin_of_safety": .2, "incentive_rate": .1, "incentive_tax_rate": 0, "peer_premium_tolerance": .1}}
    manifest = {"companies": [{"id": c["id"], "market": {"currency": "JPY", "current_price": 800 if c["id"] == "target" else 1000,
                 "price_as_of": NOW.isoformat(), "source_url": "https://example.test/quote", "delay_status": "UNKNOWN", "realtime_verified": False}} for c in [target, *peers]]}
    return request, manifest


class PublicResearchTests(unittest.TestCase):
    def test_quote_timestamp_and_currency(self):
        payload = {"chart": {"result": [{"meta": {"currency": "JPY", "symbol": "EXAMPLE", "regularMarketPrice": 1200, "regularMarketTime": 1790906400}}]}}
        quote = fetch_public.parse_quote(payload, "https://example.test/chart", NOW.isoformat())
        self.assertEqual(quote["current_price"], 1200)
        self.assertFalse(quote["realtime_verified"])
        self.assertIn("+00:00", quote["price_as_of"])
        payload["chart"]["result"][0]["meta"]["currency"] = "USD"
        with self.assertRaisesRegex(ValueError, "not JPY"):
            fetch_public.parse_quote(payload, "https://example.test/chart", NOW.isoformat())

    def test_xbrl_preserves_context_and_units(self):
        data = b'<xbrl xmlns="http://www.xbrl.org/2003/instance"><context id="c"><period><instant>2026-03-31</instant></period></context><unit id="u"><measure>JPY</measure></unit><Revenue contextRef="c" unitRef="u" decimals="-6">123000000</Revenue></xbrl>'
        result = fetch_public.extract_report(data, "xbrl")
        self.assertEqual(result["facts"][0]["value"], "123000000")
        self.assertEqual(result["facts"][0]["unit_ref"], "u")
        self.assertEqual(len(result["contexts"]), 1)

    def test_collector_records_download_failure(self):
        request = {"company": {"id": "a", "name": "fictional", "reports": [{"url": "https://example.test/report", "format": "pdf"}]}}
        with tempfile.TemporaryDirectory() as directory, patch.object(fetch_public, "download", side_effect=OSError("fixture failure")):
            result = fetch_public.collect(request, Path(directory))
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["companies"][0]["reports"][0]["status"], "failed")

    def test_peer_premiums_and_purchase_signal(self):
        request, manifest = fixtures()
        result = value_public.evaluate(request, manifest, NOW)
        self.assertAlmostEqual(result["valuation"]["fair_value_per_share"], 1000)
        self.assertAlmostEqual(result["valuation"]["market_premium_to_fair_value"], -.2)
        self.assertAlmostEqual(result["peer_fair_value_premium"]["relative_fair_value_premium"], -.2)
        self.assertAlmostEqual(result["peer_multiple_comparison"]["pe"]["peer_implied_fair_value"], 1000)
        self.assertEqual(result["purchase_signal"]["action"], "consider_increase")
        manifest["companies"][0]["market"]["current_price"] = 1300
        self.assertEqual(value_public.evaluate(request, manifest, NOW)["purchase_signal"]["action"], "avoid_increase")

    def test_stale_quote_or_incomparable_peers_do_not_signal_buy(self):
        request, manifest = fixtures()
        manifest["companies"][0]["market"]["price_as_of"] = "2026-09-01T00:00:00+00:00"
        self.assertEqual(value_public.evaluate(request, manifest, NOW)["purchase_signal"]["status"], "OPEN")
        request, manifest = fixtures()
        request["peers"] = []
        self.assertEqual(value_public.evaluate(request, manifest, NOW)["purchase_signal"]["status"], "OPEN")

    def test_missing_evidence_and_synthetic_inputs(self):
        request, manifest = fixtures()
        request["company"]["evidence"].pop("shares")
        self.assertEqual(value_public.evaluate(request, manifest, NOW)["valuation"]["status"], "OPEN")
        request, manifest = fixtures()
        request["example_only"] = True
        self.assertEqual(value_public.evaluate(request, manifest, NOW)["purchase_signal"]["status"], "SYNTHETIC")

    def test_valuation_to_contribution_cli(self):
        root = Path(__file__).resolve().parents[1]
        request, manifest = fixtures()
        request["example_only"] = True
        for record in manifest["companies"]:
            record["market"]["price_as_of"] = dt.datetime.now(dt.timezone.utc).isoformat()
        config = json.loads((root / "examples/config.example.json").read_text())
        config["company_id"] = "target"
        config.update({key: request["policy"][key] for key in ("margin_of_safety", "incentive_rate", "incentive_tax_rate")})
        holdings = json.loads((root / "examples/holdings_snapshot.example.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for name, content in (("financials", request), ("manifest", manifest), ("config", config), ("holdings", holdings)):
                (path / (name + ".json")).write_text(json.dumps(content), encoding="utf-8")
            valuation = subprocess.run([sys.executable, str(root / "scripts/value_public.py"), "--input", str(path / "financials.json"), "--market-manifest", str(path / "manifest.json"), "--output", str(path / "valuation.json")], capture_output=True, text=True)
            self.assertEqual(valuation.returncode, 2, valuation.stderr)
            command = [sys.executable, str(root / "scripts/analyze.py"), "--config", str(path / "config.json"), "--holdings", str(path / "holdings.json"), "--research", str(path / "valuation.json"), "--output", str(path / "output.json")]
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            out = json.loads((path / "output.json").read_text())
            self.assertAlmostEqual(out["valuation"]["fair_value_per_share"], 1000)
            self.assertEqual(out["decision"]["purchase_signal"]["status"], "SYNTHETIC")
            self.assertEqual(out["market"]["current_price"], 800)
            config["incentive_rate"] = .2
            (path / "config.json").write_text(json.dumps(config), encoding="utf-8")
            mismatch = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(mismatch.returncode, 0)
            self.assertIn("policy differ", mismatch.stderr)


if __name__ == "__main__":
    unittest.main()
