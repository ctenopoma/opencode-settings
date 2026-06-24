# Decision Queue（人間の設計判断キュー）の様式

AI が判断できない設計判断を `docs/decisions/NNNN-<slug>.md` として起票する。
人間は **Review Console (GUI)** または直接編集で `decision` と `status` を埋める。
`status: approved` になったものだけを Orchestrator が実装に反映する。

## frontmatter スキーマ

```yaml
---
id: 0001
title: 短い要約
status: pending        # pending | approved | rejected
related_units:         # 影響するユニット（tasks.md の id）
  - unit-xxx
recommendation: B      # AI の推奨（選択肢のラベル）
decision:              # ← 人間が記入。承認した選択肢のラベル
decided_by:            # ← 人間が記入
decided_at:            # ← 人間が記入（YYYY-MM-DD）
---
```

## 本文の構成
1. **背景** — なぜこれが問題か。元コードの該当箇所。
2. **何が決められないか** — AI が確定できない理由。
3. **選択肢** — A/B/C... それぞれの内容とトレードオフ。
4. **推奨と根拠** — AI が `recommendation` をそう選んだ理由。
5. **人間メモ** — 承認者が補足を書く欄。

承認後、Orchestrator は decision の内容を該当 `docs/design/*.md` に反映し、関連ユニットを `blocked` から `pending` に戻す。
