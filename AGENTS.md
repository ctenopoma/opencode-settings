# プロジェクト: Fortran → Python + Rust(pyo3) 移行

このリポジトリは **opencode の設定・運用基盤**。Fortran 本体は別リポジトリ（読み取り専用で参照）。

## 不変のルール（全エージェント共通）
1. **設計書ファースト**: `docs/design/*.md` が `status: approved` のものだけが実装の根拠。未承認の設計に基づく実装は禁止。
2. **挙動不変**: リファクタしてよいのは構造のみ。数値結果・丸め順序・収束条件は変えない。検証は `fixtures/golden/` との数値比較で担保。
3. **推測禁止**: 仕様が確定できない点は埋めず、`docs/decisions/` に起票して人間の判断を待つ。
4. **状態は永続化**: 進捗は必ず `tasks.md` に書く。会話の記憶に頼らない。
5. **Fortran の罠**: 列優先 / 1 始まり配列 / implicit 型 / COMMON・SAVE のグローバル状態 / D 指数表記。

## ディレクトリ
- `prompts/` … 各エージェントのシステムプロンプト
- `docs/design/` … 設計書（人間が承認）
- `docs/decisions/` … 判断キュー（人間が GUI で承認）
- `docs/migration-map.md` … モジュール対応表
- `tasks.md` … タスクボード
- `fixtures/golden/` … レガシー基準入出力
- `tools/verify/compare.py` … 数値比較ゲート
- `tools/review-console/` … 承認 GUI

## エージェント
- `orchestrator`(primary, Opus): 司令塔。tasks 選択・委譲・判定・decision 起票。
- `analyst`(Opus): レガシー読解 → 設計書ドラフト。
- `architect`(Opus): 境界・分担設計。
- `dev`(Sonnet): 実装。
- `qa`(Sonnet): golden 検証。
