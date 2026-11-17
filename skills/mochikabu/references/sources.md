# Company-specific public sources

Identify the selected company and exchange first. Record each material input's value, unit, currency, effective date, publication date, URL and status (`PUBLIC`, `ASSUMPTION`, `OPEN`).

- Official company IR: latest financial statements, cash flows, net debt, share count, dividend policy, guidance and published plans.
- Company and relevant exchange/regulator disclosures: stock splits, other corporate actions and effective dates.
- Public market data: correct listing/ticker, currency and price date. Verify split adjustment before comparing history.
- User-provided plan documents: contribution rules, incentives, adjustment deadlines, bonuses, fees and restrictions. These describe the plan; they are not public valuation evidence.

The helper queries Yahoo's chart endpoint using the configured ticker. If unsupported or unavailable, supply a dated public price manually. For an unlisted company, identify an appropriate public valuation basis; keep unavailable inputs `OPEN`.

Use the executable collection and valuation schema in [public-research.md](public-research.md). Fetch the target and selected peers on the same review, retain quote timestamps and delay status, and verify extracted report numbers against the originals.
