"""Normalize labelled, dated issuer observations independently of page and column layout."""
from datetime import date, timedelta
import math


MONEY = {"JPY million": .001, "JPY billion": 1., "JPY 100 million": .1,
         "JPY thousand": .000001, "JPY": 1e-9}
SHARES = {"shares": 1e-6, "thousand shares": .001, "million shares": 1.}
SHARE_FIELDS = {"issued_shares", "treasury_shares"}
BALANCE = {"cash", "debt", "lease_debt", "nci", "receivables", "inventory", "payables"} | SHARE_FIELDS
FLOWS = {"sales", "ebit", "da", "capex_cash", "ppe_cash", "intangible_cash"}
PROJECT = {"project_budget", "project_spent"}
FORECAST = {"sales", "ebit", "sales_low", "sales_high", "ebit_low", "ebit_high", "da", "capex_cash"}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def parse_day(text):
    day = date.fromisoformat(text)
    require(day.isoformat() == text, "Use ISO YYYY-MM-DD for all statement dates")
    return day


def is_annual(start, end):
    return 364 <= (end - start).days <= 371


def cells_value(cells, field, unit):
    scales = SHARES if field in SHARE_FIELDS else MONEY
    require(unit in scales, f"Invalid dimension or unit {unit} for {field}")
    if isinstance(cells, list) and len(cells) == 2 and isinstance(cells[0], str):
        cells = [cells]
    require(isinstance(cells, list) and cells, f"Missing issuer cells: {field}")
    values, labels = [], set()
    for cell in cells:
        require(isinstance(cell, list) and len(cell) == 2, f"Expected [original row label, number]: {field}")
        label, value = cell
        require(isinstance(label, str) and label.strip() and label not in labels, f"Empty or duplicate label: {field}")
        require(type(value) in (int, float) and math.isfinite(value), f"Invalid source amount: {field}")
        labels.add(label)
        values.append(value)
    return math.fsum(values) * scales[unit]


def observations(facts):
    cutoff = parse_day(facts["market_date"])
    values = {}
    for t in facts["tables"]:
        start, end, published = (parse_day(t[k]) for k in ("period_start","period_end","published"))
        kind = t["kind"]
        require(start <= end and published <= cutoff, "Invalid observation dates or filing after the close")
        require(str(t["page"]).strip() and isinstance(t["column"], str) and t["column"].strip()
                and t["source_url"].startswith(("https://","http://")), "Supply issuer URL, page/table and exact column caption")
        if kind == "plan":
            require(t["scope"] == "project", "Identify project-specific disclosure scope")
            allowed = PROJECT
        else:
            require(t["scope"] == "consolidated" and kind in ("actual","forecast"), "Use consolidated actuals or forecasts")
            allowed = FORECAST if kind == "forecast" else BALANCE | FLOWS
        require(kind != "actual" or end <= published, "Actual period ends after publication")
        require(kind != "forecast" or is_annual(start,end), "Use full-year guidance")
        for field, cells in t["rows"].items():
            require(field in allowed, f"Unsupported {kind} source field: {field}")
            # Annual operating rows and interim balance sheet rows may come from one filing.
            if kind == "actual" and field in FLOWS:
                require(is_annual(start,end), f"Use an annual period for {field}")
            value = cells_value(cells, field, t["unit"])
            key = (kind, end, field)
            if key in values:
                prev_date, prev_value = values[key]
                if published < prev_date:
                    continue
                require(published != prev_date or math.isclose(prev_value,value,abs_tol=1e-9),
                        f"Ambiguous filing observations for {field} as of {end}")
            values[key] = (published, value)
    groups = {"actual": {}, "forecast": {}, "plan": {}}
    for (kind, end, field), (_, value) in values.items():
        groups[kind].setdefault(end, {})[field] = value
    return groups


def capex(row):
    if "capex_cash" in row:
        require(not {"ppe_cash","intangible_cash"} & row.keys(), "Duplicated combined and separate asset purchase lines")
        return abs(row["capex_cash"])
    return abs(row["ppe_cash"]) + abs(row.get("intangible_cash",0))


def annual_history(groups, anchor):
    actual = groups["actual"]
    ends = sorted(end for end,r in actual.items() if "sales" in r)[-3:]
    require(len(ends)==3, "Extract three consecutive full years before the current guidance")
    for a,b in zip(ends, ends[1:]+[anchor]):
        require(364 <= (b-a).days <= 372, "Annual periods or comparison to current guidance are not consecutive")
    rows = []
    for end in ends:
        a = actual[end]
        require(a["sales"]>0 and a["da"]>=0, "Invalid historical sales or depreciation")
        rows.append(dict(period_end=end.isoformat(),sales=a["sales"],ebit=a["ebit"],depreciation=a["da"],
                         capex=capex(a),nwc=a["receivables"]+a["inventory"]-a["payables"]))
    return rows
