import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))
from legacy_filing_rows import check_november_5706, SEGMENTS


class FilingRowTests(unittest.TestCase):
    def test_reject_superseded_forecast_half_year_and_rounded_product_revenue(self):
        raw = dict(core_ebit_oku={k: list(range(12)) for k in (*SEGMENTS, "連結")},
                   issued_shares=100, treasury_shares=10, divested_ebit_million=-5,
                   divested_sales_million=15, product_sales_million=1234, historic_million={})
        observations = []
        for fy in (2023,2024,2025):
            raw["historic_million"][str(fy)] = dict(sales=1000, ebit=20, da=5, ppe_cash=-4,
                intangible_cash=-2, receivables=3, finished=4, wip=2, materials=1, trade_payables=3, roic_percent=8)
            observations.append(dict(fy=fy,sales=1,ebit=.02,da=.005,capex=.006,nwc=.007,roic=.08))
        f=dict(metadata=dict(filing_rows=raw), periods=[2024,2025,2026], history=observations,
               normalized_group=[0,.4,.9],segments=[dict(name=k,values=[0,.4,.9]) for k in SEGMENTS],
               product_sales=1.234,current=dict(shares_million=.00009,disposed_base_ebit=-.005,
               disposed_base_external_sales=.015,disposed_segment_name="本社管轄"),
               peer_margins=[dict(company=c,months=12,unit=u,period_end=p) for c,u,p in
                   (("5016","JPY million","2026-03-31"),("8358","TWD thousand","2025-12-31"))])
        m=dict(peers=[dict(ticker="5016"),dict(ticker="5801")])
        check_november_5706(f,m)
        for path, replacement in ((("segments",0,"values",2),1.1),(("product_sales",),1.2),
                                  (("peer_margins",0,"months"),6),(("history",0,"nwc"),.014)):
            modified=copy.deepcopy(f)
            parent=modified
            for key in path[:-1]:
                parent=parent[key]
            parent[path[-1]]=replacement
            with self.subTest(path=path), self.assertRaises(ValueError):
                check_november_5706(modified,m)
