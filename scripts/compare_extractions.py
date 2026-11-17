"""Compare two independently transcribed contribution cases, retaining source differences."""
import argparse
import csv
import json
import math
from pathlib import Path


def leaves(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from leaves(value, (*path, key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            label = index
            if isinstance(value, dict):
                for field in ("ticker", "fy", "company", "name"):
                    if field in value:
                        label = value[field]
                        break
            yield from leaves(value, (*path, str(label)))
    else:
        yield ".".join(path), node


def load(directory, name):
    return json.loads((directory / name).read_text(encoding="utf-8-sig"))


def compare(left, right, output, inputs_only=False):
    output.mkdir(exist_ok=True, parents=True)
    summary = {}
    from check_filing_rows import observations
    facts = [load(d, "financial.json") for d in (left, right)]
    if all("tables" in f for f in facts):
        def normalized(f):
            data = {(kind, day.isoformat(), field): value
                    for kind, dates in observations(f).items()
                    for day, fields in dates.items() for field, value in fields.items()}
            if "product_tables" in f:
                from product_filing_model import read_product_tables
                for (scope,kind,end,field), (_,value,_) in read_product_tables(f).items():
                    data[(scope+"/"+kind,end.isoformat(),field)]=value
            return data
        aa, bb = map(normalized, facts)
        with (output / "observations.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(("kind","period_end","field","A","B","B minus A"))
            differences = []
            for key in sorted(aa.keys() | bb.keys()):
                delta = bb[key]-aa[key] if key in aa and key in bb else None
                writer.writerow((*key, aa.get(key), bb.get(key), delta))
                if delta is None or not math.isclose(delta,0,abs_tol=1e-9):
                    differences.append(key)
        summary["normalized_observations"] = {"total":len(aa.keys() | bb.keys()),"differences":differences}
        summary["models"] = [f["model"] for f in facts]
    with (output / "fields.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(("file", "field", "A", "B", "comparison"))
        names = ["financial.json","market.json","case.json"]
        for name in names if inputs_only else [*names,"decision.json"]:
            a, b = (dict(leaves(load(d, name))) for d in (left, right))
            counts = {}
            for field in sorted(a.keys() | b.keys()):
                x, y = a.get(field), b.get(field)
                if field not in a or field not in b:
                    result = "A only" if field in a else "B only"
                elif type(x) in (int, float) and type(y) in (int, float):
                    result = "match" if math.isclose(x,y,rel_tol=1e-12,abs_tol=1e-10) else "different"
                else:
                    result = "match" if x == y else "different"
                counts[result] = counts.get(result, 0) + 1
                writer.writerow((name, field, json.dumps(x,ensure_ascii=False) if field in a else "",
                                 json.dumps(y,ensure_ascii=False) if field in b else "", result))
            summary[name] = counts
    markets = [load(d, "market.json") for d in (left, right)]
    companies = [{str(row["ticker"]):row for row in [m["target"], *m["peers"]]} for m in markets]
    peer_differences = []
    with (output / "market-observations.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(("ticker","field","A","B","comparison"))
        for ticker in sorted(companies[0].keys() | companies[1].keys()):
            for field in ("close_date","close","fiscal_year_end","eps","site_date","site_pe"):
                values = [table.get(ticker,{}).get(field) for table in companies]
                match = values[0]==values[1] and all(ticker in table for table in companies)
                writer.writerow((ticker,field,*values,"match" if match else "different"))
                if not match:
                    peer_differences.append((ticker,field))
    summary["market_observation_differences"]=peer_differences
    if inputs_only:
        (output / "summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
        return summary
    a, b = (load(d, "decision.json") for d in (left, right))
    if any(d["status"] != "review_ready" for d in (a,b)):
        raise ValueError("Both cases must have completed the contribution review")
    if (a["ticker"],a["market_date"]) != (b["ticker"],b["market_date"]):
        raise ValueError("Different companies or valuation dates")
    summary["range_difference_B_minus_A"] = {
        k: b["decision_fair_value_range_per_share"][k] - a["decision_fair_value_range_per_share"][k]
        for k in ("low","high")}
    summary["decisions"] = [d["contribution_comparison"]["decision"] for d in (a,b)]
    summary["stable_fcff_billion_jpy"] = {}
    for side in ("low","high"):
        rows = [d["valuation"]["cases"][side]["annual"][-1] for d in (a,b)]
        summary["stable_fcff_billion_jpy"][side] = dict(
            years=[row["fy"] for row in rows], A=rows[0]["fcff"], B=rows[1]["fcff"],
            difference=rows[1]["fcff"]-rows[0]["fcff"])
    (output / "summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for argument in ("left", "right", "output"):
        parser.add_argument(argument, type=Path)
    parser.add_argument("--inputs-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(compare(args.left, args.right, args.output, args.inputs_only), indent=2))
