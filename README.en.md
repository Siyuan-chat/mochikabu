# mochikabu

A conversation-led AI agent skill for employee stock ownership plans. All monetary inputs and outputs use **Japanese yen (JPY)**.

[日本語](README.md) · [Usage guide (Japanese)](docs/usage.ja.md) · [Valuation guide (Japanese)](docs/valuation.ja.md) · [Script/data contract](references/public-research.md)

The agent discusses the company, holdings, plan rules and goals with the user, gathers public evidence, creates the configuration and runs the analysis. Users do not need to edit JSON.

## Workflow

1. Establish holdings, plan rules, budget and goals through dialogue.
2. Fetch official financial reports and timestamped quotes for the company and justified peers.
3. Normalize financial facts and distinguish them from valuation assumptions.
4. Calculate DCF fair value, sensitivity and peer valuation premiums.
5. Model contribution candidates, incentives, bonus purchases and dividend reinvestment.
6. Assess the contribution choice against valuation, affordability, concentration and plan constraints.

## Installation

Use Python 3.10 or newer. Valuation, planning and offline tests use the standard library. PDF text extraction optionally uses `pypdf`; without it, downloaded originals remain available for agent inspection.

```bash
python -m pip install pypdf
git clone https://github.com/Siyuan-chat/mochikabu.git ~/.codex/skills/mochikabu
```

The repository root is the skill directory. Place it in the skill location supported by your agent, then invoke `$mochikabu` and describe your company and current contribution. See [SKILL.md](SKILL.md) for the agent workflow.

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

## Practical boundaries

Quotes include market time, retrieval time and delay status. The free public endpoint does not guarantee realtime delivery. Use an authorized verified feed if actual realtime data is needed.

DCF and peer-implied values are separate estimates. Missing/stale evidence and insufficient peers stay `OPEN` or `partial`; illustrative inputs are `SYNTHETIC`. The agent reviews budget, employer-stock concentration, fees, lockups and contribution windows before a final conclusion. FCFF is not suitable for every company; specialized bank valuation is outside the current DCF helper. No trade execution is provided.

Personal holdings, generated settings, downloaded reports and run logs are ignored by Git. Respect third-party data usage terms when distributing retrieved materials.

## License

[MIT](LICENSE).
