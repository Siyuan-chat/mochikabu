"""Attribute the cash-flow spread between the two valuation endpoints, before rounding."""
import math


def stable_review(value, facts):
    cases = [value["cases"][key] for key in ("low", "high")]
    low, high = [case["annual"][-1] for case in cases]
    if low["fy"] != high["fy"] or any(r["stage"] != "stable" for r in (low, high)):
        raise ValueError("Missing comparable stable years for endpoint review")
    product = value["model_id"] == "expansion_fcff_v1"
    definitions = [
        ("ebit", "营业利润", 1, {"ebit","normalized_ebit","disposed_ebit","sales","profit_multiple"}, "分部利润、同业利润率和公司产品目标" if product else "历史集团营业利润率和全年指引"),
        ("cash_tax", "现金税", -1, set(), "固定税率作用于模型营业利润"),
        ("depreciation", "折旧", 1, {"da","building","equipment","project_budget"}, "既有折旧加投产后按模型寿命计提的折旧"),
        ("maintenance_capex", "维护更新投资", -1, {"maintenance","building","equipment","da","project_budget","ppe_cash","intangible_cash","capex_cash"}, "原有资产维护与新厂替换支出"),
        ("growth_capex", "增长投资", -1, {"roic","maintenance","ppe_cash","intangible_cash","capex_cash"}, "历史投资与稳定增长所需再投资" if product else "合并开支扣除已计入的维护与项目支出"),
        ("project_capex", "项目建设支出", -1, {"land","building","equipment","project_budget","project_spent"}, "按模型建设进度分摊"),
        ("change_nwc", "新增营运资金", -1, {"receivables","inventory","payables","sales","disposed_sales"}, "模型收入变化乘以历史营运资金占比"),
    ]
    ledger = []
    for table in [*facts["tables"], *facts.get("product_tables", [])]:
        peer = table["scope"].startswith("peer/")
        for field, cells in table["rows"].items():
            ledger.append(dict(field=field, origin="同业代理" if peer else "公司披露", scope=table["scope"],
                               kind=table["kind"], period_end=table["period_end"], published=table["published"],
                               unit=table["unit"], cells=cells, url=table["source_url"], page=table["page"], column=table["column"]))
    rows = []
    for field, label, sign, inputs, basis in definitions:
        rows.append(dict(field=field,label=label,low=low[field],high=high[field],
                         cash_flow_effect=sign*(high[field]-low[field]),origin="模型推算",basis=basis,
                         evidence_indices=[i for i, item in enumerate(ledger) if item["field"] in inputs
                                           and (field=="ebit" or item["origin"]!="同业代理")]))
    for endpoint in (low, high):
        total = math.fsum(sign*endpoint[field] for field,_,sign,_,_ in definitions)
        if not math.isclose(total,endpoint["fcff"],abs_tol=1e-8,rel_tol=1e-12):
            raise ValueError("Stable FCFF components do not reconcile")
    gap = high["fcff"]-low["fcff"]
    operating = rows[0]["cash_flow_effect"]+rows[1]["cash_flow_effect"]
    reinvestment = math.fsum(r["cash_flow_effect"] for r in rows[2:])
    if not math.isclose(operating+reinvestment,gap,abs_tol=1e-8,rel_tol=1e-12):
        raise ValueError("Unexplained stable FCFF spread")
    return dict(fy=low["fy"],unit="JPY billion",low=low["fcff"],high=high["fcff"],difference=gap,
                after_tax_operating_effect=operating,net_reinvestment_effect=reinvestment,rows=rows,
                evidence=ledger,model_assumptions=value["policy"],
                endpoint_drivers={key:{section:value["cases"][key][section] for section in ("profit_bridge","reinvestment_bridge")}
                                  for key in ("low","high")})
