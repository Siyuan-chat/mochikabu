---
name: mochikabu
description: Analyze Japanese employee stock ownership and employee shareholding plans (社員持株会 / 従業員持株会) for any company. Use when a user asks whether to increase, maintain, reduce, or pause contributions; for holdings screenshots; plan incentive and dividend-reinvestment modeling; public financial-report and latest-quote retrieval; DCF and peer-relative valuation; employer-stock concentration review; or share and cost targets established through conversation. Treat Japanese plan rules as plan-specific rather than assuming US ESOP/ESPP rules. All monetary inputs and outputs are in Japanese yen (JPY).
---

# mochikabu

Support company-specific Japanese employee stock ownership / employee shareholding plan (社員持株会・従業員持株会) decisions. Identify the company, market and actual plan rules from the user's inputs rather than assuming a particular employer or treating US ESOP/ESPP rules as equivalent.

## Inputs and boundaries

- Fix currency to Japanese yen (JPY); do not ask the user to select a currency. Convert non-JPY public financials or prices into JPY using a dated, sourced exchange rate before modeling. Confirm company name, ticker (if listed), holdings date, valuation date and target date.
- Obtain the actual contribution limits and increments, adjustment windows, contribution start date, bonus amount/months, incentive rate/tax treatment, dividend schedule/tax/reinvestment rules, fees, withdrawal and selling restrictions. Unknown rules stay `OPEN`; example values are synthetic.
- Use public disclosures for valuation and contribution conclusions. Non-public employer information must not become a trigger to buy, sell or increase contributions.
- Separate employee cash cost from accounting purchase cost. Normalize share counts and prices for corporate actions before comparison.
- Set the decision horizon to the next permitted change under that plan. Avoid treating a one-day move as sufficient evidence.

## Workflow

### 1. Establish settings through conversation

The agent owns configuration. Do not ask the user to edit JSON or choose technical field names. Reuse facts already stated in the conversation and read supplied screenshots or plan documents before asking questions.

Ask a small group of plain-language questions at a time, prioritizing what is needed for the next calculation:
- First identify the company, current monthly/bonus contributions, current holdings and the user's goal or intended target date.
- Then resolve missing plan rules: incentive, contribution limits/increments, adjustment dates, bonus schedule and dividend handling. Extract these from supplied documents when possible; ask the user only about unresolved material facts.
- Discuss affordable contribution range and employer-stock concentration when needed for the recommendation. Establish share targets, safety margin and optional increase cap from the user's preferences. If the user has no specific target, propose a justified assumption and make it visible before using it.

The agent discovers ticker, public prices, financials, dividends and corporate actions from public sources. The user should not have to collect public valuation inputs. Select valuation assumptions and price scenarios with reasons; show assumptions separately from verified facts. Do not copy synthetic example settings into a real analysis.

After the conversation, summarize the company, goals, plan rules and remaining unknowns in plain language. Generate `config.json` and `holdings_snapshot.json` in the working directory from the agreed facts and disclosed assumptions, with `currency` set to `JPY`. Save sources/dates and explain changes on later reviews. Continue directly when the required facts are established; request clarification when an unresolved fact changes the calculation. Keep unknown rules `OPEN` in evidence notes and omit dependent conclusions until resolved.

### 2. Normalize holdings

Inspect attached screenshots visually and transcribe visible values using [examples/holdings_snapshot.example.json](examples/holdings_snapshot.example.json). Check contribution, incentive and share row sums; explain residual cash. Record the split basis and ratio. If dividends, fees or withdrawals affect reconciliation, record them separately rather than inventing contributions.

### 3. Fetch financial reports and market evidence

Read [references/public-research.md](references/public-research.md) for script inputs and evidence requirements, and [references/sources.md](references/sources.md) for source selection. Discover current official IR reports for the company and suitable peers. The agent selects peers by business mix, geography, growth, profitability and leverage; explain inclusions/exclusions. Use at least three independent comparable peers for peer-supported purchase signals when available.

Generate `research_request.json`, then call:

```bash
python scripts/fetch_public.py --request research_request.json --output-dir research_raw
```

Inspect downloaded reports and extracted PDF pages/XBRL contexts. Normalize consolidated financials into JPY with source/page/period references; distinguish actuals, guidance and agent assumptions. Generate `financials.json` rather than asking the user for public data or JSON. Fetch both the target and peer prices. Keep quote time, retrieval time and delay status; do not present latest/delayed quotes as verified realtime. The helper is a best-effort free public feed. A verified realtime feed can be used if the user already has authorized access.

For unlisted/unsupported companies, preserve the missing market evidence and explain what can be valued without a live price. Do not fabricate a ticker, quote or peer data.

### 4. Calculate fair value and peer premiums

Call:

```bash
python scripts/value_public.py --input financials.json --market-manifest research_raw/manifest.json --output valuation.json
```

Report own DCF central value and sensitivity, market premium to own fair value, peer-implied PE/PB/EV-EBITDA values where suitable, and the target's price-to-own-fair-value ratio relative to comparable peers' ratios. Match accounting, financial periods and corporate-action basis. Keep intrinsic and relative estimates separate; compare disagreements rather than silently blending them. For banks or other companies where FCFF is inappropriate, use an appropriate agent-calculated valuation method and disclose that the current FCFF helper does not cover it; keep unsupported scripted signals `OPEN`.

Forecast FCF, WACC and terminal growth are explicit modeling assumptions grounded in public evidence. Missing/stale data or insufficient peers must remain visible and cannot support a firm buy conclusion. The indicative script action is one input to the agent's final judgment.

### 5. Generate plan configuration

Adapt [examples/config.example.json](examples/config.example.json). Set `company_id` to match the target in `financials.json`; use the computed `valuation.json` in the normal workflow. Standalone `fair_value.mode = manual` or `dcf` remains available for explicit offline scenarios, with evidence limitations stated. DCF fields `fcf_billion` and `net_debt_billion` use billions of JPY; share count uses millions. Run the sensitivity table and distinguish public inputs from modeling assumptions.

All contribution, price and cash fields use neutral names and JPY. Set bonus/dividend months, incentives, targets, review months and increase cap for this plan. `review_months` is descriptive metadata: verify actual deadlines manually. `contribution_start_date` controls the projection start; otherwise the model starts next month. `max_step_change` is an optional user-selected increase cap, not an employer limit. Candidate contributions must already satisfy the actual plan rules.

### 6. Run contribution scenarios

From the skill root:

```bash
python scripts/analyze.py --config config.json --holdings holdings_snapshot.json --research valuation.json --output output.json
```

The public-research workflow uses the quote and fair value from `valuation.json`, and checks company identity, quote age and policy consistency. For a standalone price refresh without peer research, `--fetch-price` retrieves a timestamped latest regular-market quote; disclose that peer-based judgment is unavailable. The example ticker is fictional.

The model supports monthly cash purchases, optional bonus purchases and approximate equal dividend installments. For other purchase frequencies, unequal installments, caps, fees, lockups or company-specific formulas, disclose what is not modeled and adapt the calculation before giving a conclusion. The model does not enforce adjustment windows or execute transactions.

### 7. Judge buying and the contribution choice

Read [references/decision-rules.md](references/decision-rules.md). Report normalized holdings, both cost measures, public fair value and sensitivity, target cost and incentive-adjusted price threshold, candidate projections to the configured target date, bonus/dividend effects and configured target coverage. Compare employer-stock concentration with the user's assets and income exposure when data is available.

Explain whether buying/increasing, maintaining, reducing or temporarily pausing contributions is supported. Show the incentive-adjusted purchase cost, safety margin and peer premium tests behind that judgment. Never infer a buy merely from a peer discount. Treat script contribution selection as a scenario score. Check affordability, actual plan constraints, concentration, valuation uncertainty and the next adjustment date before stating a contribution conclusion. If no candidate meets the goals, report the gap rather than presenting the score winner as achieving them.

Use the user's requested language and display money in JPY (円). Show formulas and assumptions, and end with what needs refreshing at the next permitted review.
