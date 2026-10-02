#!/usr/bin/env python3
"""Source-backed DCF, peer multiples and valuation-based contribution signals."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics
from pathlib import Path

from analyze import dcf_value


def positive(value):
    return isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def has_evidence(company, field):
    evidence = company.get("evidence", {}).get(field, {})
    return bool(evidence.get("source_url") and evidence.get("locator") and evidence.get("period") and evidence.get("status") == "PUBLIC")


def usable_financial(company, field):
    value = company.get("financials", {}).get(field)
    return value if isinstance(value, (int, float)) and math.isfinite(value) and has_evidence(company, field) else None


def market_for(company, manifest, now, max_age_hours):
    records = {row["id"]: row for row in manifest["companies"]}
    quote = records.get(company["id"], {}).get("market", {})
    if quote.get("currency") != "JPY" or not positive(quote.get("current_price")) or not quote.get("source_url"):
        return {"status": "OPEN", "reason": "Missing source-backed JPY quote"}
    try:
        timestamp = dt.datetime.fromisoformat(quote["price_as_of"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("Quote timestamp requires timezone")
        age = (now - timestamp).total_seconds() / 3600
        if age < -0.1 or age > max_age_hours:
            return {**quote, "status": "OPEN", "reason": "Quote outside allowed age window", "age_hours": age}
    except (KeyError, ValueError):
        return {"status": "OPEN", "reason": "Invalid quote timestamp"}
    return {**quote, "status": "PUBLIC", "age_hours": age}


def multiples(company, market):
    values = {}
    if market.get("status") != "PUBLIC":
        return values
    price = market["current_price"]
    for name, field in [("pe", "eps"), ("pb", "bps")]:
        fundamental = usable_financial(company, field)
        if positive(fundamental):
            values[name] = price / fundamental
    ebitda = usable_financial(company, "ebitda")
    net_debt = usable_financial(company, "net_debt")
    shares = usable_financial(company, "shares")
    if positive(ebitda) and positive(shares) and net_debt is not None:
        enterprise_value = price * shares + net_debt
        if positive(enterprise_value):
            values["ev_ebitda"] = enterprise_value / ebitda
    return values


def fair_value(company):
    dcf = company.get("dcf")
    if not dcf:
        return {"status": "OPEN", "reason": "DCF forecasts or assumptions unavailable"}
    required = ("base_fcf", "net_debt", "shares")
    if not all(has_evidence(company, field) for field in required) or not company.get("dcf_assumption_note"):
        return {"status": "OPEN", "reason": "DCF requires public base FCF, debt and shares evidence plus forecast/discount assumptions"}
    debt = usable_financial(company, "net_debt")
    shares = usable_financial(company, "shares")
    if debt is None or not positive(shares) or usable_financial(company, "base_fcf") is None:
        return {"status": "OPEN", "reason": "Invalid DCF debt/share bridge"}
    if not math.isclose(dcf.get("net_debt_billion", float("nan")), debt / 1e9, rel_tol=1e-8, abs_tol=1e-8) or not math.isclose(dcf.get("shares_million_post_split", float("nan")), shares / 1e6, rel_tol=1e-8, abs_tol=1e-8):
        return {"status": "OPEN", "reason": "DCF bridge differs from normalized financials"}
    try:
        value = dcf_value(dcf)
        if not positive(value["fair_value_per_share"]):
            raise ValueError("Non-positive fair value")
        sensitivity = [v for row in value["sensitivity"].values() for v in row.values() if v is not None and math.isfinite(v)]
        return {"status": "MODELED", **value, "sensitivity_range": [min(sensitivity), max(sensitivity)], "assumption_note": company["dcf_assumption_note"]}
    except (ValueError, KeyError, TypeError) as error:
        return {"status": "OPEN", "reason": str(error)}


def evaluate(request, manifest, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if request.get("currency") != "JPY":
        raise ValueError("Valuation requires JPY")
    age_limit = float(request.get("max_quote_age_hours", 72))
    if not positive(age_limit):
        raise ValueError("Quote age limit must be positive")
    minimum_peers = 3
    company = request["company"]
    peers = request.get("peers", [])
    ids = [row["id"] for row in [company, *peers]]
    if len(ids) != len(set(ids)):
        raise ValueError("Company and peer IDs must be unique")
    tickers = [row["ticker"] for row in [company, *peers] if row.get("ticker")]
    if len(tickers) != len(set(tickers)):
        raise ValueError("Duplicate listings cannot count as independent peer companies")
    market = market_for(company, manifest, now, age_limit)
    target_multiples = multiples(company, market)
    valuation = fair_value(company)
    rows = []
    for peer in peers:
        quote = market_for(peer, manifest, now, age_limit)
        fv = fair_value(peer)
        ratio = quote["current_price"] / fv["fair_value_per_share"] if quote.get("status") == "PUBLIC" and fv.get("status") == "MODELED" else None
        rows.append({"id": peer["id"], "name": peer.get("name"), "selection_reason": peer.get("selection_reason"),
                     "market": quote, "multiples": multiples(peer, quote), "valuation": fv, "price_to_fair_value": ratio})
    comparisons = {}
    fields = {"pe": "eps", "pb": "bps", "ev_ebitda": "ebitda"}
    for metric, field in fields.items():
        basis = company.get("metric_basis", {}).get(metric)
        comparable = [row for row, peer in zip(rows, peers) if basis and peer.get("metric_basis", {}).get(metric) == basis and peer.get("selection_reason") and metric in row["multiples"]]
        eligible_ids = [row["id"] for row in comparable]
        if len(comparable) < minimum_peers or metric not in target_multiples:
            comparisons[metric] = {"status": "OPEN", "eligible_peer_ids": eligible_ids, "reason": "Requires target metric and at least three justified peers with matching metric basis"}
            continue
        median = statistics.median(row["multiples"][metric] for row in comparable)
        fundamental = usable_financial(company, field)
        implied = median * fundamental
        if metric == "ev_ebitda":
            implied = (implied - usable_financial(company, "net_debt")) / usable_financial(company, "shares")
        comparisons[metric] = {"status": "MODELED", "basis": basis, "eligible_peer_ids": eligible_ids,
                               "peer_median_multiple": median, "target_multiple": target_multiples[metric],
                               "multiple_premium_to_peers": target_multiples[metric] / median - 1,
                               "peer_implied_fair_value": implied,
                               "price_premium_to_peer_implied_value": market["current_price"] / implied - 1 if positive(implied) else None}
    dcf_basis = company.get("dcf_comparison_basis")
    peer_ratios = [row["price_to_fair_value"] for row, peer in zip(rows, peers) if positive(row["price_to_fair_value"]) and peer.get("selection_reason") and dcf_basis and peer.get("dcf_comparison_basis") == dcf_basis]
    comparison = {"status": "OPEN", "reason": "Requires target DCF and three comparable peer DCFs"}
    signal = {"status": "OPEN", "action": "resolve_evidence", "reasons": []}
    if valuation.get("status") == "MODELED" and market.get("status") == "PUBLIC":
        ratio = market["current_price"] / valuation["fair_value_per_share"]
        valuation["market_premium_to_fair_value"] = ratio - 1
        if len(peer_ratios) >= minimum_peers:
            median_ratio = statistics.median(peer_ratios)
            comparison = {"status": "MODELED", "peer_count": len(peer_ratios), "peer_median_price_to_fair_value": median_ratio,
                          "relative_fair_value_premium": ratio / median_ratio - 1}
        policy = request.get("policy", {})
        required_policy = ("margin_of_safety", "incentive_rate", "incentive_tax_rate", "peer_premium_tolerance")
        if all(key in policy for key in required_policy):
            mos, incentive, tax, tolerance = (float(policy[key]) for key in required_policy)
            if not (0 <= mos < 1 and incentive >= 0 and 0 <= tax <= 1 and tolerance >= 0):
                raise ValueError("Invalid valuation policy thresholds")
            cost = market["current_price"] / (1 + incentive * (1 - tax))
            threshold = valuation["fair_value_per_share"] * (1 - mos)
            peer_checks = [row["price_premium_to_peer_implied_value"] for row in comparisons.values() if row.get("status") == "MODELED" and row.get("price_premium_to_peer_implied_value") is not None]
            if comparison["status"] == "MODELED":
                peer_checks.append(comparison["relative_fair_value_premium"])
            if peer_checks:
                attractive = cost <= threshold
                peer_ok = all(p <= tolerance for p in peer_checks)
                action = "consider_increase" if attractive and peer_ok else "avoid_increase" if not attractive else "review_peer_premium"
                signal = {"status": "INDICATIVE", "action": action, "effective_personal_purchase_cost": cost,
                          "target_cost": threshold, "meets_margin_of_safety": attractive, "peer_checks_pass": peer_ok,
                          "execution": "Agent must check affordability, concentration and actual plan constraints before a contribution conclusion"}
            else:
                signal["reasons"].append("Comparable peer evidence incomplete")
        else:
            signal["reasons"].append("Dialogue-established policy thresholds incomplete")
    else:
        signal["reasons"].append("Target valuation or dated market evidence incomplete")
    if request.get("example_only") or manifest.get("example_only"):
        signal = {"status": "SYNTHETIC", "action": "example_only", "simulated_signal": signal}
    return {"currency": "JPY", "as_of": now.isoformat(), "company_id": company["id"], "market": market,
            "policy": request.get("policy", {}), "max_quote_age_hours": age_limit,
            "valuation": valuation, "peers": rows, "peer_multiple_comparison": comparisons,
            "peer_fair_value_premium": comparison, "purchase_signal": signal,
            "status": "completed" if signal["status"] == "INDICATIVE" else "partial"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Agent-normalized financial evidence and assumptions")
    parser.add_argument("--market-manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = evaluate(json.loads(Path(args.input).read_text(encoding="utf-8")), json.loads(Path(args.market_manifest).read_text(encoding="utf-8")))
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"status": result["status"], "action": result["purchase_signal"]["action"], "artifact_path": str(Path(args.output).resolve())}))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
