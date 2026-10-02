# mochikabu

**対話から始める、社員持株会のための AI エージェント用スキル。**

[English](README.en.md) · [使い方](docs/usage.ja.md) · [評価方法](docs/valuation.ja.md) · [スクリプト仕様（English）](references/public-research.md)

特定の会社に依存せず、公開財務情報、最新の株価、同業他社の評価、持株会の奨励金を組み合わせて、買付・拠出額の検討を支援します。金額はすべて **日本円（JPY）** です。

ユーザーは会社名、現在の拠出額、保有状況、目的などをエージェントと話すだけです。エージェントが不足情報を確認し、公開資料を調べ、設定ファイルを作成してスクリプトを実行します。通常の利用で JSON の編集は必要ありません。

## できること

- 持株会画面の読み取り、保有株数・取得費用の整理、株式分割の調整。
- 対象企業と同業他社の公開決算資料の取得、PDF・XBRL の情報抽出。
- 日付・時刻・出典付きの最新株価の取得。
- DCF による推定適正株価（フェアバリュー）と感応度の計算。
- PER・PBR・EV/EBITDA、および各社のフェアバリューに対する株価倍率の比較。
- 奨励金、賞与拠出、配当再投資を考慮した拠出額別の保有株数・自己負担取得費用の試算。
- 予算、勤務先への資産集中、変更可能時期を踏まえた増額・維持・減額等の検討。

## 処理の流れ

```text
ユーザーとの対話・持株会資料
    → 会社・保有状況・制度・目標の確認
    → 公開決算資料と株価の取得
    → エージェントによる財務数値と前提の整理
    → DCF・同業比較・プレミアム率の計算
    → 拠出額別の試算
    → 根拠と条件を示した買付・拠出判断
```

| ファイル | 役割 |
| --- | --- |
| `SKILL.md` | エージェントの対話・調査・判断手順（English） |
| `scripts/fetch_public.py` | 公開資料と最新株価の取得 |
| `scripts/value_public.py` | DCF、同業比較、評価上の買付シグナル |
| `scripts/analyze.py` | 拠出額別の持株会シミュレーション |
| `references/` | 財務データ仕様、計算式、判断条件（English） |
| `examples/` | 架空企業・架空口座のサンプル |
| `tests/` | 外部通信を必要としない検証 |

## 導入

Python 3.10 以降を使用します。評価・試算・テストは標準ライブラリで動作します。PDF のテキスト抽出には `pypdf` を使用します。未導入の場合は原本を保存し、エージェントによる読取が必要な状態として報告します。

```bash
python -m pip install pypdf
```

このリポジトリ全体が `mochikabu` スキルです。利用するエージェントのスキル保存先に配置してください。ユーザー用の Codex スキルとして配置する例：

```bash
git clone https://github.com/Siyuan-chat/mochikabu.git ~/.codex/skills/mochikabu
```

Windows PowerShell の例：

```powershell
git clone https://github.com/Siyuan-chat/mochikabu.git "$env:USERPROFILE\.codex\skills\mochikabu"
```

エージェントからスキルが参照できる状態で、次のように依頼します。

> $mochikabu を使って、勤務先の持株会の拠出額を検討したいです。会社名は〇〇、現在の月額拠出は〇〇円です。まず必要な情報を対話で確認してください。

## スクリプトの実行

通常はエージェントが次の入力を生成します。手動実行の詳細は [使い方](docs/usage.ja.md) と [データ仕様](references/public-research.md) を参照してください。

```bash
python scripts/fetch_public.py --request research_request.json --output-dir research_raw
python scripts/value_public.py --input financials.json --market-manifest research_raw/manifest.json --output valuation.json
python scripts/analyze.py --config config.json --holdings holdings_snapshot.json --research valuation.json --output output.json
```

オフラインの動作確認：

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

## ライセンス

[MIT License](LICENSE)。
