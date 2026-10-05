# Mochikabu — AI Agent Skill for Japanese Employee Stock Ownership Plans

**An open-source AI agent skill for evaluating employee stock ownership / employee shareholding plans in Japan using public financial data, DCF valuation, peer comparison, plan incentives, dividend reinvestment, and employer-stock concentration risk.**

[日本語](README.md) · [Usage guide (Japanese)](docs/usage.ja.md) · [Valuation guide (Japanese)](docs/valuation.ja.md) · [Script/data contract](references/public-research.md)

> **Not just a contribution calculator.** Mochikabu evaluates the company first, then evaluates the employee stock plan.

## What Mochikabu does

Mochikabu is designed for Japanese employee stock ownership and employee shareholding plans such as 社員持株会 and 従業員持株会. Instead of only projecting contributions and incentives, it connects company valuation with the employee plan decision.

| Area | Mochikabu |
| --- | --- |
| Holdings and cost-basis normalization | ✓ |
| Incentive, bonus contribution, and dividend-reinvestment modeling | ✓ |
| Timestamped latest-price retrieval | ✓ |
| DCF fair-value estimation | ✓ |
| PER / PBR / EV/EBITDA peer comparison | ✓ |
| Fair-value sensitivity analysis | ✓ |
| Employer-stock concentration review | ✓ |
| Increase / maintain / reduce / pause contribution assessment | ✓ |
| Automated trade execution | — |

### Example questions

- “My employee stock plan gives a 10% incentive. Should I increase my monthly contribution?”
- “Is my employer stock overvalued or undervalued based on DCF and peers?”
- “How do ¥30,000 and ¥50,000 monthly contributions change my projected shares and employee cash cost?”
- “Am I concentrating too much of my income and assets in my employer?”
- “Can an employee stock plan still be attractive when the market price is above estimated fair value?”
- “Should I increase, maintain, or reduce contributions before the next plan adjustment window?”

## Install / Quick start

The self-contained Agent Skills package lives at `skills/mochikabu/`. It can be installed into Codex, Claude Code, and other compatible agents using the Agent Skills CLI or GitHub CLI.

### Agent Skills CLI

```bash
npx skills add Siyuan-chat/mochikabu --skill mochikabu
```

After registry indexing, users can discover it by intent:

```bash
npx skills find "employee stock ownership"
npx skills find "employee shareholding Japan"
```

### GitHub CLI

Codex:

```bash
gh skill install Siyuan-chat/mochikabu mochikabu --agent codex --scope user
```

Claude Code:

```bash
gh skill install Siyuan-chat/mochikabu mochikabu --agent claude-code --scope user
```

After publication, GitHub skill search can also discover the package:

```bash
gh skill search "employee stock ownership"
gh skill search "employee shareholding"
```

### DSH / shared Agent Skills directory

For DSH or another host that reads `~/.agents/skills/`, copy only the packaged skill directory:

```bash
git clone --depth 1 https://github.com/Siyuan-chat/mochikabu.git /tmp/mochikabu
mkdir -p ~/.agents/skills
cp -R /tmp/mochikabu/skills/mochikabu ~/.agents/skills/mochikabu
```

For a DSH-only installation, place the same directory at `~/.dsh/skills/mochikabu`.

Use Python 3.10 or newer. Valuation and planning use the standard library. PDF text extraction optionally uses `pypdf`.

```bash
python -m pip install pypdf
```

Then invoke `$mochikabu` and describe your company, current contribution, holdings, and goal.

For example:

> Use $mochikabu to review my employee stock ownership plan. My employer is [company], my current monthly contribution is ¥[amount], and I want you to first ask for any missing information.

Users normally do not need to edit JSON. The agent establishes the company, holdings, plan rules, budget, and goals through conversation, gathers public evidence, creates the configuration, and runs the analysis.

The repository root remains the development source; `skills/mochikabu/` is the portable distribution unit for agent installers.

## Workflow

```text
User conversation / plan documents
    → identify company, holdings, plan rules, and goals
    → fetch public financial reports and market evidence
    → normalize financial facts and modeling assumptions
    → calculate DCF, peer comparisons, and valuation premiums
    → simulate candidate contribution levels
    → assess contribution choice with budget, concentration, and plan constraints
```

## Core capabilities

- Read employee-plan screenshots and normalize shares, employee cash cost, accounting purchase cost, and stock splits.
- Retrieve public reports for the company and justified peers, including PDF and XBRL sources where available.
- Retrieve timestamped latest market prices with source and delay status.
- Estimate DCF fair value and sensitivity.
- Compare PER, PBR, EV/EBITDA, and market-price-to-fair-value multiples across peers.
- Model employee incentives, bonus contributions, dividend reinvestment, projected shares, and employee cash cost.
- Review affordability, employer-stock concentration, contribution windows, and other plan constraints before giving a contribution conclusion.

## Repository structure

| File | Role |
| --- | --- |
| `SKILL.md` | Agent conversation, research, and decision workflow |
| `scripts/fetch_public.py` | Public-report and latest-price retrieval |
| `scripts/value_public.py` | DCF, peer comparison, and valuation signals |
| `scripts/analyze.py` | Contribution scenario simulation |
| `references/` | Financial-data contracts, formulas, and decision rules |
| `examples/` | Fictional company and account examples |
| `tests/` | Offline verification without external network access |

## Agent-generated pipeline

```bash
python scripts/fetch_public.py --request research_request.json --output-dir research_raw
python scripts/value_public.py --input financials.json --market-manifest research_raw/manifest.json --output valuation.json
python scripts/analyze.py --config config.json --holdings holdings_snapshot.json --research valuation.json --output output.json
```

The agent discovers report URLs and peers, verifies extracted facts against original pages or XBRL contexts, and generates the input files. See [public-research.md](references/public-research.md) for schemas and formulas.

Offline verification:

```bash
python -m unittest discover -s tests -v
python scripts/analyze.py --config examples/config.example.json --holdings examples/holdings_snapshot.example.json --output output.json
```

Examples are fictional. Financial cash flows and debt in DCF use billions of JPY; shares use millions. Other monetary fields use JPY, with per-share fields in JPY/share. Convert foreign-currency sources with a dated, sourced FX rate before modeling.

## Data and decision boundaries

Quotes include market time, retrieval time, and delay status. The free public endpoint does not guarantee realtime delivery. Use an authorized verified feed if actual realtime data is required.

DCF and peer-implied values are separate estimates. Missing or stale evidence and insufficient peers remain `OPEN` or `partial`; illustrative inputs are `SYNTHETIC`. The agent reviews budget, employer-stock concentration, fees, lockups, and contribution windows before a final conclusion.

FCFF is not suitable for every company; specialized bank valuation is outside the current DCF helper. No trade execution is provided. Non-public employer information must not be used as a trigger to buy, sell, or increase contributions.

Personal holdings, generated settings, downloaded reports, and run logs are ignored by Git. Respect third-party data usage terms when distributing retrieved materials.

## FAQ

### Is Mochikabu an ESOP or ESPP calculator?

Mochikabu targets Japanese employee stock ownership / employee shareholding arrangements, especially 社員持株会 and 従業員持株会. It does not assume that US ESOP or ESPP rules are equivalent. The actual plan rules are established from the user's plan documents and inputs.

### Does a high employee incentive automatically mean “increase contributions”?

No. An incentive lowers the employee's effective acquisition cost, but valuation, affordability, employer-stock concentration, lockups, contribution windows, and uncertainty still matter.

### Can Mochikabu tell whether employer stock is overvalued?

It can estimate DCF fair value, run sensitivity analysis, and compare peer valuation multiples using public information. These are estimates rather than guaranteed intrinsic values, and conflicting signals are shown rather than hidden.

### Is Mochikabu limited to Japanese companies?

Its primary use case is Japanese employee stock plans and all model outputs are normalized to JPY. Foreign-company public financials or prices can be modeled after conversion to JPY with a dated, sourced exchange rate.

### Does Mochikabu execute trades?

No. It supports research, valuation, scenario analysis, and contribution decisions. It does not place orders or execute trades.

## License

[MIT](LICENSE).
