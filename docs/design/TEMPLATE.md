---
module: <fortran-module-name>
source_files:
  - path/to/legacy.f
status: draft        # draft -> review -> changes_requested -> approved
approved_by:
approved_at:
tolerance:           # golden 比較の許容誤差（承認時に確定）
  rtol: 1.0e-9
  atol: 1.0e-12
---

# 設計書: <モジュール名>

## 1. 目的と責務
<このモジュール/サブルーチンが何を計算するか。元コードを読まずに分かるように。>

## 2. 公開インターフェース
| 名前 | 種別 | 引数 (intent / 型 / 次元) | 戻り値 | 説明 |
|---|---|---|---|---|
| sub_foo | subroutine | x(in, real, n), y(out, real, n) | - | ... |

## 3. グローバル状態（最重要）
| 種別 | 名前 | 型/次元 | 初期化 | 移行後の置き場所 |
|---|---|---|---|---|
| COMMON | /blk/ a, b | ... | BLOCK DATA | 構造体 State に閉じ込め |

## 4. 数値的振る舞い
- アルゴリズム / 反復・収束条件 / 許容誤差 / 特異点処理 / 丸めに敏感な箇所。

## 5. 副作用・I/O
- ファイル、ユニット番号、FORMAT、単位系。

## 6. Fortran 固有の注意
- implicit 型 / 列優先 / 1 始まり / EQUIVALENCE / GOTO など。

## 7. 検証（golden）
- 入力の切り出し方、期待出力の単位・桁、許容誤差の根拠。

## 8. 移行方針（Architect 記入）
- Rust / Python の分担、pyo3 境界シグネチャ、状態の持たせ方。

## 9. 未解決（要・人間判断）
- 仕様が確定できない点。Orchestrator がここを decision queue 化する。
