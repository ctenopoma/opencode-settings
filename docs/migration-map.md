# 移行マップ: Fortran → Python / Rust(pyo3)

Architect が維持する正典。各ユニットの行き先と依存順を管理する。

| unit id | Fortran source | 設計書 | 行き先 (Rust/Python) | pyo3 境界 | 依存 | 状態 |
|---|---|---|---|---|---|---|
| example-grid-init | grid.f: GRIDINIT | docs/design/grid.md | Rust | `grid_init(nx,ny)->Grid` | - | draft |

## 凡例
- **行き先**: Rust=数値カーネル/ホットループ、Python=IO/オーケストレーション/グルー。
- **依存**: 葉（依存なし）から先に移行する。
- **状態**: draft / review / approved / verified。

## 分担の原則
- 性能 critical・決定性が要る数値処理 → Rust
- 設定・ファイル I/O・CLI・組み立て → Python
- 状態は COMMON/module をそのまま移さず、構造体/クラスに閉じ込める（挙動は不変）。
