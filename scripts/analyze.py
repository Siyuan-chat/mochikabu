#!/usr/bin/env python3
"""Deterministic planner for company employee stock plan decisions.

The script deliberately separates public-valuation inputs from personal holdings.
It is a planning model, not a price prediction engine.
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import math
import statistics
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def load_json(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump_json(obj: Dict[str, Any], path: Optional[str]) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if path:
        Path(path).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def validate_currency(config: Dict[str, Any]) -> None:
    if config.get("currency", "JPY") != "JPY":
        raise ValueError("mochikabu requires JPY inputs; convert foreign-currency values before modeling")


def normalize_holdings(h: Dict[str, Any]) -> Dict[str, Any]:
    ratio = float(h.get("split_ratio_to_current", 1.0))
    basis = h.get("price_basis", "post_split")
    shares_displayed = float(h["displayed_shares"])
    shares_current = shares_displayed * ratio if basis == "pre_split" else shares_displayed

    personal = float(h["personal_contribution"])
    incentive = float(h.get("company_incentive", 0.0))
    purchase_amount = float(h.get("purchase_amount", personal + incentive))
    residual_cash = personal + incentive - purchase_amount

    row_contrib = sum(float(r.get("contribution", 0)) for r in h.get("rows", []))
    row_incentive = sum(float(r.get("incentive", 0)) for r in h.get("rows", []))
    row_shares = sum(float(r.get("shares", 0)) for r in h.get("rows", []))

    warnings: List[str] = []
    if abs(row_contrib - personal) > 1:
        warnings.append(f"row contribution sum {row_contrib:.0f} != total {personal:.0f}")
    if abs(row_incentive - incentive) > 1:
        warnings.append(f"row incentive sum {row_incentive:.0f} != total {incentive:.0f}")
    if h.get("rows") and abs(row_shares - shares_displayed) > 0.005:
        warnings.append(f"row shares sum {row_shares:.4f} != displayed {shares_displayed:.4f}")

    return {
        "as_of": h.get("as_of"),
        "shares_current_basis": shares_current,
        "personal_contribution": personal,
        "company_incentive": incentive,
        "purchase_amount": purchase_amount,
        "residual_cash": residual_cash,
        "personal_cash_cost_per_share": personal / shares_current if shares_current else None,
        "accounting_purchase_cost_per_share": purchase_amount / shares_current if shares_current else None,
        "validation_warnings": warnings,
    }


def dcf_value(dcf: Dict[str, Any]) -> Dict[str, Any]:
    fcfs = [float(x) for x in dcf["fcf_billion"]]
    wacc = float(dcf["wacc"])
    g = float(dcf["terminal_growth"])
    net_debt = float(dcf.get("net_debt_billion", 0.0))
    shares_m = float(dcf["shares_million_post_split"])

    if not fcfs:
        raise ValueError("DCF requires at least one FCF year")
    if not all(math.isfinite(x) for x in [*fcfs, wacc, g, net_debt, shares_m]):
        raise ValueError("DCF inputs must be finite")
    if wacc <= 0 or g <= -1 or wacc <= g:
        raise ValueError("WACC must be greater than terminal growth")
    if shares_m <= 0:
        raise ValueError("share count must be positive")

    pv_fcfs = sum(cf / ((1 + wacc) ** t) for t, cf in enumerate(fcfs, start=1))
    terminal = fcfs[-1] * (1 + g) / (wacc - g)
    pv_terminal = terminal / ((1 + wacc) ** len(fcfs))
    enterprise_value = pv_fcfs + pv_terminal
    equity_value = enterprise_value - net_debt
    per_share = equity_value / shares_m * 1000.0

    def sens(w: float, tg: float) -> Optional[float]:
        if w <= tg:
            return None
        pv = sum(cf / ((1 + w) ** t) for t, cf in enumerate(fcfs, start=1))
        tv = fcfs[-1] * (1 + tg) / (w - tg)
        eq = pv + tv / ((1 + w) ** len(fcfs)) - net_debt
        return eq / shares_m * 1000.0

    wacc_grid = [max(0.001, wacc + delta) for delta in (-0.01, -0.005, 0, 0.005, 0.01)]
    g_grid = [max(0.0, g - 0.005), g, g + 0.005]
    sensitivity = {
        f"wacc_{w:.4f}": {f"g_{tg:.4f}": sens(w, tg) for tg in g_grid}
        for w in wacc_grid
    }

    return {
        "pv_forecast_fcf_billion": pv_fcfs,
        "pv_terminal_value_billion": pv_terminal,
        "terminal_value_share_of_ev": pv_terminal / enterprise_value if enterprise_value else None,
        "enterprise_value_billion": enterprise_value,
        "equity_value_billion": equity_value,
        "fair_value_per_share": per_share,
        "sensitivity": sensitivity,
    }


def get_fair_value(config: Dict[str, Any]) -> Dict[str, Any]:
    fv = config["fair_value"]
    mode = fv.get("mode", "manual")
    if mode == "dcf":
        out = dcf_value(fv["dcf"])
        out["mode"] = "dcf"
        return out
    if mode == "manual":
        return {"mode": "manual", "fair_value_per_share": float(fv["value"])}
    raise ValueError(f"unknown fair_value mode: {mode}")


def fetch_yahoo_history(ticker: str, years: int = 3) -> List[Tuple[dt.date, float]]:
    now = int(dt.datetime.now(dt.timezone.utc).timestamp())
    start = int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=365 * years + 30)).timestamp())
    q = urllib.parse.urlencode({"period1": start, "period2": now, "interval": "1d", "events": "history"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    result = payload["chart"]["result"][0]
    if result.get("meta", {}).get("currency") != "JPY":
        raise ValueError("Live market data must be in JPY; supply a converted JPY price manually")
    ts = result.get("timestamp", [])
    closes = result["indicators"]["quote"][0].get("close", [])
    rows = []
    for t, c in zip(ts, closes):
        if c is None:
            continue
        rows.append((dt.datetime.fromtimestamp(t, dt.timezone.utc).date(), float(c)))
    if not rows:
        raise RuntimeError("No price history returned")
    return rows


def price_stats(rows: List[Tuple[dt.date, float]]) -> Dict[str, Any]:
    prices = [p for _, p in rows]
    dates = [d for d, _ in rows]
    current = prices[-1]
    peak = max(prices)
    drawdown = current / peak - 1

    returns = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices)) if prices[i - 1] > 0]
    ann_vol = statistics.pstdev(returns) * math.sqrt(252) if len(returns) > 1 else None

    def avg(n: int) -> Optional[float]:
        if not prices:
            return None
        seq = prices[-min(n, len(prices)):]
        return sum(seq) / len(seq)

    return {
        "start_date": str(dates[0]),
        "end_date": str(dates[-1]),
        "current_price": current,
        "high": peak,
        "drawdown_from_period_high": drawdown,
        "ma20": avg(20),
        "ma60": avg(60),
        "ma120": avg(120),
        "annualized_realized_volatility": ann_vol,
    }


def month_range(start_date: dt.date, end_date: dt.date) -> Iterable[Tuple[int, int]]:
    y, m = start_date.year, start_date.month
    while (y, m) <= (end_date.year, end_date.month):
        yield y, m
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1


def months_between(start_date: dt.date, end_date: dt.date) -> int:
    return sum(1 for _ in month_range(start_date, end_date))


def simulate_plan(
    holdings: Dict[str, Any],
    config: Dict[str, Any],
    avg_price: float,
    monthly: float,
    bonus: float,
) -> Dict[str, Any]:
    validate_currency(config)
    start = dt.date.fromisoformat(config["contribution_start_date"]) if config.get("contribution_start_date") else dt.date.fromisoformat(config["as_of"]) + dt.timedelta(days=1)
    # Review decisions apply from the next calendar month. If as_of is month-end, this naturally starts next month.
    if not config.get("contribution_start_date") and start.day != 1:
        if start.month == 12:
            start = dt.date(start.year + 1, 1, 1)
        else:
            start = dt.date(start.year, start.month + 1, 1)
    end = dt.date.fromisoformat(config["target_date"])

    shares = float(holdings["shares_current_basis"])
    personal_cash = float(holdings["personal_contribution"])
    company_incentive_cash = float(holdings["company_incentive"])
    dividend_cash_reinvested = 0.0

    incentive_rate = float(config.get("incentive_rate", 0.0))
    incentive_tax_rate = float(config.get("incentive_tax_rate", 0.0))
    effective_incentive_rate = incentive_rate * (1 - incentive_tax_rate)
    bonus_months = set(int(x) for x in config.get("bonus_months", []))
    dividend_months = set(int(x) for x in config.get("dividend_reinvest_months", []))
    annual_div = float(config.get("dividend_annual_post_split", 0.0))
    div_tax = float(config.get("dividend_tax_rate", 0.0))
    div_reinvest = bool(config.get("dividend_reinvest", False))

    monthly_contrib_count = 0
    bonus_count = 0
    dividend_events = 0

    for y, m in month_range(start, end):
        # Monthly contribution
        monthly_contrib_count += 1
        personal_cash += monthly
        gross = monthly * (1 + effective_incentive_rate)
        company_incentive_cash += monthly * effective_incentive_rate
        shares += gross / avg_price

        # Bonus contribution
        if m in bonus_months:
            bonus_count += 1
            personal_cash += bonus
            gross_bonus = bonus * (1 + effective_incentive_rate)
            company_incentive_cash += bonus * effective_incentive_rate
            shares += gross_bonus / avg_price

        # Dividend reinvestment; approximate equal dividend installments on shares held by reinvestment month.
        if div_reinvest and m in dividend_months and annual_div > 0:
            dividend_events += 1
            net_div = shares * (annual_div / max(1, len(dividend_months))) * (1 - div_tax)
            dividend_cash_reinvested += net_div
            shares += net_div / avg_price

    personal_cost = personal_cash / shares if shares else None
    return {
        "avg_price": avg_price,
        "monthly": monthly,
        "bonus": bonus,
        "months": monthly_contrib_count,
        "bonus_count": bonus_count,
        "dividend_events": dividend_events,
        "final_shares": shares,
        "final_personal_cash": personal_cash,
        "final_personal_cash_cost_per_share": personal_cost,
        "cumulative_company_incentive_effective": company_incentive_cash,
        "cumulative_dividend_cash_reinvested": dividend_cash_reinvested,
    }


def choose_bonus(config: Dict[str, Any], monthly: float) -> float:
    mode = config.get("bonus_mode", "fixed")
    if mode == "fixed":
        return float(config.get("candidate_bonus", config.get("current_bonus", 0.0)))
    if mode == "multiple_of_monthly":
        multiple = float(config.get("bonus_multiple", 3.0))
        return monthly * multiple
    raise ValueError(f"unknown bonus_mode: {mode}")


def recommend_candidate(
    grid: List[Dict[str, Any]],
    current_monthly: float,
    max_step: float,
) -> Dict[str, Any]:
    # Primary: scenario count meeting minimum shares + cost target.
    # Secondary: avoid > target_max when possible; then prefer lower monthly contribution.
    grouped: Dict[float, List[Dict[str, Any]]] = {}
    for row in grid:
        grouped.setdefault(row["monthly"], []).append(row)

    scores = []
    for monthly, rows in sorted(grouped.items()):
        success = sum(1 for r in rows if r["minimum_share_goal"] and r["cost_goal"])
        in_band = sum(1 for r in rows if r["soft_band"] and r["cost_goal"])
        scores.append((success, in_band, -monthly, monthly))

    best = max(scores) if scores else (0, 0, -current_monthly, current_monthly)
    raw = float(best[3])

    # Risk-control rule: cap increase to one configured step per review unless current candidate is below current.
    if raw > current_monthly + max_step:
        selected = current_monthly + max_step
        rationale = "raw scenario winner capped to one review-step increase"
    else:
        selected = raw
        rationale = "selected by robust goal coverage"

    if selected not in grouped:
        # Pick nearest available candidate not above the cap; if none, current amount.
        allowed = [m for m in grouped if m <= current_monthly + max_step]
        selected = max(allowed) if allowed else current_monthly
        rationale += "; snapped to available candidate"

    return {
        "selected_monthly": selected,
        "rationale": rationale,
        "candidate_scores": [
            {"monthly": s[3], "goal_success_scenarios": s[0], "in_target_band_success_scenarios": s[1]}
            for s in sorted(scores, key=lambda x: x[3])
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--holdings", required=True)
    ap.add_argument("--fetch-price", action="store_true")
    ap.add_argument("--research", help="Public valuation/peer result from value_public.py")
    ap.add_argument("--output")
    args = ap.parse_args()

    config = load_json(args.config)
    validate_currency(config)
    holdings_raw = load_json(args.holdings)
    holdings = normalize_holdings(holdings_raw)
    research = load_json(args.research) if args.research else None
    if research:
        if research.get("currency") != "JPY" or research.get("company_id") != config.get("company_id"):
            raise ValueError("Research report must match config company_id and JPY currency")
        if research.get("valuation", {}).get("status") != "MODELED":
            raise ValueError("Resolve research valuation evidence before projecting contributions")
        for field in ("margin_of_safety", "incentive_rate", "incentive_tax_rate"):
            if field not in research.get("policy", {}) or field not in config or not math.isclose(float(research["policy"][field]), float(config[field])):
                raise ValueError("Plan and valuation policy differ: " + field)
        quote = research.get("market", {})
        if quote.get("status") != "PUBLIC":
            raise ValueError("Resolve dated market evidence before projecting contributions")
        timestamp = dt.datetime.fromisoformat(quote["price_as_of"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("Quote timestamp requires timezone")
        age_hours = (dt.datetime.now(dt.timezone.utc) - timestamp).total_seconds() / 3600
        if age_hours < -0.1 or age_hours > float(research.get("max_quote_age_hours", 72)):
            raise ValueError("Refresh the research quote before projecting contributions")
        fv = research["valuation"]
    else:
        fv = get_fair_value(config)
    fair_value = float(fv["fair_value_per_share"])
    margin = float(config.get("margin_of_safety", 0.20))
    target_cost = fair_value * (1 - margin)
    incentive_rate = float(config.get("incentive_rate", 0.0))
    incentive_tax_rate = float(config.get("incentive_tax_rate", 0.0))
    effective_incentive = incentive_rate * (1 - incentive_tax_rate)
    marginal_target_market_price = target_cost * (1 + effective_incentive)

    market: Dict[str, Any] = {}
    if research:
        market = research["market"]
    elif args.fetch_price:
        try:
            if not config.get("ticker") or config["ticker"] == "EXAMPLE":
                raise ValueError("Live price fetch requires a real market ticker")
            from fetch_public import fetch_quote
            market = fetch_quote(config["ticker"])
        except Exception as e:
            market = {"error": str(e), "current_price": config.get("market_price")}
    else:
        market = {"current_price": config.get("market_price")}

    scenarios = [fair_value * float(x) for x in config.get("scenario_price_multipliers_vs_fv", [0.8, 0.9, 1.0, 1.1])]
    candidates = [float(x) for x in config.get("candidate_monthly", [config.get("current_monthly", 0)])]
    target_min = float(config.get("target_shares_min", 0))
    target_max = float(config.get("target_shares_max", float("inf")))

    grid: List[Dict[str, Any]] = []
    for monthly in candidates:
        bonus = choose_bonus(config, monthly)
        for p in scenarios:
            proj = simulate_plan(holdings, config, p, monthly, bonus)
            proj["minimum_share_goal"] = proj["final_shares"] >= target_min
            proj["cost_goal"] = proj["final_personal_cash_cost_per_share"] <= target_cost
            proj["soft_band"] = target_min <= proj["final_shares"] <= target_max
            grid.append(proj)

    decision = recommend_candidate(
        grid,
        float(config.get("current_monthly", 0.0)),
        float(config.get("max_step_change", float("inf"))),
    )
    decision["role"] = "scenario_score_requires_agent_review"
    if research:
        decision["purchase_signal"] = research["purchase_signal"]

    current_price = market.get("current_price")
    if current_price is not None:
        current_price = float(current_price)
        decision["current_price_vs_fair_value"] = current_price / fair_value - 1
        decision["current_marginal_personal_cost"] = current_price / (1 + effective_incentive)
        decision["current_price_is_below_marginal_target_threshold"] = current_price <= marginal_target_market_price

    out = {
        "company_name": config.get("company_name"),
        "currency": "JPY",
        "ticker": config.get("ticker"),
        "as_of": config["as_of"],
        "holdings": holdings,
        "valuation": fv,
        "policy_thresholds": {
            "margin_of_safety": margin,
            "target_personal_cash_cost_per_share": target_cost,
            "marginal_target_market_price": marginal_target_market_price,
            "target_shares_min": target_min,
            "target_shares_max_soft": target_max if math.isfinite(target_max) else None,
        },
        "market": market,
        "scenario_grid": grid,
        "decision": decision,
        "public_research": research,
        "notes": [
            "Scenario prices are constant-average planning cases, not forecasts.",
            "Dividend timing is approximate and configurable.",
            "Refresh all DCF inputs from public IR before an actual contribution change.",
        ],
    }
    dump_json(out, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
