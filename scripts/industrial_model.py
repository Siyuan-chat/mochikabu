"""Versioned group DCF for an industrial issuer with disclosed plant budget and dates."""
from datetime import date
import hashlib
import json
import math
from check_filing_rows import observations, annual_history, parse_day, require

MODEL = "industrial_project_fcff_v1"
POLICY = dict(wacc=.08, cash_tax_rate=.30, terminal_growth=0., composite_plant_life=20,
    horizon="Through third operating anniversary, minimum five full years after guidance.",
    project_profit="No separate incremental project profit assigned; issuer revenue guidance held flat after guidance.",
    project_spending="Spread remaining disclosed cash budget across remaining construction years including commissioning. If already started without cumulative spent disclosure, remaining spend ranges from zero to full budget.",
    replacement="Historical consolidated D&A/sales proxy for legacy replacement. Stress uses the larger of that and historical cash capex/sales; historical nonmaintenance spending may overstate this proxy.",
    debt_basis="Most recent disclosed consolidated closing cash less interest-bearing debt including lease debt and book noncontrolling interests. Balance sheet held unchanged from its reporting date to valuation; operating enterprise is valued directly at the close.")


def step_year(end, count):
    try:
        return end.replace(year=end.year + count)
    except ValueError:
        return end.replace(year=end.year + count, day=28)


def limits(row, field):
    if field in row:
        require(field+"_low" not in row and field+"_high" not in row, "Conflicting point and forecast interval")
        return row[field],row[field]
    low,high=row[field+"_low"],row[field+"_high"]
    require(low<=high,"Reversed guidance interval: "+field)
    return low,high


def value_case(history, guidance, balance, shares, last_history, anchor, close, start, opening, budget, spent, not_started, stress):
    pick=min if stress else max
    margins=[r["ebit"]/r["sales"] for r in history]
    sales=limits(guidance,"sales")[0 if stress else 1]
    guided=limits(guidance,"ebit")[0 if stress else 1]
    require(sales>0,"Expected positive consolidated revenue")
    margin=pick(margins+[guided/sales])
    da_ratio=pick(r["depreciation"]/r["sales"] for r in history)
    capex_ratio=max(r["capex"]/r["sales"] for r in history)
    replacement_ratio=max(da_ratio,capex_ratio) if stress else da_ratio
    working_ratios=[r["nwc"]/r["sales"] for r in history]
    working_ratio=(max if stress else min)(working_ratios)
    projection_years=max(5,opening.year-anchor.year+3)
    year_ends=[step_year(anchor, i) for i in range(projection_years+1)]
    first_start=step_year(anchor,-1)
    stub=(anchor-close).days/(anchor-first_start).days
    durations={}
    for index,end in enumerate(year_ends):
        if start<=end<=opening:
            durations[end]=stub if index==0 else 1.
    remaining=budget-spent if spent is not None else (budget if not_started or stress else 0.)
    denom=sum(durations.values())
    require(denom>0 or remaining==0, "No remaining construction period for the disclosed outlay")
    previous_sales=history[-1]["sales"]
    annual=[]
    pv=0.
    for i,end in enumerate(year_ends):
        fraction=stub if i==0 else 1.
        project=remaining*durations.get(end,0)/denom if denom else 0.
        ramp=min(1,max(0,(i-(opening.year-anchor.year)+1)/3))
        # One third of the composite plant enters service at each operating stage.
        increment_da=budget/POLICY["composite_plant_life"]*ramp
        ebit=guided if i==0 else guided + (sales*margin-guided)*min(1,i/3)
        da=(guidance.get("da",sales*da_ratio) if i==0 else sales*da_ratio+increment_da)
        replacement=sales*replacement_ratio+increment_da
        maintenance=replacement*fraction
        # Guidance capex includes the same project. Never add it twice.
        annual_capex=abs(guidance.get("capex_cash",0))*fraction if i==0 else 0.
        growth=max(0., annual_capex-maintenance-project)
        capex=maintenance+growth+project
        nwc=(sales-previous_sales)*working_ratio*fraction
        previous_sales=sales
        tax=max(ebit,0.)*POLICY["cash_tax_rate"]*fraction
        fcff=ebit*fraction-tax+da*fraction-capex-nwc
        discount=(1+POLICY["wacc"])**((end-close).days/365.25)
        pv+=fcff/discount
        annual.append(dict(fy=end.year,period_end=end.isoformat(),fraction=fraction,stage="stable" if i==projection_years else
                           "ramp" if 0<ramp<1 else "operating" if ramp else "construction" if end>=start else "preconstruction",
                           sales=sales*fraction,ebit=ebit*fraction,cash_tax=tax,depreciation=da*fraction,
                           maintenance_capex=maintenance,project_capex=project,growth_capex=growth,
                           capex=capex,change_nwc=nwc,fcff=fcff))
    terminal=annual[-1]["fcff"]/POLICY["wacc"]
    enterprise=pv+terminal/discount
    equity=enterprise+balance["cash"]-balance["debt"]-balance.get("lease_debt",0)-balance.get("nci",0)
    return dict(scenario="weak" if stress else "favorable",annual=annual,
                profit_bridge=dict(guided_ebit=guided,historical_group_margins=margins,stable_group_margin=margin,
                                   standalone_project_profit="undisclosed; no separate earnings uplift booked"),
                reinvestment_bridge=dict(project_budget=budget,remaining_project_at_close=remaining,total_project_in_forecast=sum(r["project_capex"] for r in annual),
                                         legacy_da_ratio=da_ratio,replacement_ratio=replacement_ratio,working_capital_ratio=working_ratio),
                date_bridge=dict(valuation_date=close.isoformat(),balance_as_of=last_history.isoformat(),first_period_end=anchor.isoformat(),
                                 cash=balance["cash"],debt=balance["debt"],lease_debt_additional=balance.get("lease_debt",0),
                                 noncontrolling_interests=balance.get("nci",0),shares_million=shares,stub_fraction=stub),
                enterprise_value_billion=enterprise,terminal_pv_billion=terminal/discount,explicit_pv_billion=pv,
                fair_value_per_share=max(0.,equity)*1000/shares)


def run_model(facts):
    require(set(facts)<= {"ticker","model","market_date","tables","project","notes","guidance_check"}, "Submit only observed tables and project dates")
    require(facts["model"]==MODEL,"Unsupported plant model")
    close=parse_day(facts["market_date"])
    g=observations(facts)
    anchor=min((d for d in g["forecast"] if d>=close),default=None)
    require(anchor is not None and (anchor-close).days<=366,"Supply current fiscal year guidance as of the close")
    checks=facts.get("guidance_check",{})
    for field in ("da","capex_cash"):
        check=checks.get(field,{})
        require(check.get("source_url","").startswith(("https://","http://")) and check.get("locator"),
                "Review the latest full-year supplementary forecast and record the page and basis for "+field)
        require(check.get("status") in {"reported","not_disclosed","different_basis"}
                and (check["status"]=="reported")== (field in g["forecast"][anchor]),
                "Forecast evidence status and extracted amount differ: "+field)
    history=annual_history(g,anchor)
    balance_date=max((d for d,r in g["actual"].items() if any(k in r for k in ("cash","debt","issued_shares"))),default=None)
    require(balance_date is not None and (close-balance_date).days<=366,"Supply recent consolidated balance sheet and share count")
    b=g["actual"][balance_date]
    shares=b["issued_shares"]-b["treasury_shares"]
    require(shares>0 and min(b["cash"],b["debt"],b.get("lease_debt",0),b.get("nci",0))>=0,
            "Invalid net debt, minority interest or outstanding share inputs")
    p=facts["project"]
    require(set(p)<={"name","start_fy_end","operation_fy_end","start_month","operation_month"} and p["name"].strip(),"Supply project name and disclosed fiscal-year schedule")
    start,opening=(parse_day(p[k]) for k in ("start_fy_end","operation_fy_end"))
    require(start<=opening and opening>=anchor and opening==step_year(anchor,opening.year-anchor.year)
            and start==step_year(anchor,start.year-anchor.year),"Align announced project timing to the issuer's fiscal year ends")
    require(opening.year-anchor.year<=30, "Check project year or applicable model")
    plan=g["plan"][opening]
    budget,spent=plan["project_budget"],plan.get("project_spent")
    require(budget>0 and (spent is None or 0<=spent<=budget),"Check project amount or cumulative cash already spent")
    not_started=start>anchor
    for key, fiscal_end in (("start_month",start),("operation_month",opening)):
        if key in p:
            month=parse_day(p[key]+"-01")
            require(step_year(fiscal_end,-1)<month<=fiscal_end,"Reported calendar month outside its mapped fiscal year")
            if key=="start_month":
                not_started=month>close
    cases=[value_case(history,g["forecast"][anchor],b,shares,balance_date,anchor,close,start,opening,budget,spent,not_started,s) for s in (True,False)]
    cases.sort(key=lambda c:c["fair_value_per_share"])
    endpoints=dict(zip(("low","high"),cases))
    digest=hashlib.sha256(json.dumps(facts,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return dict(status="model_ready",model_id=MODEL,policy_version="1.1.0",inputs_sha256=digest,ticker=facts["ticker"],
                trading_date=close.isoformat(),policy=POLICY,project=p,history=history,
                sources=sorted({t["source_url"] for t in facts["tables"]}),cases=endpoints,
                range_interpretation="Conditional operating scenarios; group margins, asset replacement and commissioning are uncertain.",
                fair_value_range_per_share={k:c["fair_value_per_share"] for k,c in endpoints.items()})
