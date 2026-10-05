# Public research script contract

The agent discovers current official URLs, chooses justified peers and normalizes extracted financials. Scripts download, preserve evidence and calculate; users do not maintain these files. A PDF table or XBRL fact is not automatically a correct valuation input: verify consolidated scope, period, units, corporate actions and extraordinary items.

## 1. Download financial reports and latest quotes

Generate `research_request.json`:

```json
{
  "company": {
    "id": "target",
    "name": "Company identified in conversation",
    "ticker": "Actual market ticker",
    "reports": [{"url": "Official HTTPS report URL", "format": "pdf", "publication_date": "YYYY-MM-DD", "period": "Fiscal year or quarter"}]
  },
  "peers": []
}
```

Populate peers with the same fields. Download latest quarterly/yearly results and enough cash-flow history to assess normalized cash generation; do not annualize a single quarter without considering seasonality. Format is `pdf`, `xbrl`, `zip` (XBRL package) or `html`.

Run `scripts/fetch_public.py --request research_request.json --output-dir research_raw`. It saves original reports, page-numbered PDF text or raw XBRL facts/contexts/units, plus `manifest.json`. PDF extraction uses `pypdf` if available; otherwise the original remains available for the agent to read/render. Inline XBRL values retain scale/sign attributes and must be interpreted by the agent.

Market quotes use the Yahoo chart endpoint with price time, fetch time, currency, source URL and `delay_status: UNKNOWN`. This public endpoint is best effort and not a guaranteed realtime feed. Historical/daily last close must not be mislabeled realtime. If the user already has an authorized realtime feed, use it and retain its documented delay and timestamp in a compatible market manifest; no paid signup is implied. J-Quants historical/minute data is not automatically realtime: [JPX data description](https://www.jpx.co.jp/markets/other-data-services/j-quants-api/index.html). EDINET API access needs the user's configured access: [official API documentation](https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/WZEK0110.html). Direct official IR downloads require no new API subscription.

## 2. Normalize financial evidence and assumptions

Generate `financials.json` with `currency: JPY`, `company`, `peers`, `policy`, and optional `max_quote_age_hours` (default 72; account for holidays and explain changes). Each company uses:

- `id`: matches manifest; unique across target and peers.
- `financials`: `eps` and `bps` in JPY/share; `ebitda`, `net_debt`, `base_fcf` in JPY; `shares` in actual shares. Negative net debt means net cash. Normalize splits and financial periods.
- `evidence`: per financial field `{source_url, locator, period, status: PUBLIC}`. Locator identifies downloaded file/page/table or XBRL tag/context/unit. The agent checks figures against the original; labels alone do not establish validity.
- `metric_basis`: keys `pe`, `pb`, `ev_ebitda` describe comparable period/accounting scope, e.g. TTM adjusted consolidated EPS. Matching labels require actual matching calculations; exclude inappropriate ratios (loss-making PE, bank EV/EBITDA, incomparable leverage/accounting).
- `dcf`: `fcf_billion` forecast array, `wacc`, `terminal_growth`, `net_debt_billion`, `shares_million_post_split`. Debt and shares must reconcile with normalized financials.
- `dcf_assumption_note`: public historical starting point and reasons for forecast growth, margins, reinvestment, WACC and terminal growth. Forecasts are modeled assumptions, even when informed by company guidance. `base_fcf` evidence is mandatory.
- `dcf_comparison_basis`: common methodology/horizon for comparing price-to-own-DCF ratios. Allow company-specific risk assumptions when justified and disclose them.
- For peers, `selection_reason`: industry, revenue mix, geography, profitability, growth and leverage comparability. Use at least three independent suitable companies when available. If not, show the gap and keep the peer-based buy signal `OPEN`.

Policy fields are `margin_of_safety`, `incentive_rate`, `incentive_tax_rate`, `peer_premium_tolerance`; establish them through dialogue and disclosed assumptions. Do not use sample policy values as actual preferences. For offline illustrative data, set `example_only: true`; results are explicitly `SYNTHETIC`.

Run `scripts/value_public.py --input financials.json --market-manifest research_raw/manifest.json --output valuation.json`.

## 3. Compare fair values and judge contributions

Keep intrinsic DCF and peer-implied values separate; do not silently average inconsistent methods.

- Own fair-value premium = `market_price / own_DCF_fair_value - 1`.
- Relative own-fair-value premium = `(target_price / target_DCF) / median(peer_price / peer_DCF) - 1`.
- Peer-implied PE/PB fair value = `median(peer_multiple) * target_per_share_fundamental`.
- Peer-implied EV/EBITDA fair value = `(median(peer_EV_EBITDA) * target_EBITDA - target_net_debt) / target_shares`.
- Peer-implied price premium = `market_price / peer_implied_fair_value - 1`.

Report contributing/excluded peers and reasons, sensitivity range and disagreements. Peer prices can all be expensive; peer-relative discounts alone do not establish intrinsic undervaluation.

The script returns an indicative `consider_increase` only when incentive-adjusted personal cost meets the chosen safety margin and all eligible peer premium checks are within the chosen tolerance. `avoid_increase` means the modeled cost test fails; `review_peer_premium` means peer evidence conflicts; `resolve_evidence` means no supported judgment is available. These are valuation signals, not executed trades or final personalized actions.

Then set `company_id` in `config.json` to match the target and run `scripts/analyze.py --config config.json --holdings holdings_snapshot.json --research valuation.json --output output.json`. This uses the computed DCF and quote rather than a manually copied fair value. The agent combines valuation signals with contribution scenarios, budget, concentration, lockups and permitted adjustment windows to conclude increase/maintain/reduce/temporarily pause, as applicable. Explain when existing mandatory contributions cannot be changed immediately.

`partial` collection or valuation results require the agent to resolve missing evidence before a firm conclusion. Scripts use exit code 2 for partial results and preserve usable artifacts; do not overwrite them with invented inputs.
