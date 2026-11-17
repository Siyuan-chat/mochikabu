"""Fixed operating DCF for a growth product inside a disclosed segment, JPY billions.

The input is a filing extract, not a forecast. Timing, reinvestment, rates and
scenario construction are versioned code. Neither endpoint is a price target.
"""
import argparse
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path

from analyze import dcf_value


MODEL = "expansion_fcff_v1"
VERSION = "1.0.0"
POLICY = {
    "cash_tax_rate": 0.30, "wacc": 0.08, "cost_of_equity": 0.09, "growth": 0.01,
    "equipment_life_years": [8, 16], "building_life_years": [20, 40],
    "debt_basis": "Fiscal-end net financial debt excludes unpaid ex-dividend liability.",
    "project_schedule": "Entire announced project after anchor; land in first year, building evenly before opening, equipment evenly from first forecast year through final ramp year. No land depreciation.",
    "sales_translation": "At stable product margin the earnings multiple is also the product revenue multiple; other revenue held at comparable base-period level.",
    "growth_spending": "Before maturity, recurring nonproject growth capex is historical cash capex less annualized realized maintenance, floored at zero. At maturity use the greater of that proxy and the investment needed for growth at historical consolidated ROIC, net of NWC and net maintenance. Historical ROIC is a proxy, not a measured marginal return.",
    "profit_range": "Weak case holds product profit at base level despite investment. Strong case attains issuer's final product target. Other non-pool business lines use one simultaneous observed period at each endpoint. No individual undisclosed product is assigned a reported EBIT.",
    "tax_basis": "Versioned 30% cash tax convention with no immediate negative-tax refund for losses.",
    "rates_basis": "Illustrative nominal JPY discount/growth policy, not issuer guidance or measured capital costs.",
}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, key):
    need(type(value) in (int, float) and math.isfinite(value), f"Missing finite filing amount: {key}")
    return value


def source(url):
    need(isinstance(url, str) and url.startswith(("http://", "https://")), "Missing public filing URL")


def inputs(f):
    need(f["model"] == MODEL and f["ticker"], "Unsupported model or missing ticker")
    allowed = {"model", "market_date", "fiscal_end_anchor", "first_forecast_fy", "history",
               "segments","normalized_group","periods","base_period","product_sales",
               "peer_margins","growth_targets","project","plan","current","sources","ticker","notes","metadata"}
    need(not (set(f) - allowed), "Only documented filing extract fields are accepted: " + str(set(f)-allowed))
    for key in ("project", "plan", "current", "product_sales", "growth_targets", "normalized_group"):
        source(f["sources"][key])
    history = sorted(f["history"], key=lambda h: h["fy"])
    periods, segments = f["periods"], f["segments"]
    need(len(history) >= 3 and len({h["fy"] for h in history}) == len(history), "Need three distinct completed financial years")
    need(len(set(periods)) == len(periods) >= 2 and periods == sorted(periods), "Need successive comparable segment periods")
    need(sum(r["role"] == "product_pool" for r in segments) == 1 and all(r["role"] in ("product_pool","other") for r in segments), "Separate one product pool and each other segment, including adjustments")
    need(len({r["name"] for r in segments}) == len(segments), "Duplicate reporting segment")
    for row in segments:
        source(row["source"])
        need(len(row["values"]) == len(periods), "Missing comparable segment observation")
        for v in row["values"]:
            number(v, row["name"])
    groups = f["normalized_group"]
    need(len(groups) == len(periods), "Missing group control total")
    # Displayed source amounts may individually round to the nearest JPY 0.1bn.
    for i, total in enumerate(groups):
        need(abs(sum(r["values"][i] for r in segments)-number(total,"normalized EBIT")) <= .05*(len(segments)+1)+1e-8, "Disclosed segments do not reconcile to normalized group EBIT")
    for h in history:
        source(h["source"])
        for k in ("sales","ebit","capex","da","nwc"):
            number(h[k],k)
        need(h["sales"] > 0 and min(h["capex"],h["da"])>=0, "Invalid cash capex, revenue or depreciation")
    need(sum(h.get("roic") is not None and 0 < number(h["roic"],"ROIC") < 1 for h in history)>=2,"Need at least two positive realized ROIC observations (decimal)")
    peers = f["peer_margins"]
    need(len({p["company"] for p in peers}) == len(peers) >= 2, "Need two distinct operating peer observations")
    for p in peers:
        source(p["source"])
        need(number(p["sales"],"peer sales") > 0 and 0 < number(p["ebit"],"peer earnings") < p["sales"], "Peer margin policy requires positive operating observations")
    c, plan, proj = f["current"],f["plan"],f["project"]
    for k in ("maintenance_total","maintenance_years","realized_maintenance_total","realized_years"):
        need(number(plan[k],k)>0, "Invalid maintenance disclosure")
    for k in ("equipment","building","land"):
        need(number(proj[k],k)>=0,"Negative project budget")
    for k in ("da","net_debt","sales","ebit","shares_million","dividend"):
        number(c[k],k)
    need(c["sales"]>0 and c["shares_million"]>0 and min(c["da"],c["dividend"])>=0,"Invalid current guidance")
    need(number(f["product_sales"],"base product sales")>0,"Missing product sales")
    t=f["growth_targets"]
    need(len(t)>=1 and [x["fy"] for x in t] == sorted({x["fy"] for x in t}) and all(number(x["multiple"],"multiple")>=1 for x in t),"Need dated disclosed growth targets")
    first=f["first_forecast_fy"]
    need(first < proj["start_fy"] <= proj["end_fy"] == t[-1]["fy"],"Forecast must cover construction and final target")
    need(f["base_period"] in periods and f["base_period"] in {h["fy"] for h in history},"Missing comparable product base FY")
    need(periods[-1]==first-1 and history[-1]["fy"]<=periods[-1],"Guidance and forecast do not line up")
    a=date.fromisoformat(f["fiscal_end_anchor"]); day=date.fromisoformat(f["market_date"])
    need(0<=(a-day).days<=366 and a.year==first,"Dates inconsistent with fiscal-end anchor")
    return history


def earnings(f, strong):
    pick = max if strong else min
    seg, periods = f["segments"], f["periods"]
    pool = next(s for s in seg if s["role"]=="product_pool")
    other = [s for s in seg if s["role"]!="product_pool"]
    i = periods.index(f["base_period"])
    # Apply one historical cycle-state across all other businesses, preserving covariance.
    other_totals = [f["normalized_group"][j]-pool["values"][j] for j in range(len(periods))]
    disposed=f["current"].get("disposed_base_ebit")
    if disposed is not None:
        source(f["current"]["disposed_base_source"])
        number(disposed,"disposed EBIT")
        disposed_segment=f["current"]["disposed_segment_name"]
        need(disposed_segment in {s["name"] for s in other},"Disposed business must map to a non-product segment")
        other_totals[i]-=disposed
    j = other_totals.index(pick(other_totals))
    margin = pick(p["ebit"]/p["sales"] for p in f["peer_margins"])
    product = f["product_sales"]*margin
    multiple = f["growth_targets"][-1]["multiple"] if strong else 1
    residual = pool["values"][i]-product
    rows=[{"name":s["name"],"amount":s["values"][j],"source":s["source"],"period":periods[j]} for s in other]
    if disposed is not None and j==i:
        rows.append({"name":"Exclude divested operation in "+disposed_segment,"amount":-disposed,
                     "period":periods[i],"source":f["current"]["disposed_base_source"]})
    rounding = f["normalized_group"][j]-sum(s["values"][j] for s in seg)
    profit = other_totals[j]+residual+product*multiple
    return dict(ebit=profit, product_peer_margin=margin, product_base_ebit_proxy=product,
                product_multiple=multiple, product_endpoint_ebit=product*multiple,
                product_pool_base=pool["values"][i], other_products_residual=residual,
                other_product_disclosure="Combined unallocated balance. Standalone EBIT unavailable.",
                product_pool_period=periods[i], other_businesses=rows, rounding=rounding,
                non_product_ebit=other_totals[j]+residual)


def milestone_progress(f, year):
    """Interpolate the issuer's relative profit targets, never book the whole uplift on opening."""
    initial=f["first_forecast_fy"]-1
    milestones=[(initial,1.0)]+[(t["fy"],t["multiple"]) for t in f["growth_targets"] if t["fy"]>initial]
    last=milestones[-1][1]
    need(last>1,"Selected expansion model requires a positive final uplift")
    prior_y,prior_m=milestones[0]
    for y,m in milestones[1:]:
        need(m>=prior_m, "Expansion targets must be nondecreasing")
        if year<=y:
            v=prior_m+(m-prior_m)*(year-prior_y)/(y-prior_y)
            return (v-1)/(last-1)
        prior_y,prior_m=y,m
    return 1.0


def dividend_bridge(curr, day, anchor):
    dividend=curr["dividend"]
    pay=(date.fromisoformat(curr["dividend_pay_date"]) if curr.get("dividend_pay_date")
         else anchor+timedelta(days=91))
    if not dividend:
        return 0.0,0.0,pay
    record=curr.get("dividend_record_date")
    ex=curr.get("dividend_ex_date")
    need(ex or record, "Missing dividend eligibility date")
    if ex:
        ex_day=date.fromisoformat(ex)
        entitled=day < ex_day
        ex_by_anchor=ex_day <= anchor
    else:
        # A record date is not an exchange ex-date. Accept only an unambiguous
        # position well before, or after, record. Near the boundary require the exchange row.
        record_day=date.fromisoformat(record)
        need(day >= record_day or day < record_day-timedelta(days=14),
             "Near dividend record date: supply the actual exchange ex-date")
        need(anchor >= record_day or anchor < record_day-timedelta(days=14),
             "Anchor near dividend record date: supply the exchange ex-date")
        entitled=day < record_day-timedelta(days=14)
        ex_by_anchor=record_day <= anchor
    need(not curr.get("dividend_pay_date") or pay>=date.fromisoformat(ex or record), "Invalid dividend payment date")
    # Fiscal-end liabilities are independent of whether today's buyer owns the payout.
    liability=dividend*curr["shares_million"]/1000 if ex_by_anchor and pay>anchor else 0.0
    due=dividend if entitled and ex_by_anchor else 0.0
    return liability,due,pay


def endpoint(f, history, strong):
    bridge=earnings(f,strong)
    curr,plan,p=f["current"],f["plan"],f["project"]
    first,opening,end=f["first_forecast_fy"],p["start_fy"],p["end_fy"]
    growth=POLICY["growth"]
    annual_past=plan["realized_maintenance_total"]/plan["realized_years"]
    annual_plan=plan["maintenance_total"]/plan["maintenance_years"]
    pick=max if strong else min
    roic=pick(h["roic"] for h in history if h.get("roic") is not None and 0<h["roic"]<1)
    spending_pick=min if strong else max
    old_maint=spending_pick(annual_plan,annual_past)
    nonproject_growth=spending_pick(max(0,h["capex"]-annual_past) for h in history)
    nwc_ratio=spending_pick(h["nwc"]/h["sales"] for h in history)
    life_index=1 if strong else 0
    annual_plant=p["equipment"]/POLICY["equipment_life_years"][life_index]+p["building"]/POLICY["building_life_years"][life_index]
    sales_base=next(h["sales"] for h in history if h["fy"]==f["base_period"])
    disposed=curr.get("disposed_base_external_sales")
    if disposed is not None:
        source(curr["disposed_base_source"])
        need(0<=number(disposed,"disposed base external sales")<=sales_base-f["product_sales"], "Disposed revenue outside base")
        sales_base-=disposed
    end_sales=sales_base+f["product_sales"]*(bridge["product_multiple"]-1)
    prev_sales=curr["sales"]; rows=[]
    for fy in range(first,end+2):
        progress=milestone_progress(f,fy)
        utilization=max(0,min(1,(fy-opening+1)/(end-opening+1)))
        stable=fy>end
        sales=curr["sales"]+(end_sales-curr["sales"])*progress
        if stable:
            sales=prev_sales*(1+growth)
        nwc=(sales-prev_sales)*nwc_ratio
        prev_sales=sales
        normalized_start=f["normalized_group"][-1]
        ebit=normalized_start+(bridge["ebit"]-normalized_start)*progress
        if stable:
            ebit *= 1+growth
        tax=max(0,ebit)*POLICY["cash_tax_rate"]
        depreciation=curr["da"]+annual_plant*utilization
        maintenance=old_maint+annual_plant*utilization
        project_land=p["land"] if fy==first else 0.0
        project_build=p["building"]/(opening-first) if fy<opening else 0.0
        project_equip=p["equipment"]/(end-first+1) if fy<=end else 0.0
        project=project_land+project_build+project_equip
        required=(ebit-tax)*growth/roic if stable else None
        growth_capex=max(nonproject_growth,required-nwc-maintenance+depreciation) if stable else nonproject_growth
        capex=maintenance+growth_capex+project
        cf=ebit-tax+depreciation-capex-nwc
        rows.append(dict(fy=fy,stage="stable" if stable else ("construction" if fy<opening else "ramp"),
            sales=sales,ebit=ebit,cash_tax=tax,depreciation=depreciation,maintenance_capex=maintenance,
            growth_capex=growth_capex,project_capex=project,project_land=project_land,project_building=project_build,
            project_equipment=project_equip,capex=capex,change_nwc=nwc,fcff=cf,required_growth_reinvestment=required))
    w=POLICY["wacc"]; eq=POLICY["cost_of_equity"]
    day=date.fromisoformat(f["market_date"]); anchor=date.fromisoformat(f["fiscal_end_anchor"])
    liability,amount,payment=dividend_bridge(curr,day,anchor)
    model=dict(wacc=w,terminal_growth=growth,net_debt_billion=curr["net_debt"]+liability,
        shares_million_post_split=curr["shares_million"],annual_operating_forecast=rows)
    value=dcf_value(model)["fair_value_per_share"]
    factor=(1+eq)**((anchor-day).days/365)
    payout_pv=amount/(1+eq)**((payment-day).days/365)
    return dict(annual=rows,profit_bridge=bridge,reinvestment_bridge={
        "base_maintenance_observed_annual":[annual_past,annual_plan],"existing_maintenance":old_maint,
        "actual_guidance_ebit":curr["ebit"], "starting_normalized_guidance_ebit":f["normalized_group"][-1],
        "new_plant_replacement_annual":annual_plant,"capex_less_realized_maintenance_proxy":[max(0,h["capex"]-annual_past) for h in history],
        "ex_project_growth_proxy":nonproject_growth,"working_capital_sales_ratio":nwc_ratio,
        "disposed_base_external_sales_excluded":disposed, "scope_limit":"If disposed consolidated external sales are not separately disclosed, the sales proxy retains the base-year scope, affecting working capital.",
        "historical_roic_proxy":roic,"terminal_net_reinvestment":rows[-1]["capex"]-rows[-1]["depreciation"]+rows[-1]["change_nwc"]},
        date_bridge=dict(anchor=anchor.isoformat(),days=(anchor-day).days,discount_factor=factor,
            net_debt=curr["net_debt"],dividend_liability=liability,dividend_pv=payout_pv,
            payment_date=payment.isoformat(),payment_date_assumed=not bool(curr.get("dividend_pay_date"))),
        fiscal_end_fair_value_per_share=value,fair_value_per_share=value/factor+payout_pv)


def run_model(facts):
    history=inputs(facts)
    raw=json.dumps(facts,allow_nan=False,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
    cases={"weak_execution":endpoint(facts,history,False),"target_execution":endpoint(facts,history,True)}
    ordered=sorted(cases,key=lambda k:cases[k]["fair_value_per_share"])
    endpoints={label:dict(cases[name],scenario=name) for label,name in zip(("low","high"),ordered)}
    bounds={k:v["fair_value_per_share"] for k,v in endpoints.items()}
    return dict(status="model_ready",model_id=MODEL,policy_version=VERSION,ticker=facts["ticker"],
        trading_date=facts["market_date"],inputs_sha256=hashlib.sha256(raw).hexdigest(),policy=POLICY,
        sources=facts["sources"],cases=endpoints,fair_value_range_per_share=bounds,
        range_interpretation="Conditional stress scenarios; not statistically estimated limits or an identified fair-value point.")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("input",type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    try:
        result=run_model(json.loads(args.input.read_text(encoding="utf-8-sig")))
    except (ValueError,KeyError,TypeError,OSError) as error:
        result={"status":"incomplete","missing_or_invalid":str(error)}
    args.output.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2),encoding="utf-8")
    print(result["status"],result.get("missing_or_invalid",""))
    return int(result["status"]=="incomplete")


if __name__ == "__main__":
    raise SystemExit(main())
