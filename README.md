# Mochikabu — 社員持株会・従業員持株会のための AI Agent Skill

**公開情報から会社を評価し、奨励金・配当再投資・自社株集中リスクまで含めて、持株会の拠出額を検討するオープンソース AI エージェントスキル。**

Mochikabu is an open-source AI agent skill for Japanese employee stock ownership / employee shareholding plans（社員持株会・従業員持株会）. It combines public financial data, DCF valuation, peer comparison, employee incentives, dividend reinvestment, and contribution planning.

[English](README.en.md) · [使い方](docs/usage.ja.md) · [評価方法](docs/valuation.ja.md) · [スクリプト仕様 (English)](references/public-research.md)

> **Not just a contribution calculator.** Mochikabu evaluates the company first, then evaluates the employee stock plan.

## Mochikabu でできること

一般的な持株会シミュレーションが奨励金や積立結果の計算を中心とするのに対し、Mochikabu は「その会社の株を、現在の評価水準で、勤務先への資産集中も考慮しながら、どの程度買うか」という判断まで一つのワークフローで扱います。

| 項目 | Mochikabu |
| --- | --- |
| 持株会の保有株数・取得費用の整理 | ✓ |
| 奨励金・賞与拠出・配当再投資の試算 | ✓ |
| 最新株価と出典・時刻の確認 | ✓ |
| DCF によるフェアバリュー推定 | ✓ |
| PER / PBR / EV/EBITDA と同業比較 | ✓ |
| 株価とフェアバリューの感応度分析 | ✓ |
| 勤務先への資産集中リスクの確認 | ✓ |
| 増額・維持・減額・一時停止の検討 | ✓ |
| 自動売買・注文執行 | — |

### こんな質問に使えます

- 「持株会の奨励金が 10% なら、月額拠出を増やすべき？」
- 「自社株は DCF や同業比較で割高・割安？」
- 「月 3 万円と 5 万円では、目標時点の保有株数と自己負担取得費用はどう変わる？」
- 「給与も資産も勤務先に集中しすぎていない？」
- 「株価がフェアバリューを上回っていても、奨励金を考えると買付は合理的？」
- 「次の持株会変更時期まで、増額・維持・減額のどれが妥当？」

## Install / Quick start

Mochikabu は Agent Skills 互換の自己完結パッケージを `skills/mochikabu/` に収録しています。Codex、Claude Code など複数の Agent では、Agent Skills CLI または GitHub CLI からインストールできます。

### Agent Skills CLI（推奨）

```bash
npx skills add Siyuan-chat/mochikabu --skill mochikabu
```

公開レジストリに反映された後は、例えば次のように検索できます。

```bash
npx skills find "employee stock ownership"
npx skills find "持株会"
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

公開後は GitHub の skill search からも検索できます。

```bash
gh skill search "employee stock ownership"
gh skill search "持株会"
```

### DSH / 共通 skill directory

DSH など `~/.agents/skills/` を読む Agent では、配布パッケージだけを配置できます。

```bash
git clone --depth 1 https://github.com/Siyuan-chat/mochikabu.git /tmp/mochikabu
mkdir -p ~/.agents/skills
cp -R /tmp/mochikabu/skills/mochikabu ~/.agents/skills/mochikabu
```

DSH 専用にする場合は同じディレクトリを `~/.dsh/skills/mochikabu` に配置できます。

Python 3.10 以降を使用します。評価・試算は標準ライブラリで動作し、PDF のテキスト抽出には `pypdf` を使用します。

```bash
python -m pip install pypdf
```

インストール後は、例えば次のように依頼します。

> $mochikabu を使って、勤務先の持株会の拠出額を検討したいです。会社名は〇〇、現在の月額拠出は〇〇円です。まず必要な情報を対話で確認してください。

ユーザーは通常 JSON を編集する必要はありません。エージェントが会社、現在の拠出額、保有状況、制度ルール、目的を確認し、公開資料を調べ、設定ファイルを作成してスクリプトを実行します。

従来どおりリポジトリ全体を clone して開発・テストすることもできますが、Agent への配布単位は `skills/mochikabu/` です。

## 処理の流れ

```text
ユーザーとの対話・持株会資料
    → 会社・保有状況・制度・目標の確認
    → 公開決算資料と株価の取得
    → 財務数値と前提の整理
    → DCF・同業比較・プレミアム率の計算
    → 拠出額別のシミュレーション
    → 予算・集中リスク・制度制約を含む拠出判断
```

## 主な機能

- 持株会画面の読み取り、保有株数・取得費用の整理、株式分割の調整。
- 対象企業と同業他社の公開決算資料の取得、PDF・XBRL の情報抽出。
- 日付・時刻・出典付きの最新株価の取得。
- DCF による推定適正株価（フェアバリュー）と感応度の計算。
- PER・PBR・EV/EBITDA、および各社のフェアバリューに対する株価倍率の比較。
- 奨励金、賞与拠出、配当再投資を考慮した拠出額別の保有株数・自己負担取得費用の試算。
- 予算、勤務先への資産集中、変更可能時期を踏まえた増額・維持・減額等の検討。

## リポジトリ構成

| ファイル | 役割 |
| --- | --- |
| `SKILL.md` | エージェントの対話・調査・判断手順 (English) |
| `scripts/fetch_public.py` | 公開資料と最新株価の取得 |
| `scripts/value_public.py` | DCF、同業比較、評価上の買付シグナル |
| `scripts/analyze.py` | 拠出額別の持株会シミュレーション |
| `references/` | 財務データ仕様、計算式、判断条件 (English) |
| `examples/` | 架空企業・架空口座のサンプル |
| `tests/` | 外部通信を必要としない検証 |

## スクリプトの実行

通常はエージェントが入力ファイルを生成します。手動実行の詳細は [使い方](docs/usage.ja.md) と [データ仕様](references/public-research.md) を参照してください。

```bash
python scripts/fetch_public.py --request research_request.json --output-dir research_raw
python scripts/value_public.py --input financials.json --market-manifest research_raw/manifest.json --output valuation.json
python scripts/analyze.py --config config.json --holdings holdings_snapshot.json --research valuation.json --output output.json
```

オフラインの動作確認:

```bash
python -m unittest discover -s tests -v
python scripts/analyze.py --config examples/config.example.json --holdings examples/holdings_snapshot.example.json --output output.json
```

サンプルの会社、持株口座、財務数値は架空です。実際の判断に転用しないでください。

## データと判断の扱い

無料の株価取得は最新の通常取引時間帯の株価を返しますが、リアルタイム配信は保証しません。株価時刻、取得時刻、遅延の確認状況を出力します。真のリアルタイムデータが必要な場合は、利用権限のある配信元を接続してください。

スクリプトは資料を取得して計算します。財務期間、連結範囲、単位、株式分割、予測前提、同業企業の適切さはエージェントが原資料で確認します。DCF は推定値であり、同業比較と食い違う場合も両方を示します。

公開データや比較企業が不足する場合は `OPEN` または `partial` として扱います。評価シグナルだけで最終判断を確定せず、予算、資産集中、制度上の制約を確認します。銀行など FCFF が適さない企業の専用評価は、現在の DCF スクリプトの対象外です。自動発注機能はありません。

実口座、生成設定、取得財報、実行ログは `.gitignore` で除外しています。配布する資料の利用条件も確認してください。

## FAQ

### Mochikabu は普通の持株会シミュレーターと何が違いますか？

奨励金や積立結果だけでなく、公開財務情報を使った企業価値評価、同業比較、株価水準、勤務先への資産集中、制度上の変更時期まで同じ判断フローで扱います。

### 奨励金が高ければ、必ず持株会を増額しますか？

いいえ。奨励金は実質的な取得コストを下げますが、株価の割高・割安、予算、自社株への集中、ロックアップや変更可能時期なども確認します。条件が不足する場合は結論を確定しません。

### 日本企業専用ですか？

主な利用対象は日本の社員持株会・従業員持株会です。金額は JPY に統一し、会社や制度ルールはユーザー入力と公開資料から確認します。海外企業を扱う場合も、非 JPY の公開財務情報や株価を日付付き為替レートで JPY に換算してからモデル化します。

### Mochikabu は売買を実行しますか？

いいえ。調査、評価、シミュレーション、拠出判断の支援までを扱い、自動発注や取引執行は行いません。

### 非公開の社内情報を投資判断に使いますか？

いいえ。評価や拠出判断には公開情報を使用します。非公開の勤務先情報を買付・売却・増額のトリガーとして扱いません。

## License

[MIT License](LICENSE).
