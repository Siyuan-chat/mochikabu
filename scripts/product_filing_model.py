"""Convert labelled source observations into the fixed product-profit milestone DCF."""
import hashlib
import json
import math
import re

from check_filing_rows import annual_history, cells_value, is_annual, observations, parse_day, require
from fixed_model import run_model as calculate


def read_product_tables(facts):
    cutoff = parse_day(facts["market_date"])
    result = {}
    by_scope = {
        "group": {"normalized_ebit", "roic", "net_debt", "dividend", "maintenance",
                  "disposed_sales", "disposed_ebit"},
        "segment": {"normalized_ebit"}, "product": {"sales", "profit_multiple"},
        "peer": {"sales", "ebit"}, "project": {"land", "building", "equipment"},
    }
    for t in facts["product_tables"]:
        start, end, published = (parse_day(t[k]) for k in ("period_start", "period_end", "published"))
        scope, _, name = t["scope"].partition("/")
        kind = t["kind"]
        require(scope in by_scope and bool(name) == (scope in {"peer","segment"}), "Invalid product-model scope")
        require(kind in {"actual","forecast","plan"} and start <= end and published <= cutoff
                and (kind != "actual" or end <= published), "Invalid product observation dates")
        require(t["source_url"].startswith(("https://","http://")) and str(t["page"]).strip()
                and t["column"].strip(), "Product table requires original source, page and column")
        for field, cell in t["rows"].items():
            require(field in by_scope[scope], f"Unsupported field for {scope}: {field}")
            if field in {"normalized_ebit","roic","sales","ebit","disposed_sales","disposed_ebit"}:
                require(is_annual(start,end), f"Use a full fiscal year for {field}")
            if field in {"roic","profit_multiple","dividend"} or scope == "peer":
                units = {"roic":{"percent"},"profit_multiple":{"multiple"},"dividend":{"JPY/share"}}
                require(t["unit"] in units[field] if field in units else
                        bool(re.fullmatch(r"[A-Z]{3}(?: (?:thousand|million|100 million|billion))?", t["unit"])),
                        f"Invalid dimension for {field}")
                require(len(cell)==2 and isinstance(cell[0],str) and cell[0].strip()
                        and type(cell[1]) in (int,float) and math.isfinite(cell[1]), "Invalid source cell")
                value = cell[1] / 100 if field == "roic" else cell[1]
            else:
                value = cells_value(cell, field, t["unit"])
            key = (t["scope"],kind,end,field)
            old = result.get(key)
            if old and old[0] > published:
                continue
            require(not old or old[0] != published or old[1] == value, f"Conflicting source cells: {key}")
            result[key] = (published,value,t)
    return result


def comparable_segments(facts, observations_by_key, history, anchor):
    coverage = facts["segment_coverage"]
    require(coverage.get("basis") and coverage.get("page") and
            str(coverage.get("source_url","")).startswith(("https://","http://")),
            "Identify the issuer's comparable organization and full annual trend table")
    scopes = coverage["scopes"]
    require("group" in scopes and len(scopes)==len(set(scopes)) and
            all(s=="group" or s.startswith("segment/") for s in scopes),
            "Inventory group, segments and consolidation adjustments from the original trend legend")
    required = {parse_day(r["period_end"]) for r in history} | {anchor}
    columns = coverage["columns"]
    require({parse_day(c["period_end"]) for c in columns}==required and len(columns)==len(required),
            "Account for every historical year and the current guidance in the period inventory")
    selected = set()
    for c in columns:
        end = parse_day(c["period_end"])
        kind = "forecast" if end==anchor else "actual"
        require(c.get("column") and c.get("page"),"Identify the source panel and original column")
        if c["status"]=="unavailable":
            require(end!=anchor and c.get("reason") and c.get("checked_sources") and
                    all(str(u).startswith(("https://","http://")) for u in c["checked_sources"]),
                    "Document the original basis and where recast data were sought")
            continue
        require(c["status"]=="comparable" and set(c["control_cells"])==set(scopes),
                "Include every consolidated and segment row in each comparable annual column")
        for scope,cell in c["control_cells"].items():
            key = (scope,kind,end,"normalized_ebit")
            require(key in observations_by_key,"Missing comparable observation: "+str(key))
            control = cells_value(cell,"normalized_ebit",coverage["unit"])
            require(math.isclose(control,observations_by_key[key][1],rel_tol=0,abs_tol=1e-8),
                    "Normalized segment value differs from the full-period control column: "+str(key))
            selected.add(key)
    actual = {key for key in observations_by_key if key[-1]=="normalized_ebit"}
    require(actual==selected,"Submitted segment periods or scopes differ from comparable-period inventory")
    return sorted((end,k) for scope,k,end,_ in selected if scope=="group")


def run_model(facts):
    allowed = {"model","ticker","market_date","tables","product_tables","project","product"}
    require(set(facts)==allowed|{"segment_coverage"} and facts["model"]=="expansion_fcff_v1","Expected product-model filing tables and segment_coverage")
    g = observations(facts)
    x = read_product_tables(facts)
    eligible = [end for end in g["forecast"] if end >= parse_day(facts["market_date"])]
    require(eligible, "Missing eligible full-year issuer guidance")
    anchor = min(eligible)
    cfg, project = facts["product"], facts["project"]
    base, opening, ramp = map(parse_day,(cfg["base_fy_end"],project["operation_fy_end"],project["ramp_fy_end"]))
    require(all((e.month,e.day)==(anchor.month,anchor.day) for e in (base,opening,ramp)),
            "Product base year, opening and ramp must use the issuer's fiscal-end dates")
    def find(scope,kind,end,field):
        require((scope,kind,end,field) in x, f"Missing labelled {scope} {kind} {field} for {end}")
        return x[(scope,kind,end,field)]
    def value(scope,kind,end,field):
        return find(scope,kind,end,field)[1]
    def url(scope,kind,end,field):
        return find(scope,kind,end,field)[2]["source_url"]
    def year(end):
        return end.year-1
    history = []
    annual = annual_history(g,anchor)
    for row in annual:
        end = parse_day(row["period_end"])
        history.append(dict(fy=year(end),sales=row["sales"],ebit=row["ebit"],da=row["depreciation"],
                            capex=row["capex"],nwc=row["nwc"],roic=value("group","actual",end,"roic"),
                            source=url("group","actual",end,"roic")))
    periods = comparable_segments(facts,x,annual,anchor)
    names = sorted({s for s,_,_,_ in x if s.startswith("segment/")})
    segments = [dict(name=s[8:],role="product_pool" if s[8:]==cfg["pool"] else "other",
                     values=[value(s,k,end,"normalized_ebit") for end,k in periods],
                     source=url(s,"forecast",anchor,"normalized_ebit")) for s in names]
    peers = []
    for s in sorted({s for s,_,_,_ in x if s.startswith("peer/")}):
        end = max(e for scope,k,e,field in x if (scope,k,field)==(s,"actual","sales"))
        revenue, profit = (find(s,"actual",end,f) for f in ("sales","ebit"))
        require(revenue[2]["unit"] == profit[2]["unit"],"Peer numerator and denominator must share currency and units")
        peers.append(dict(company=s[5:],sales=revenue[1],ebit=profit[1],source=revenue[2]["source_url"]))
    milestones = sorted(e for s,k,e,f in x if (s,k,f)==("product","plan","profit_multiple"))
    require(milestones and all((e.month,e.day)==(anchor.month,anchor.day) for e in milestones),
            "Product milestones must use issuer fiscal-end dates")
    asset = {f:value("project","plan",ramp,f) for f in ("land","building","equipment")}
    require(math.isclose(sum(asset.values()),g["plan"][ramp]["project_budget"],abs_tol=.001),
            "Project components must reconcile to consolidated project budget")
    maintenance = {}
    for kind, prefix in (("actual","realized_"),("plan","")):
        end = max(e for s,k,e,f in x if (s,k,f)==("group",kind,"maintenance"))
        _, amount, t = find("group",kind,end,"maintenance")
        if kind == "plan":
            check = t.get("revision_check", {})
            require(check.get("checked_through") == facts["market_date"] and
                    str(check.get("index_url","")).startswith(("https://","http://")) and
                    check.get("latest_publication") == t["published"] and check.get("locator")
                    and not re.search(r"前回|当初|旧計画|previous|superseded",t["column"],re.I),
                    "Check management-plan updates through the close and use the latest applicable maintenance column")
        start = parse_day(t["period_start"])
        years = round(((end-start).days+1)/365.25)
        require(years>0 and abs(((end-start).days+1)-years*365.25)<8, "Use complete maintenance-plan periods")
        maintenance["realized_maintenance_total" if prefix else "maintenance_total"]=amount
        maintenance["realized_years" if prefix else "maintenance_years"]=years
    bal = g["actual"][max(end for end,r in g["actual"].items() if "issued_shares" in r)]
    fc = g["forecast"][anchor]
    require({"sales","ebit","da"} <= fc.keys(), "Product model requires published point guidance for sales, EBIT and DA")
    current = dict(sales=fc["sales"],ebit=fc["ebit"],da=fc["da"],net_debt=value("group","forecast",anchor,"net_debt"),
                   shares_million=bal["issued_shares"]-bal["treasury_shares"],
                   dividend=value("group","forecast",anchor,"dividend"),dividend_record_date=cfg["dividend_record_date"])
    if "disposed_segment" in cfg:
        disposal = [find("group","actual",base,field)[2] for field in ("disposed_sales","disposed_ebit")]
        require(all(disposal[0][field] == disposal[1][field] for field in ("source_url","page","column","unit")),
                "Use paired sales and signed profit from the same audited business-separation note and original scale")
        current.update(disposed_segment_name=cfg["disposed_segment"],disposed_base_ebit=value("group","actual",base,"disposed_ebit"),
                       disposed_base_external_sales=value("group","actual",base,"disposed_sales"),
                       disposed_base_source=url("group","actual",base,"disposed_sales"))
    sources = dict(project=url("project","plan",ramp,"equipment"),current=url("group","forecast",anchor,"net_debt"),
                   normalized_group=url("group","forecast",anchor,"normalized_ebit"),product_sales=url("product","actual",base,"sales"),
                   growth_targets=url("product","plan",ramp,"profit_multiple"),plan=t["source_url"])
    model = dict(model=facts["model"],ticker=facts["ticker"],market_date=facts["market_date"],fiscal_end_anchor=anchor.isoformat(),
                 first_forecast_fy=anchor.year,base_period=year(base),periods=[year(e) for e,_ in periods],
                 normalized_group=[value("group",k,e,"normalized_ebit") for e,k in periods],segments=segments,
                 product_sales=value("product","actual",base,"sales"),growth_targets=[dict(fy=year(e),multiple=value("product","plan",e,"profit_multiple")) for e in milestones],
                 peer_margins=peers,project=dict(asset,start_fy=year(opening),end_fy=year(ramp)),plan=maintenance,
                 history=history,current=current,sources=sources)
    result=calculate(model)
    result["inputs_sha256"]=hashlib.sha256(json.dumps(facts,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    return result
