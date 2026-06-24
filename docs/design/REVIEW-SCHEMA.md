# 設計書レビューの仕組み（コメント/承認）

設計書 `docs/design/<name>.md` のレビュー状態とコメントは、**サイドカー** `docs/design/<name>.review.yaml`
に機械可読で保存する。Review Console (GUI) が読み書きし、AI(analyst) がこれを読んで設計書を直す。

## レビューの状態遷移（設計書 frontmatter の `status`）
```
draft → review → changes_requested → approved
                       ↑__________│   （コメント対応のたびに行き来）
```
- **draft**: analyst が生成した直後。
- **review**: 人間レビュー中。
- **changes_requested**: 人間がコメントを出した（差し戻し）。AI が対応する。
- **approved**: 人間が承認。**この状態のものだけ実装してよい。**

## サイドカー `*.review.yaml`
```yaml
status: changes_requested   # review | changes_requested | approved
comments:
  - id: 1
    target: "3. グローバル状態"   # 指摘箇所（節見出し等・任意）
    body: "COMMON /grid/ の dy が抜けている"
    by: naoki
    at: 2026-06-25
    status: open               # open | resolved
```

## AI(analyst) の対応手順
1. 担当設計書の `*.review.yaml` で `status: open` のコメントを読む。
2. 設計書 `*.md` を**コメントに沿って修正**する。
3. 対応したコメントは `*.review.yaml` の該当 `status` を `resolved` にし、必要なら設計書に反映理由を残す。
4. 全コメント解決後、設計書 frontmatter の `status` を `review` に戻す（再レビュー依頼）。
5. **人間が再度 GUI で承認**して初めて `approved`。

> AI はコメントを勝手に削除しない。`resolved` にするだけ（履歴を残す）。
