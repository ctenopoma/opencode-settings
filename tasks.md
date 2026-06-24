# タスクボード（移行ユニット）

Orchestrator が更新する状態の正典。1 行 = 1 移行ユニット。

状態: `pending`（着手可） / `in-progress` / `verified`（golden 合格） / `blocked`（decision 待ち）

| unit id | 設計書 | 状態 | 試行回数 | blocked_by | メモ |
|---|---|---|---|---|---|
| example-grid-init | docs/design/grid.md | blocked | 0 | 0001 | サンプル。実開始時に削除 |

## 運用ルール
- 着手前に設計書が `status: approved` であること。
- `docs/decisions/` に `pending` がある間は新規実装を始めない。
- FAIL は最大 3 回再試行。超えたら `blocked` + decision 起票。
