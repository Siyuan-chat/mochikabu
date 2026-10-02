# 利用ガイド

[README](../README.md) · [評価方法](valuation.ja.md) · [データ仕様（English）](../references/public-research.md)

## 最初の対話

ユーザーは会社名と持株会を検討したい理由を伝えます。保有画面や制度説明があれば、エージェントは先にその情報を読み、すでに分かっている内容を再質問しません。

確認する情報は必要な範囲で段階的に整理します。

| 分類 | 確認する内容 |
| --- | --- |
| 現在の状態 | 保有株数、本人拠出、奨励金、取得額、月額・賞与拠出 |
| 制度 | 奨励金率、上限・単位、変更時期、賞与月、配当、税・手数料、引出制限 |
| 目的 | 積立期間、株数または費用の目標、無理なく拠出できる金額 |
| リスク | 勤務先株式への資産集中、収入と資産の同時リスク |

通貨は日本円に固定します。会社の公表情報、証券コード、株価、財務数値はエージェントが調べます。確認できない制度や数値をサンプル値で埋めません。

## 入力ファイルはエージェントが作成

| 入力 | 内容 |
| --- | --- |
| `research_request.json` | 対象企業・比較企業、公開決算資料の URL |
| `financials.json` | 原資料で確認した財務数値、出典、比較口径、DCF 前提 |
| `config.json` | 対話で整理した持株会制度、候補拠出額、期間、目標 |
| `holdings_snapshot.json` | 保有画面等から整理した現状 |

入力は利用中の作業ディレクトリに保存します。スキルを別の場所に導入した場合は、スクリプトのパスを導入先に合わせて指定してください。ユーザーがこれらを手作業で編集する必要はありません。

## 取得・評価・試算

```bash
python scripts/fetch_public.py --request research_request.json --output-dir research_raw
python scripts/value_public.py --input financials.json --market-manifest research_raw/manifest.json --output valuation.json
python scripts/analyze.py --config config.json --holdings holdings_snapshot.json --research valuation.json --output output.json
```

取得結果は `research_raw/manifest.json` に記録されます。元の財報、PDF のページ別テキスト、XBRL の事実・コンテキスト・単位も保存します。PDF からの抽出ができない場合は、原本をエージェントが読みます。

エージェントは、連結範囲、期間、単位、臨時損益、株式分割を確認してから財務数値を評価入力にします。予測 FCF、割引率、永久成長率は、公開事実と区別した前提です。

`config.json` の `company_id` は評価対象と一致させます。安全余裕率と奨励金・税率も評価入力と一致させます。株価の有効期間を過ぎた場合は更新します。

## 最終的に読む内容

- 現在の株数と、本人負担・会計上の取得費用。
- 株価の時刻・出典・遅延状態。
- フェアバリューの中心値と感応度範囲。
- 自社のフェアバリューに対する株価プレミアムと、同業比較によるプレミアム。
- 月額・賞与拠出別の将来株数、本人負担取得費用、配当再投資の影響。
- 増額・維持・減額等の結論、その理由、次に見直す条件と時期。

## 状態と失敗時の対応

| 状態 | 意味・対応 |
| --- | --- |
| `PUBLIC` | 公開資料・市場データに基づく値。原資料の確認は必要 |
| `MODELED` | 確認済み入力と明示した前提から計算した値 |
| `INDICATIVE` | 評価条件に基づく参考シグナル。制度・予算等の最終確認が必要 |
| `OPEN` | 情報不足、期限超過、または適用できない計算 |
| `SYNTHETIC` | 架空入力を使った動作確認 |
| `partial` | 一部の取得・評価が未完了 |

取得・評価スクリプトは `partial` の場合に終了コード `2` を返し、利用できた成果物は残します。エージェントは不足項目を確認し、影響する処理だけ再実行します。成功表示のために未知の数値を補いません。

## 動作確認とデータ保護

```bash
python -m unittest discover -s tests -v
python scripts/analyze.py --config examples/config.example.json --holdings examples/holdings_snapshot.example.json --output output.json
```

テストは外部サービスへのアクセスを必要としません。サンプルの制度・財務・口座は架空です。実データ、ダウンロードした財報、設定、ログは Git の追跡対象から除外されています。保存先を変更する際は除外設定も確認してください。
