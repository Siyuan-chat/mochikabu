"""Validate fresh 5706 observations against the issuer's November 2026 table layout."""
import math


SEGMENTS = ("機能材料", "金属", "本社管轄", "事業創造", "調整額")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def equal(observed, expected, label):
    require(isinstance(observed, (float, int)) and math.isclose(observed, expected, abs_tol=1e-8),
            f"Check filing row or unit: {label} (transcribed {observed}, statement implies {expected})")


def check_november_5706(facts, market):
    raw = facts["metadata"]["filing_rows"]
    require(facts["periods"] == [2024, 2025, 2026], "Include every comparable annual observation in the new organization")
    segments = {row["name"]: row["values"] for row in facts["segments"]}
    require(set(segments) == set(SEGMENTS), "Use the original five segment labels from the numerical EBIT table")
    for name in (*SEGMENTS, "連結"):
        row = raw["core_ebit_oku"][name]
        require(len(row) == 12, f"Copy the full twelve-value operating-profit row for {name}")
        observed = facts["normalized_group"] if name == "連結" else segments[name]
        for year, index, position in ((2025, 4, 1), (2026, 9, 2)):
            equal(observed[position], row[index] / 10, f"{name} FY{year}, original 億円")
    require([h["fy"] for h in facts["history"]] == [2023,2024,2025], "Use the last three completed reporting years")
    for h in facts["history"]:
        row = raw["historic_million"][str(h["fy"])]
        equal(h["capex"], (abs(row["ppe_cash"]) + abs(row["intangible_cash"])) / 1000, "cash capex")
        nwc = sum(row[k] for k in ("receivables","finished","wip","materials")) - row["trade_payables"]
        equal(h["nwc"], nwc / 1000, "operating working capital")
        for name in ("sales","ebit","da"):
            equal(h[name], row[name] / 1000, name)
        equal(h["roic"], row["roic_percent"] / 100, "realized ROIC")
    c = facts["current"]
    equal(facts["product_sales"], raw["product_sales_million"]/1000, "revenue disaggregation note, original million yen")
    equal(c["shares_million"], (raw["issued_shares"]-raw["treasury_shares"])/1e6, "issued less treasury shares")
    equal(c["disposed_base_ebit"], raw["divested_ebit_million"]/1000, "signed disposed business EBIT")
    equal(c["disposed_base_external_sales"], raw["divested_sales_million"]/1000, "disposed external revenue")
    require(c["disposed_segment_name"] == "本社管轄", "Map the disposed business to the comparable organization")
    peers = {p["company"]:p for p in facts["peer_margins"]}
    require(set(peers) == {"5016","8358"} and len(peers)==len(facts["peer_margins"]), "Use the two product operating benchmarks")
    for company, period, unit in (("5016","2026-03-31","JPY million"), ("8358","2025-12-31","TWD thousand")):
        p = peers[company]
        require(p["period_end"] == period and p["months"] == 12 and p["unit"] == unit,
                f"Use the latest completed annual operating observation in filing units: {company}")
    require({p["ticker"] for p in market["peers"]} == {"5016","5801"},
            "Check both March-year listed product peers against their latest company EPS forecasts")
