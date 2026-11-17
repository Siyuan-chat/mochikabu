"""Compute both evidence tables before accepting a real contribution review."""
import argparse
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import median

from analyze import dcf_value
from stable_review import stable_review


def require(condition, message):
    if not condition:
        raise ValueError(message)


def source(value):
    require(isinstance(value, str) and value.startswith(("https://", "http://")), "Missing public source URL")


def equity_at_close(model, trading_day):
    """Roll an ex-distribution fiscal-end equity value back at the cost of equity."""
    bridge = model["date_bridge"]
    anchor = date.fromisoformat(bridge["fiscal_end_anchor"])
    days = (anchor - trading_day).days
    require(0 <= days <= 366, "Use the current or next fiscal end as the DCF anchor")
    first_end = date.fromisoformat(bridge["first_full_cash_flow_end"])
    require(364 <= (first_end - anchor).days <= 366, "First full forecast must end one year after anchor")
    require(bridge["first_forecast_fy"] == model["annual_operating_forecast"][0]["fy"],
            "First forecast FY differs from dated bridge")
    require(date.fromisoformat(bridge["net_debt_as_of"]) == anchor, "Net debt must correspond to DCF anchor")
    rate = bridge["cost_of_equity"]
    require(math.isfinite(rate) and rate > 0, "Provide a positive annual cost of equity")
    require(bridge["distribution_basis"].strip(), "Explain dividend eligibility and anchor treatment")
    dividend_pv = 0
    for dist in bridge["distributions"]:
        ex = date.fromisoformat(dist["ex_date"])
        pay = date.fromisoformat(dist["payment_date"])
        require(trading_day < ex <= anchor and pay >= ex, "Distribution outside holding period")
        amount = dist["per_share"]
        require(math.isfinite(amount) and amount >= 0, "Invalid per-share distribution")
        dividend_pv += amount / (1 + rate) ** ((pay - trading_day).days / 365)
    forward = dcf_value(model)
    discount = (1 + rate) ** (days / 365)
    value = forward["fair_value_per_share"] / discount + dividend_pv
    sensitivity = {w: {g: v / discount + dividend_pv if v is not None else None
                       for g, v in grid.items()} for w, grid in forward["sensitivity"].items()}
    return {"valuation_date": trading_day.isoformat(), "fair_value_per_share": value,
            "sensitivity": sensitivity, "annual_operating_forecast": forward["annual_operating_forecast"],
            "date_bridge": dict(bridge, days=days, discount_factor=discount, distribution_pv=dividend_pv),
            "fiscal_end_valuation": forward}


def eps_bounds(eps):
    if isinstance(eps, dict):
        require(set(eps)=={"low","high"}, "EPS range requires both published bounds")
        low, high=eps["low"],eps["high"]
    else:
        low=high=eps
    require(all(type(x) in (int,float) and math.isfinite(x) for x in (low,high)) and low<=high,
            "Invalid issuer EPS guidance")
    return low,high


def peer_table(data, trading_day):
    comparison = []
    ids = set()
    for company in [data["target"], *data["peers"]]:
        ticker = company["ticker"]
        require(ticker not in ids, "Duplicate company: " + ticker)
        ids.add(ticker)
        require(date.fromisoformat(company["close_date"]) == trading_day, "Closing date differs: " + ticker)
        require(date.fromisoformat(company["filing_date"]) <= trading_day, "EPS published after close date")
        require(company["fiscal_year_end"] == data["target"]["fiscal_year_end"], "Mismatched forecast period")
        for key in ("close_url", "filing_url", "product_url"):
            source(company[key])
        require(company["overlap"].strip(), "Explain product and business mix")
        close, eps = company["close"], company["eps"]
        require(type(close) in (int,float) and math.isfinite(close) and close > 0, "Invalid close")
        lower, upper = eps_bounds(eps)
        if lower <= 0:
            ratio = None
        elif isinstance(eps, dict):
            ratio = {"low": close / upper, "high": close / lower}
        else:
            ratio = close / eps
        shown = company.get("site_pe")
        delta = None
        if shown is None:
            require(company.get("site_gap"), "Identify unavailable website evidence")
        else:
            source(company["site_url"])
            require(company["site_date"] == data["market_date"], "Website date differs")
            require(math.isfinite(shown) and shown > 0, "Invalid website P/E")
            if isinstance(ratio, dict):
                delta = {k:v-shown for k,v in ratio.items()}
            elif ratio is not None:
                delta = ratio-shown
        comparison.append(dict(company, calculated_pe=ratio, delta=delta))
    ratios = [r["calculated_pe"] for r in comparison[1:] if r["calculated_pe"] is not None]
    require(ratios, "Find at least one justified core peer or report public research as incomplete")
    if len(ratios) < 3:
        exclusions = data.get("peer_exclusions")
        require(isinstance(exclusions, list) and exclusions, "Document specific excluded candidates")
        for candidate in exclusions:
            require(isinstance(candidate, dict) and candidate.get("name") and candidate.get("reason"),
                    "Identify each excluded candidate and reason")
            source(candidate.get("source_url"))
    lower = median(r["low"] if isinstance(r,dict) else r for r in ratios)
    upper = median(r["high"] if isinstance(r,dict) else r for r in ratios)
    el, eh = eps_bounds(data["target"]["eps"])
    multiple = {"low":lower,"high":upper} if lower!=upper else lower
    implied = None
    if el>0:
        implied = {"low":lower*el,"high":upper*eh} if lower!=upper or el!=eh else lower*el
    return dict(pe_comparison=comparison, peer_median=multiple,
                peer_exclusions=data.get("peer_exclusions", []), peer_implied_price=implied)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def fact_packet(request, directory, key):
    require(key in request, f"Missing independently identified observation file: {key}")
    return read_json(directory / request[key])


def revision_detail(old, new):
    """Keep changes in dated cash flows visible even when the endpoints are unchanged."""
    prior_years = {row["fy"]: row for row in old["annual"]}
    new_years = {row["fy"]: row for row in new["annual"]}
    years = []
    for fy in sorted(set(prior_years) | set(new_years)):
        a, b = prior_years.get(fy), new_years.get(fy)
        if a != b:
            years.append(dict(fy=fy, previous=a, current=b))
    return dict(annual_changes=years, prior_profit_bridge=old["profit_bridge"], current_profit_bridge=new["profit_bridge"],
                prior_reinvestment=old["reinvestment_bridge"], current_reinvestment=new["reinvestment_bridge"],
                prior_equity_bridge=old["date_bridge"], current_equity_bridge=new["date_bridge"])


def money_choice(monthly, multiplier, count, incentive):
    bonus = monthly * multiplier * count
    cash = 12 * monthly + bonus
    return dict(monthly=monthly, annual_personal_bonus=bonus, annual_personal=cash,
                annual_gross_reward=cash * incentive, annual_purchases=cash * (1 + incentive))


def compare_amounts(personal, price, bounds):
    fields = {"monthly", "bonus_multiplier", "bonus_count", "incentive_rate", "employer_stock_share",
              "cash_sufficient", "regular_diversification"}
    require(set(personal) <= fields, "Only observed personal facts are accepted")
    monthly, multiple, count = (personal[k] for k in ("monthly", "bonus_multiplier", "bonus_count"))
    rate, share = personal["incentive_rate"], personal["employer_stock_share"]
    sufficient = personal["cash_sufficient"]
    selling = personal.get("regular_diversification")
    require(type(monthly) is int and monthly > 0 and type(count) is int and count >= 0,
            "Supply positive monthly yen and a nonnegative count of bonus payments")
    require(all(type(n) in (int, float) and math.isfinite(n) and n >= 0 for n in (multiple, rate, share))
            and share <= 1, "Supply nonnegative bonus multiplier and incentive, and a 0–1 asset share")
    require(type(sufficient) is bool and (selling is None or type(selling) is bool),
            "Identify affordability and whether regular diversification is known")
    # Policy v1 compares a one-third reduction, rounded down to a whole yen.
    # The amount is conditional on the plan offering that election.
    reduced = monthly * 2 // 3
    current = money_choice(monthly, multiple, count, rate)
    alternative = money_choice(reduced, multiple, count, rate)
    cost = price / (1 + rate)
    position = "below_range" if cost < bounds["low"] else "above_range" if cost > bounds["high"] else "inside_range"
    reasons = []
    if not sufficient:
        reasons.append("insufficient_cash")
    if position == "above_range":
        reasons.append("reward_adjusted_price_above_entire_range")
    concentrated = share >= 0.10
    if concentrated and selling is not True:
        reasons.append("employer_stock_concentration_if_accumulating")
    condition = concentrated and selling is None and sufficient and position != "above_range"
    return dict(policy_version="contribution_v1", concentration_review_threshold=0.10,
                alternative_basis="Two thirds of current monthly, subject to plan availability; bonus rule unchanged.",
                current=current, alternative=alternative,
                cash_released=current["annual_personal"] - alternative["annual_personal"],
                gross_reward_forgone=current["annual_gross_reward"] - alternative["annual_gross_reward"],
                gross_incentive_adjusted_price=cost, adjusted_cost_position=position,
                fair_value_less_adjusted_cost={k:v-cost for k,v in bounds.items()},
                decision="reduce" if reasons else "maintain", reasons=reasons,
                decision_if_regularly_diversifying="maintain" if condition else None,
                regular_diversification_unknown=selling is None)


def build_review(request, directory, final):
    allowed = {"ticker", "model_id", "market_date", "facts_file", "market_file", "personal", "previous_decision_file"}
    require(set(request) <= allowed, "Submit a model ID and observation files; hand-built DCFs or decisions are invalid")
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", request["ticker"]), "Invalid issuer identifier")
    day = date.fromisoformat(request["market_date"])
    require(day.isoformat() == request["market_date"], "Use YYYY-MM-DD for the completed session")
    facts = fact_packet(request, directory, "facts_file")
    market = fact_packet(request, directory, "market_file")
    if request["model_id"] == "industrial_project_fcff_v1":
        from industrial_model import run_model
        for peer in market["peers"]:
            mix=peer.get("core_sales",{})
            source(mix.get("source_url"))
            amounts=[mix.get(k) for k in ("product_sales","group_sales")]
            require(all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in amounts)
                    and .5 <= amounts[0]/amounts[1] <= 1 and mix.get("locator"),
                    "Use separately disclosed same-product external revenue of at least half of consolidated revenue for the industrial core peer median")
    elif request["model_id"] == "expansion_fcff_v1":
        from product_filing_model import run_model
    else:
        raise ValueError("Select an implemented model matching the disclosed inputs")
    require(facts["model"] == request["model_id"], "Fact packet and selected model differ")
    require(facts["ticker"] == request["ticker"] == market["target"]["ticker"], "Issuer differs between observation files")
    require(facts["market_date"] == market["market_date"] == day.isoformat(), "Observation dates differ from requested close")
    verification = market["disclosure_check"]
    for url in (verification["source_url"], market["guidance_url"], market["project_url"]):
        source(url)
    require(date.fromisoformat(verification["checked_through"]) >= day and verification["changes_and_model_impact"].strip(),
            "Verify public disclosures through the closing session")
    comparisons = peer_table(market, day)
    value = run_model(facts)
    require(value["status"] == "model_ready", "Fixed operating model did not complete")
    bounds = value["fair_value_range_per_share"]
    require(set(bounds) == {"low", "high"} and all(math.isfinite(v) for v in bounds.values())
            and bounds["low"] <= bounds["high"], "Invalid close-date valuation range")
    market_hash = hashlib.sha256(json.dumps(market, sort_keys=True, ensure_ascii=False,
                                            separators=(",", ":")).encode()).hexdigest()
    result = dict(valuation=value, stable_cash_flow_review=stable_review(value, facts), ticker=facts["ticker"], market_date=day.isoformat(),
                  decision_fair_value_range_per_share=bounds, market_inputs_sha256=market_hash,
                  disclosure_check=verification, guidance_url=market["guidance_url"], project_url=market["project_url"],
                  **comparisons)
    if "previous_decision_file" in request:
        prior = read_json(directory / request["previous_decision_file"])
        require(prior.get("market_date") == day.isoformat() and prior.get("ticker") == facts["ticker"],
                "Restate prior and current reviews to the same issuer and date")
        old = prior["decision_fair_value_range_per_share"]
        result["same_date_change"] = dict(prior=old, current=bounds, difference={k:bounds[k]-old[k] for k in bounds},
                                          prior_facts=prior["valuation"]["inputs_sha256"], current_facts=value["inputs_sha256"],
                                          prior_policy=prior["valuation"]["policy_version"], current_policy=value["policy_version"])
        result["same_date_change"]["cases"] = {
            k: revision_detail(prior["valuation"]["cases"][k], value["cases"][k]) for k in bounds}
    if final:
        result["personal"] = request["personal"]
        result["contribution_comparison"] = compare_amounts(request["personal"], market["target"]["close"], bounds)
        comparison = result["contribution_comparison"]
        current = comparison["current"]["monthly"]
        alternative = comparison["alternative"]["monthly"]
        action = f"建议维持每月 {current:,} 日元。"
        if comparison["decision"] == "reduce":
            action = f"如果计划允许，建议从每月 {current:,} 下调至 {alternative:,} 日元。"
            if comparison["decision_if_regularly_diversifying"] == "maintain":
                action += f"如果你定期卖出以分散持股，可以维持每月 {current:,} 日元。"
        position = comparison["adjusted_cost_position"]
        assessment = {"inside_range":"奖励后买价位于区间内，估值不足以支持下调。",
                      "above_range":"奖励后买价高于区间上限，估值支持下调。",
                      "below_range":"奖励后买价低于区间下限，估值不足以支持下调。"}[position]
        share = request["personal"]["employer_stock_share"]
        selling = request["personal"].get("regular_diversification")
        stock_reason = (f"公司股票占资产约 {share:.1%}。"
                        + ("继续累积达到模型的集中度复核线。" if share >= comparison["concentration_review_threshold"] and selling is not True
                           else "定期卖出分散持股，集中度规则没有触发下调。" if selling is True
                           else "目前低于模型的集中度复核线。"))
        result["valuation_assessment_zh"] = assessment
        result["concentration_assessment_zh"] = stock_reason
        audit = result["stable_cash_flow_review"]
        result["answer_zh"] = (
            f"{action}{day.isoformat()} 收盘价为 {market['target']['close']:,.2f} 日元，"
            f"计入税前奖励后每股自付约 {comparison['gross_incentive_adjusted_price']:,.2f} 日元。"
            f"固定模型的每股估值区间为 {bounds['low']:,.2f} 至 {bounds['high']:,.2f} 日元。"
            f"{assessment}{stock_reason}"
            f"稳定期自由现金流分别为 {10*audit['low']:,.2f} 和 {10*audit['high']:,.2f} 亿日元；"
            f"税后营业利润对差额的贡献为 {10*audit['after_tax_operating_effect']:+,.2f} 亿，净再投资的贡献为 {10*audit['net_reinvestment_effect']:+,.2f} 亿。"
            f"两档相比，下调后每年多留 {comparison['cash_released']:,} 日元现金，"
            f"少拿 {comparison['gross_reward_forgone']:,.0f} 日元税前奖励。"
        )
    result["status"] = "review_ready" if final else "public_tables_ready"
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()
    try:
        result = build_review(read_json(args.input), args.input.parent, args.final)
    except (ValueError, KeyError, TypeError, OSError) as error:
        result = {"status": "incomplete", "missing_or_invalid": str(error)}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(result["status"], result.get("missing_or_invalid", ""))
    return int(result["status"] == "incomplete")


if __name__ == "__main__":
    raise SystemExit(main())
