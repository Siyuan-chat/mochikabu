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

## Valuation and contribution decisions

After source collection, record original filing cells, dates, units and citations using references/filing-recognition.md. Choose a registered fixed model whose documented requirements fit those disclosures. Run scripts/review_contribution.py according to references/review-input.md. The script sets all model assumptions and produces the valuation, peer arithmetic and action. Missing required observations produce an incomplete review. In Chinese, present the runner's answer_zh, with the evidence links and company-specific context. For other languages translate that result preserving every number and condition.
