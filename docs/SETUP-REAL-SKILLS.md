# 本物のskill/ループ導入手順（opencode-loop / BMAD-METHOD / spec-kit）

このリポジトリの「自作層（数値検証ゲート・decisionキュー・承認GUI・移行ガードレール）」に、
WEBで有名な本物のツールを組み合わせるための**導入手順だけ**をまとめる（実インストールは各自の環境で）。

## 役割分担（本物 × 自作）
| 層 | 採用 | 種別 |
|---|---|---|
| 設計書生成（レガシー→spec） | **BMAD-METHOD** brownfield「Document existing project」 | 本物 |
| 実装 | このリポジトリの dev/qa エージェント（golden 数値ゲート密結合） | 自作 |
| ループ機構 | **opencode-loop**（`opencode-loopd`） | 本物 |
| 数値検証ゲート / decisionキュー / 承認GUI / pyo3・挙動不変ガード | 本リポジトリ | 自作 |

> **spec-kit は使わない。** spec→tasks→implement の規律はこのリポジトリの orchestrator + `tasks.md` + dev/qa が担っており、spec-kit と二重管理になる。また spec-kit の汎用 implement は golden 数値ゲートを知らないため、挙動不変保証が崩れる。

> **BMAD の dev/QA エージェントも使わない。** 同じ理由（ゲート非対応）。BMAD は「設計書生成」フェーズのみで使い、実装フェーズは自前エージェントで回す。

## 前提
- opencode が動く環境（本マシンには未インストール。動かすマシンで `npm i -g opencode-ai`）
- Node.js 20.12+（確認: `node -v`）
- uv（spec-kit 用。確認: `uv --version`）
- Python 3.10+（検証ツール用）

---

## 1. opencode-loop（ループ機構）
```bash
npx -y @bybrawe/opencode-loop@latest      # ~/.config/opencode/plugins/ に入る
# opencode を再起動してから:
/loop-doctor                              # 動作確認
```
インストール先: `~/.config/opencode/plugins/opencode-loop.js`（Windowsは `%USERPROFILE%\.config\opencode\plugins\`）。

### 今回の要件に効くフラグ
| フラグ | 用途 |
|---|---|
| `--stop-file <file>` | **decision発生で停止＝人間承認ゲート** |
| `--max-runs <n>` / `--max-runtime <6h>` / `--max-failures <n>` | 無人運転の安全弁 |
| `--ask-never` | 質問せず仮定で進む（使わない方が安全） |

> **`--verify` は使わない。** golden 検証はユニットごとに expected/actual パスと tolerance（設計書 frontmatter 由来）が異なる。ループ起動時に静的コマンドとして渡せないため、`--verify` には出さず qa サブエージェントの中に置いたまま運用する。`--verify` を使う場合は「全 verified ユニットを一括再検証する回帰スイープ」専用コマンドとして切り出すこと。

### デーモン（無人運転）
```bash
opencode-loopd --project . --every 10m --prompt-file loop-prompt.md
# Windows タスクスケジューラ登録:
opencode-loopd install-task --project "C:\work_space\opencode-settings" --every 10m
```

---

## 2. BMAD-METHOD（設計＝レガシー→設計書 / 実装エージェント）
```bash
npx bmad-method@latest install --tools opencode
# 対話式。モジュールは BMM(BMad Method) を選択。skill は .agents/skills に入る
```
- opencode サポート確認済み: `opencode  OpenCode  .agents/skills`。
- **設計用の本命** = brownfield の「**Document existing project (DP)**」ワークフロー。
  別repoのレガシー Fortran を入力に、既存コードから設計/ドキュメントを生成する。
- 実装用 = BMAD の dev / QA エージェント。

### ★ GUI 連携の橋渡し（必須の1ステップ）
BMAD は独自の場所/書式で設計書を出力する。承認GUI(Review Console)は `docs/design/*.md`
（`docs/design/TEMPLATE.md` のfrontmatter）を読む。よって:
- BMAD の出力を `docs/design/<module>.md` に置き、先頭に
  `status: draft` / `module:` / `tolerance:` のfrontmatterを付与して正規化する。
- これで設計段階も GUI で承認/コメント差し戻しが回る（`docs/design/REVIEW-SCHEMA.md` 参照）。
- 正規化は手動でも、Analyst エージェントに「BMAD出力をTEMPLATE形式に整える」と指示してもよい。

---

## 3. spec-kit（このプロジェクトでは使わない）

spec→tasks→implement の規律はこのリポジトリの orchestrator + `tasks.md` + dev/qa が担っているため不要。

---

## 4. 全体の配線（本物 × 自作のループ）

### Phase 0-1（設計フェーズ）— 人間ペース、ループなし
```
BMAD(brownfield: Document existing project)
    → 設計書を生成
    → analyst が docs/design/<module>.md に正規化
        （status:draft, module, tolerance を frontmatter に付与、Fortran の罠チェック）
    → Review Console で承認 / コメント差し戻し
```

### Phase 2（実装フェーズ）— opencode-loopd が駆動
```bash
opencode-loopd --project . --every 10m \
  --prompt-file loop-prompt.md \
  --stop-file docs/decisions/.has-pending \
  --max-failures 3 --max-runtime 6h
```

- `loop-prompt.md`: プロジェクトルートに配置済み。orchestrator を 1 イテレーション進める内容。
- `--stop-file`: `tools/sync_stop_file.py` が冪等に管理する（下記参照）。orchestrator イテレーション末尾と Review Console の decision 承認後に自動実行される。
- `--verify` は使わない（ユニットごとに tolerance が異なるため静的コマンドにできない）。

### stop-file のライフサイクル（実装済み）
```
docs/decisions/ に pending あり  → tools/sync_stop_file.py → .has-pending 作成 → ループ停止
    ↓ Review Console で承認
docs/decisions/ に pending なし  → tools/sync_stop_file.py → .has-pending 削除 → ループ再開
```
`sync_stop_file.py` は2か所から呼ばれる:
1. orchestrator プロンプト末尾（各イテレーション終了時）
2. Review Console `/api/decisions/{file}/resolve`（承認/却下後）

### Windows タスクスケジューラ登録
```bash
opencode-loopd install-task --project "C:\work_space\opencode-settings" --every 10m
```

---

## 流れ（まとめ）
```
【Phase 0-1 / 人間ペース】
BMAD(brownfield) → 設計書生成 → analyst が正規化(docs/design/) → GUIで承認/差し戻し

【Phase 2 / 機械ペース】
opencode-loopd → orchestrator 1イテレーション
    → dev 実装 → qa が compare.py で golden 検証（数値ゲート）
    → PASS: tasks.md を verified に → 次サイクル
    → FAIL×3 / 仕様割れ: decision 起票 → sync_stop_file → ループ停止
        → GUI で承認 → sync_stop_file → ループ再開
```
本物（BMAD/loop）は「書く・回す」、自作層（検証ゲート・decisionキュー・承認GUI）は「人が承認・数値で守る」。
