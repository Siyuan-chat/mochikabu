# 評価方法と買付判断

[README](../README.md) · [利用ガイド](usage.ja.md) · [計算仕様（English）](../references/public-research.md)

## フェアバリューの位置付け

ここでのフェアバリューは、公開情報と明示した前提から推定する適正株価です。将来の実現株価や会計上の公正価値を保証するものではありません。中心値だけでなく、割引率と永久成長率の感応度を示します。

## DCF

企業全体のフリーキャッシュフロー（FCFF）を割り引き、企業価値から純有利子負債を差し引いて株主価値を求めます。

```text
PV_FCF = sum(FCF_t / (1 + WACC)^t)
TerminalValue = FCF_last * (1 + g) / (WACC - g)
EnterpriseValue = PV_FCF + TerminalValue / (1 + WACC)^N
EquityValue = EnterpriseValue - NetDebt
FairValuePerShare = EquityValue / Shares
```

FCF と純有利子負債は十億円、株数は百万株で入力するため、スクリプトでは株価への換算時に `1000` を掛けます。`WACC > g` が必要です。会社独自のキャッシュフロー指標と FCFF を混同せず、純有利子負債の二重控除を避けます。

銀行等に FCFF を機械的に適用しません。適切な専用評価をエージェントが別途行い、現行スクリプトの対象外となる部分を示します。

## 同業他社との比較

比較企業の選定理由を記録し、事業構成、地域、成長率、利益率、財務レバレッジ、会計基準を確認します。計算対象の期間・連結範囲も統一します。参考シグナルには原則として独立した適切な比較企業が 3 社以上必要です。

| 比較指標 | 計算 |
| --- | --- |
| 自社フェアバリューに対するプレミアム | `Price / OwnFairValue - 1` |
| 同業のフェアバリュー倍率に対する相対プレミアム | `(TargetPrice / TargetFairValue) / median(PeerPrice / PeerFairValue) - 1` |
| PER による同業評価株価 | `median(PeerPE) * TargetEPS` |
| PBR による同業評価株価 | `median(PeerPB) * TargetBPS` |
| EV/EBITDA による同業評価株価 | `(median(PeerEV_EBITDA) * TargetEBITDA - TargetNetDebt) / TargetShares` |
| 同業評価株価に対するプレミアム | `Price / PeerImpliedFairValue - 1` |

マイナスは割安側、プラスは割高側を示します。赤字企業の PER、銀行の EV/EBITDA など、経済的に適さない指標は使いません。同業全体が割高な可能性もあるため、相対的な割安だけで買付を支持しません。DCF と同業評価の差は明示します。

## 奨励金と本人負担

```text
EffectiveIncentive = IncentiveRate * (1 - IncentiveTaxRate)
PersonalPurchaseCost = MarketPrice / (1 + EffectiveIncentive)
TargetCost = FairValue * (1 - MarginOfSafety)
MarginalTargetMarketPrice = TargetCost * (1 + EffectiveIncentive)
```

制度固有の奨励金計算、税、手数料がある場合はその影響を確認します。本人負担取得費用と、口座上の購入金額から計算する取得費用は別に示します。

## 参考シグナル

| スクリプトの出力 | 意味 |
| --- | --- |
| `consider_increase` | 本人負担費用が安全余裕の条件を満たし、同業プレミアムの条件も満たす |
| `avoid_increase` | 評価上の安全余裕条件を満たさない |
| `review_peer_premium` | 安全余裕条件は満たすが同業比較との不一致がある |
| `resolve_evidence` | 株価・評価・同業情報・判断基準の不足を解消する必要がある |

安全余裕率と許容プレミアムは、対話で整理した方針と明示した前提から設定します。スクリプトは、この参考シグナルと別に、拠出額候補を目標達成シナリオ数で採点します。候補の採点だけで買付の結論は確定しません。

最終判断では、無理なく続けられる拠出額、勤務先株式への資産集中、変更可能時期、引出・売却制限、手数料等を確認します。変更がすぐにできない場合は、次の変更可能時期に向けた結論を示します。

## 株価の時間とデータ品質

無料取得の株価は、時刻付きの最新通常取引株価です。取得できたこととリアルタイム配信が保証されることは別です。遅延状態が不明なら `UNKNOWN` として表示します。

評価スクリプトは通常 72 時間以内の株価を使用します。休日などによる変更は理由を記録します。決算資料の新しさと数値の比較可能性はエージェントが確認します。原資料、ページ・XBRL コンテキスト、出典 URL、財務期間を残します。
