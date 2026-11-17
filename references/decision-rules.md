# Configurable contribution review

## Thresholds

- `FV`: source-backed central fair value per share.
- `TargetCost = FV * (1 - margin_of_safety)`.
- `r = incentive_rate * (1 - incentive_tax_rate)`.
- `MarginalTargetMarketPrice = TargetCost * (1 + r)`.

This simplified threshold assumes the configured incentive, no unmodeled fees and JPY amounts. Verify the actual incentive formula and tax treatment.

## Scenario selection

Use only candidate contributions permitted by the actual plan. For each configured average-price scenario, project shares and employee cash cost to `target_date`.

The script ranks candidates by scenarios meeting both the configured minimum shares and cost target, then by scenarios within the soft share band, then by lower contribution. An optional `max_step_change` caps increases relative to current contributions. If absent, the script applies no increase cap. The upper share target is a soft preference, not an employer rule.

A score is not sufficient for a final conclusion. Check affordability, employer-stock concentration, adjustment dates, public valuation uncertainty and unmodeled fees/restrictions. Zero successful scenarios means no tested candidate achieves both goals. Refresh public inputs at the plan's next permitted review, or when material public evidence changes.

## Position lifecycle policy

Add these optional fields to the existing flat plan config. The values below illustrate a fictional policy. Agree each threshold with the user.

```json
{
  "position": {"lifecycle_state":"employee","thesis_status":"intact","portfolio_concentration":0.12},
  "valuation_policy":{
    "accumulation_bands":{"extreme":0.70,"strong":0.80,"normal":0.95},
    "trim_bands":{"watch":1.20,"partial":1.50,"major":1.80},
    "max_concentration":0.20
  }
}
```

Each cut belongs to the band beginning at that value. Classify holdings using market price / base FV. Classify employee purchases using the after-tax incentive-adjusted price. An increase also requires the margin of safety and current peer support. Read the candidate score alongside the contribution state and verify affordability, employment-income exposure and the actual adjustment window. At the concentration ceiling pause new contributions and review the position. Trim states call for review against selling restrictions and the agreed exit policy.

With `former_employee`, use the full market price and skip plan purchases. An optional `position.transfer_destination` records the receiving account. A broken or unconfirmed thesis takes priority and calls for review. Use `company.valuation_metadata` in financials.json for reviewed `as_of`, `model_version`, `confidence` and optional evidence-backed `bear_fv` and `bull_fv`. Omitted scenarios stay null. WACC/g sensitivity endpoints are reported separately.

### Valuation residency

Pass an optional history file to analyze.py. Match the config company_id, JPY and split basis across all records. A valuation date is the first trading session when the assessed FV was available before the observations used. For an after-close release use the next eligible session.

```json
{"company_id":"example","currency":"JPY","thresholds":[0.7,0.8,0.9,1],
 "valuations":[{"date":"2026-04-01","base_fv":1000}],
 "closes":[{"date":"2026-04-02","price":780}],
 "purchases":[{"date":"2026-04-02","price":790,"shares":10,"personal_cash":7500}]}
```

Each observed close counts once. Gaps and weekends add zero observations. Purchases use execution prices and the latest FV available on their date. Include actual employee cash only in personal_cash. The acquisition ratio is weighted by acquired shares, including shares funded by incentives or dividends.
