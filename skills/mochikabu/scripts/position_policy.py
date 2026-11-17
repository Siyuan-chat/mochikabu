"""User-defined valuation bands and point-in-time accumulation history."""
from bisect import bisect_right
from datetime import date
from math import isfinite


def number(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value) or value < minimum:
        raise ValueError(f"Invalid {name}")
    return value


def positive(value, name):
    if number(value, name) == 0:
        raise ValueError(f"{name} must be positive")
    return value


def boundaries(values):
    for value in values:
        positive(value, "threshold")
    if not values or sorted(set(values)) != values:
        raise ValueError("Band thresholds must be strictly increasing")
    return values


def decide(config, valuation, price, signal=None):
    position = config["position"]
    policy = config["valuation_policy"]
    employee = position["lifecycle_state"] == "employee"
    if not employee and position["lifecycle_state"] != "former_employee":
        raise ValueError("Unknown lifecycle_state")
    acc, trim = policy["accumulation_bands"], policy["trim_bands"]
    cuts = boundaries([acc["extreme"], acc["strong"], acc["normal"], trim["watch"], trim["partial"], trim["major"]])
    base = positive(valuation["fair_value_per_share"], "base FV")
    ratio = positive(price, "price") / base
    incentive = number(config["incentive_rate"], "incentive") if employee else 0
    tax = number(config["incentive_tax_rate"], "tax") if employee else 0
    if tax > 1:
        raise ValueError("Invalid incentive tax rate")
    effective = price / (1 + incentive * (1 - tax))
    labels = ["EXTREME_UNDERVALUE", "STRONG_ACCUMULATION", "ACCUMULATION", "HOLD", "OVERVALUED_WATCH", "PARTIAL_TRIM", "MAJOR_REVIEW"]
    band = bisect_right(cuts, ratio)
    holding = "MAJOR_TRIM" if band == 6 else "PARTIAL_TRIM" if band == 5 else "LONG_TERM_HOLD"
    contribution = None
    concentration = position.get("portfolio_concentration")
    limit = policy.get("max_concentration")
    for x in (concentration, limit):
        if x is not None and number(x, "concentration") > 1:
            raise ValueError("Invalid concentration fraction")
    if limit is not None and concentration is None and holding == "LONG_TERM_HOLD":
        holding = "REVIEW_CONCENTRATION"
    elif limit is not None and concentration is not None and concentration >= limit and holding == "LONG_TERM_HOLD":
        holding = "REVIEW_CONCENTRATION"
    if employee:
        effective_band = bisect_right(cuts, effective / base)
        if limit is not None and concentration is None:
            contribution = "OPEN"
        elif (limit is not None and concentration >= limit) or effective_band >= 5:
            contribution = "PAUSE_CONTRIBUTION"
        elif effective_band == 4:
            contribution = "REDUCE_CONTRIBUTION"
        elif effective_band < 3 and effective <= base * (1 - config["margin_of_safety"]):
            contribution = "ACCUMULATE" if signal == "consider_increase" else "REVIEW_CONTRIBUTION"
        else:
            contribution = "NORMAL_CONTRIBUTION"
    thesis = position.get("thesis_status", "unknown")
    if thesis not in ("intact", "broken", "unknown"):
        raise ValueError("Unknown thesis status")
    if thesis != "intact":
        holding = "THESIS_REVIEW"
        contribution = "THESIS_REVIEW" if employee else None
    bear = valuation.get("bear_fv")
    return dict(lifecycle_state=position["lifecycle_state"], valuation_band=labels[band],
                price_to_fv=ratio, price_to_bear_fv=price / positive(bear, "bear FV") if bear is not None else None,
                effective_price=effective, effective_price_to_fv=effective / base,
                contribution_state=contribution, holding_state=holding)


def residency(history, company_id, as_of):
    if not company_id or history["company_id"] != company_id or history["currency"] != "JPY":
        raise ValueError("History must match company and currency")
    cuts = boundaries(history["thresholds"])
    end = date.fromisoformat(as_of)
    vintages = sorted((date.fromisoformat(row["date"]), positive(row["base_fv"], "historical FV"))
                      for row in history["valuations"])
    dates = [d for d, _ in vintages]
    if len(set(dates)) != len(dates):
        raise ValueError("Duplicate FV date")
    bins = [dict(lower=lo, upper=hi, days=0, shares=0, personal_cash=0)
            for lo, hi in zip([None] + cuts, cuts + [None])]
    seen = set()
    weighted = total = 0
    for kind in ("closes", "purchases"):
        for row in history[kind]:
            day = date.fromisoformat(row["date"])
            index = bisect_right(dates, day) - 1
            if index < 0 or day > end:
                raise ValueError("Observation outside dated FV coverage or analysis horizon")
            ratio = positive(row["price"], "historical price") / vintages[index][1]
            bucket = bins[bisect_right(cuts, ratio)]
            if kind == "closes":
                if day in seen:
                    raise ValueError("Duplicate daily close")
                seen.add(day)
                bucket["days"] += 1
            else:
                shares = positive(row["shares"], "purchased shares")
                bucket["shares"] += shares
                bucket["personal_cash"] += number(row["personal_cash"], "personal cash")
                weighted += shares * ratio
                total += shares
    return dict(bands=bins, observed_days=len(seen),
                days_below=[dict(threshold=cut, days=sum(b["days"] for b in bins[:i+1])) for i, cut in enumerate(cuts)],
                weighted_average_purchase_p_to_fv=weighted / total if total else None)

