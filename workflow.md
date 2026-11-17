## Inputs and boundaries

- Fix currency to Japanese yen (JPY); do not ask the user to select a currency. Convert non-JPY public financials or prices into JPY using a dated, sourced exchange rate before modeling. Confirm company name, ticker (if listed), holdings date, valuation date and target date.
- Obtain the actual contribution limits and increments, adjustment windows, contribution start date, bonus amount/months, incentive rate/tax treatment, dividend schedule/tax/reinvestment rules, fees, withdrawal and selling restrictions. Unknown rules stay `OPEN`; example values are synthetic.
- Use public disclosures for valuation and contribution conclusions. Non-public employer information must not become a trigger to buy, sell or increase contributions.
- Separate employee cash cost from accounting purchase cost. Normalize share counts and prices for corporate actions before comparison.
- Set the decision horizon to the next permitted change under that plan. Avoid treating a one-day move as sufficient evidence.

## Workflow

### Real monthly contribution decisions

Use the installed SKILL.md and references/review-input.md. The reviewed numerical result and action come from scripts/review_contribution.py. The remaining sections describe how to read holdings, collect disclosures, and run additional projections or historical scenarios. Their legacy/manual valuation options are for explicitly requested exploration only.

### 1. Establish settings through conversation

The agent owns configuration. Do not ask the user to edit JSON or choose technical field names. Reuse facts already stated in the conversation and read supplied screenshots or plan documents before asking questions.

Ask a small group of plain-language questions at a time, prioritizing what is needed for the next calculation:
- First identify the company, current monthly/bonus contributions, current holdings and the user's goal or intended target date.
- Then resolve missing plan rules: incentive, contribution limits/increments, adjustment dates, bonus schedule and dividend handling. Extract these from supplied documents when possible; ask the user only about unresolved material facts.
- Discuss affordable contribution range and employer-stock concentration when needed for the recommendation. Establish share targets, safety margin and optional increase cap from the user's preferences. If the user has no specific target, propose a justified assumption and make it visible before using it.

The agent discovers ticker, public prices, financials, dividends and corporate actions from public sources. The user should not have to collect public valuation inputs. Select the fixed model and map disclosed facts. The versioned script owns all numeric conventions. Do not copy synthetic example settings into a real analysis.

After the conversation, summarize the company, goals, plan rules and remaining unknowns in plain language. Generate `config.json` and `holdings_snapshot.json` in the working directory from the agreed facts and disclosed assumptions, with `currency` set to `JPY`. Save sources/dates and explain changes on later reviews. Continue directly when the required facts are established; request clarification when an unresolved fact changes the calculation. Keep unknown rules `OPEN` in evidence notes and omit dependent conclusions until resolved.

### 2. Normalize holdings

Inspect attached screenshots visually and transcribe visible values using [examples/holdings_snapshot.example.json](examples/holdings_snapshot.example.json). Check contribution, incentive and share row sums; explain residual cash. Record the split basis and ratio. If dividends, fees or withdrawals affect reconciliation, record them separately rather than inventing contributions.

### 3. Fetch financial reports and market evidence

Read [references/public-research.md](references/public-research.md) for script inputs and evidence requirements, and [references/sources.md](references/sources.md) for source selection. Discover current official IR reports for the company and suitable peers. The agent selects peers by business mix, geography, growth, profitability and leverage; explain inclusions/exclusions. Use at least three independent comparable peers for peer-supported purchase signals when available.

Generate `research_request.json`, then call:

```bash
python scripts/fetch_public.py --request research_request.json --output-dir research_raw
```

Record the original consolidated rows, periods, units and forecast labels in the selected model’s filing schema. For live reviews the fixed runner calculates every valuation assumption and result.

For unlisted/unsupported companies, preserve the missing market evidence and explain what can be valued without a live price. Do not fabricate a ticker, quote or peer data.

### 4. Run the selected model

Use the contribution runner described in SKILL.md for real decisions. If the script cannot calculate a required value, report its specific missing input. For an explicitly requested replay of a legacy scenario only, scripts/value_public.py can read the historical financials.json and manifest.

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

### 7. Interpret the amount decision

Report the scripted action, conditions and differences in annual cash and rewards from decision.json. Use the holdings projection to explain cash and shares over time.

### 8. Review the position across employment changes

For a position review, establish the lifecycle state, investment thesis, concentration and valuation bands with the user. Add the fields in [Position lifecycle policy](references/decision-rules.md#position-lifecycle-policy) to the plan config. Run the same analyze command and read both states in `decision.position_policy`. For former employees, skip plan setup and contribution targets. Report the holding decision with the transferred shares on their current split basis.

Save the reviewed public valuation as `valuation_snapshot.json`. Reassess FV after results, guidance, major investment, acquisitions, financing or capital-allocation changes, and at the scheduled full review. Between reviews pass the saved snapshot as `--research` and the current fetch manifest as `--market-manifest`. This updates the price comparison while preserving the FV date. Recompute peer comparisons before supporting a contribution increase.

For historical purchases supply `--history history.json` as described in the decision rules. Report observed trading days, acquired shares and personal cash by valuation band.
