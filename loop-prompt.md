orchestrator として tasks.md を **1 イテレーションだけ** 進めよ。

## このイテレーションでやること（順番に）

1. `docs/decisions/` に `status: pending` の decision がないか確認する。
   - あれば新規実装を始めず「pending decision: <ファイル名> が承認待ちです」と報告して終了する。
2. `tasks.md` から `pending` 状態で、かつ `docs/design/*.md` が `status: approved` のユニットを 1 つ選ぶ。
   - 該当がなければ「全ユニット完了または全ブロック中」と報告して終了する。
3. そのユニットを `in-progress` に更新し、`dev` サブエージェントに実装させる。
4. 実装後、`qa` サブエージェントに `tools/verify/compare.py` で golden 検証させる。
5. 判定:
   - PASS → `verified` に更新。
   - FAIL → 原因を分析して dev に再依頼（最大 3 回）。3 回失敗または仕様割れ → `blocked` にして `docs/decisions/` に起票。
6. **最後に `python tools/sync_stop_file.py` を実行して stop-file を同期する。**
7. 今回のイテレーション結果を 3 行以内でサマリして終了する。

## 制約
- 1 イテレーション = 1 ユニット。複数ユニットをまとめて処理しない。
- 状態は必ず `tasks.md` に書いてから終了する。
- 設計書が `approved` でないユニットは絶対に実装しない。
