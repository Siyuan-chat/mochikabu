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
