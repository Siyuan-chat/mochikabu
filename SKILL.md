---
name: mochikabu
description: Review Japanese employee shareholding plans (持株会), including a simple question about maintaining or reducing a monthly contribution. Use current disclosures, an operating DCF and comparable companies, then explain the practical choice in the user's language. Also supports holdings reconciliation and incentive, bonus and dividend projections in JPY.
license: MIT
---

# mochikabu

## Discovery intents

Use this skill when the user's request is about Japanese employee stock plans, including queries such as:

- 「持株会」「社員持株会」「従業員持株会」
- 「持株会の奨励金」「持株会の拠出額」「持株会を増額・減額・維持すべきか」
- 「自社株の集中リスク」「勤務先株への資産集中」
- 「持株会の適正株価」「自社株は割高か割安か」「DCF で自社株を評価」
- 「持株会の配当再投資」「賞与拠出」「目標株数」
- "Japanese employee stock ownership plan", "employee shareholding Japan", "employee stock contribution planning"

Support company-specific Japanese employee stock ownership / employee shareholding plan (社員持株会・従業員持株会) decisions. Identify the company, market and actual plan rules from the user's inputs rather than assuming a particular employer or treating US ESOP/ESPP rules as equivalent.

The current assistant reads the issuer filings and calls the installed fixed-model scripts directly. Keep the dated source observations, model version and case inputs with the result so the calculation can be reproduced.

## Real contribution reviews

1. Identify the issuer, last completed trading session and relevant filings. Ask once in ordinary language for missing monthly/bonus amount, incentive, employer-stock share, affordability and whether the user regularly sells to diversify. Continue public research while waiting. Read the supplied plan and transactions before asking.
2. Select a supported **versioned script model** for the issuer's business structure. The analyst may recognize filings and map reported facts, periods, units and sources. All valuation policy, normalization, reinvestment, project timing, low/high paths, discounting, date bridge, peer P/E arithmetic, incentive economics and contribution decisions belong to scripts. Never ask a model to select margins, WACC, growth, scenario endpoints, a middle estimate or the action. If no supported model fits, report that boundary.
3. Read [filing field definitions](references/filing-recognition.md), then extract the issuer's original statements and market data into fresh case-local files. For a consolidated industrial expansion with a dated investment budget and commissioning date, use [the industrial project contract](references/industrial-project.md). Use [the product-pool model](references/product-project.md) only when the issuer discloses product earnings milestones, comparable segment pools and the other required evidence. Select by what the issuer discloses. Keep the evidence, actual/forecast period, source units and table headers with each observation. Historical fixtures are for regression testing only.
4. Follow [the runner contract](references/review-input.md). Write a small case request with the selected model, references to financial and market facts, and the user's personal facts. Run `python scripts/review_contribution.py case.json --output public.json`, then with `--final --output decision.json` once personal facts are available. Resolve scripts and packaged data relative to the installed skill; write outputs to the case directory. A new review requires a successful `review_ready` response from this runner. If inputs fail validation, repair the financial transcription or identify the missing disclosure. Never substitute a manual DCF, an improvised script, a prior decision or a manual contribution score.
5. In Chinese, present the final runner’s answer_zh. For another language translate its figures, action and conditions faithfully. Explain the evidence in the user's language. Give the monthly amount, annual change in personal cash and reward, the same-day stock price and effective purchase cost relative to the script's interval. Link the output with its segment/group reconciliation, annual FCFF through ramp-up, reinvestment, date bridge and peer comparisons. Distinguish observations from fixed modelling conventions. For same-date revisions reconcile the changed facts and model version. For reproducibility compare corresponding interval endpoints and actions, never average the endpoints into a fair price.

In every live answer show the stable-year breakdown from stable_cash_flow_review: low, high and signed contribution for every row, with units. Explain major disclosed drivers, peer proxies (including observed rates and their limitations) and model assumptions separately, citing their recorded sources. State valuation_assessment_zh and concentration_assessment_zh independently; retain the script’s conditional decision for regular diversification.

For holdings reconciliation, projections and explicitly requested historical scenario replay, see [workflow.md](workflow.md). Keep private plan details in the current case.

