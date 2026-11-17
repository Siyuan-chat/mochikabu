# Important pseudocode

## Screenshot -> normalized holdings

```text
read screenshot visually
extract each row: contribution, incentive, purchase amount, shares, unit price
validate row sums against displayed totals
if screenshot is pre-split:
    normalized_shares = displayed_shares * split_ratio
    normalized_unit_price = row_unit_price / split_ratio
else:
    use displayed values

personal_cash_cost = total_employee_contribution / normalized_shares
accounting_cost = total_purchase_amount / normalized_shares
```

## Public DCF

```text
for year t in forecast_years:
    PV_FCF += FCF[t] / (1 + WACC)^t

TV = FCF[last] * (1 + g) / (WACC - g)
PV_TV = TV / (1 + WACC)^N
EV = PV_FCF + PV_TV
EquityValue = EV - NetDebt
FV_per_share = EquityValue / post_split_share_count
TargetCost = FV_per_share * (1 - margin_of_safety)
```

## Marginal employee-plan threshold

```text
effective_incentive = incentive_rate * (1 - incentive_tax_rate)
MarginalTargetMarketPrice = TargetCost * (1 + effective_incentive)
```

Below this market price, a new contribution has a personal cash cost at/below the target before dividends.

## Configured-horizon contribution decision

```text
for candidate_monthly in candidates:
    for scenario_avg_price in scenario_grid:
        shares = current_shares
        personal_cash = current_personal_cash

        for every month until target_date:
            buy monthly contribution * (1 + incentive) / scenario_price
            if month is in configured bonus_months:
                buy bonus contribution * (1 + incentive) / scenario_price
            if month is in configured dividend_reinvest_months:
                net_dividend = shares * dividend_per_period * (1 - dividend_tax)
                shares += net_dividend / scenario_price

        projected_personal_cost = personal_cash / shares
        success = shares >= target_min AND projected_personal_cost <= TargetCost
        soft_band = target_min <= shares <= target_max

choose candidate with most success scenarios
if tie: prefer more soft-band successes, then smaller contribution
apply configured max_step_change increase cap if supplied
```
