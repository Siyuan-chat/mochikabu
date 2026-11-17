"""Reconcile two close-date DCFs in yen per share, retaining every annual input."""
import math
from datetime import date

from review_contribution import equity_at_close

SIGNS = {"ebit": 1, "cash_tax": -1, "depreciation": 1, "capex": -1, "change_nwc": -1}


def compare(old, new):
    if old["target"]["ticker"] != new["target"]["ticker"] or old["market_date"] != new["market_date"]:
        raise ValueError("Restate both models for the same company and closing date before attribution")
    series = []
    for data in (old, new):
        model = data["dcf"]
        value = equity_at_close(model, date.fromisoformat(data["market_date"]))
        rows = value["annual_operating_forecast"]
        scale = 1000 / model["shares_million_post_split"] / value["date_bridge"]["discount_factor"]
        weights = {r["fy"]: scale / (1 + model["wacc"]) ** t for t, r in enumerate(rows, 1)}
        g = model["terminal_growth"]
        terminal_weight = weights[rows[-1]["fy"]] * (1 + g) / (model["wacc"] - g)
        series.append((rows, weights, terminal_weight, -scale * model["net_debt_billion"], value))
    a, wa, ta, da, va = series[0]
    b, wb, tb, db, vb = series[1]
    by_year = {r["fy"]: r for r in a}
    annual = []
    for year in sorted(set(by_year) | set(wb)):
        left = by_year.get(year, {})
        right = next((r for r in b if r["fy"] == year), {})
        annual.append({"fy": year, "old": left, "new": right,
                       "yen_per_share": right.get("fcff", 0) * wb.get(year, 0) - left.get("fcff", 0) * wa.get(year, 0)})
    terms = {"explicit_years": sum(r["yen_per_share"] for r in annual),
             "terminal_cash_flow_at_old_parameters": (b[-1]["fcff"] - a[-1]["fcff"]) * ta,
             "terminal_parameter_change_at_new_cash_flow": b[-1]["fcff"] * (tb-ta),
             "net_debt_bridge": db-da,
             "interim_distributions": vb["date_bridge"]["distribution_pv"]-va["date_bridge"]["distribution_pv"]}
    total = vb["fair_value_per_share"] - va["fair_value_per_share"]
    if not math.isclose(sum(terms.values()), total, abs_tol=1e-7):
        raise ValueError("DCF change does not reconcile")
    stable = {k: (b[-1][k]-a[-1][k])*sign for k,sign in SIGNS.items()}
    return dict(old_price=va["fair_value_per_share"], new_price=vb["fair_value_per_share"],
                delta=total, components=terms, annual=annual, stable_fcff_change_billion=stable)
