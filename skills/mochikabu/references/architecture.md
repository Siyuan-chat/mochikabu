# Architecture

```text
Screenshot / manual holdings     Public IR / corporate actions     Timestamped market quotes
          |                              |                              |
          v                              v                              v
  Holdings adapter -------------- Evidence normalizer -------- Market adapter
          |                              |                              |
          +------------------------------+------------------------------+
                                         |
                                         v
                                Normalized research state
                                         |
                    +--------------------+-------------------+
                    |                    |                   |
                    v                    v                   v
                DCF / peer engine         Holdings engine      Price stats
                    |                    |                   |
                    +--------------------+-------------------+
                                         |
                                         v
                                Valuation signal / contribution engine
                                         |
                        +----------------+----------------+
                        |                                 |
                        v                                 v
               Contribution review            Audit/evidence output
```

## Modules

### Holdings adapter
Normalizes screenshots/manual inputs into post-split shares, employee cash contributed, company incentive, purchase amount, and residual cash.

### Evidence normalizer
Stores the date, value, unit, source URL, and status (`PUBLIC`, `OPEN`, `NON_ACTIONABLE_INTERNAL`) for each material input.

### DCF / peer engine
Computes PV of forecast cash flows, terminal value, EV-to-equity bridge, per-share value, and WACC/g sensitivity.

### Price stats
Computes current price, moving averages, realized volatility, drawdown, and the configured historical price context. These are context, not standalone buy signals.

### Holdings engine
Computes personal cash cost/share, accounting purchase cost/share, incentive benefit, dividend-reinvestment shares, and projected final holdings.

### Scenario/policy engine
Evaluates candidate contribution amounts across constant-average-price scenarios. The base model is intentionally transparent and robust; it does not pretend to forecast the exact price path.

### Audit/evidence output
Emits machine-readable JSON so a later notebook or quantitative model can reuse the same state.

Executable flow: `fetch_public.py` saves reports, extracted content and quote manifest; the agent normalizes public facts and assumptions; `value_public.py` computes intrinsic and peer-relative values/signals; `analyze.py --research` projects contribution candidates; the agent concludes after checking user budget and plan constraints.
