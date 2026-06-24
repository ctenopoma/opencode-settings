# 本物のskill/ループ導入手順（opencode-loop / BMAD-METHOD / spec-kit）

このリポジトリの「自作層（数値検証ゲート・decisionキュー・承認GUI・移行ガードレール）」に、
WEBで有名な本物のツールを組み合わせるための**導入手順だけ**をまとめる（実インストールは各自の環境で）。

## 役割分担（本物 × 自作）
| 層 | 採用 | 種別 |
|---|---|---|
| 設計書生成（レガシー→spec） | **BMAD-METHOD** brownfield「Document existing project」 | 本物 |
| 実装 | **BMAD** dev/QA、または **spec-kit** | 本物 |
| ループ機構 | **opencode-loop**（`/loop` + `opencode-loopd`） | 本物 |
| 数値検証ゲート / decisionキュー / 承認GUI / pyo3・挙動不変ガード | 本リポジトリ | 自作 |

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
| `--verify "<cmd>"` | 失敗で自動修正プロンプト → **golden検証ゲートを刺す** |
| `--until <marker>` / `--stop-file <file>` | **decision発生で停止＝人間承認ゲート** |
| `--max-runs <n>` / `--max-runtime <6h>` / `--max-failures <n>` | 無人運転の安全弁 |
| `--ask-never` | 質問せず仮定で進む（使わない方が安全） |

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

## 3. spec-kit（実装フロー・任意）
BMAD実装の代わりに spec→plan→tasks→implement の流儀を使いたい場合のみ。
```bash
uvx --from git+https://github.com/github/spec-kit.git specify init . --integration opencode
# コマンドは .opencode/commands に入る。/specify /plan /tasks /implement が使える
```
> 注意: v0.10.0 以降 `--ai` は廃止、`--integration` を使う。

---

## 4. 全体の配線（本物 × 自作のループ）
```bash
opencode-loopd --project . --every 10m \
  --prompt-file loop-prompt.md \
  --verify "python tools/verify/compare.py --expected fixtures/golden/<unit>/expected --actual fixtures/golden/<unit>/actual --rtol <r> --atol <a>" \
  --stop-file docs/decisions/.has-pending \
  --max-failures 3
```
- `loop-prompt.md`: 「orchestrator として tasks.md を1イテレーション進めよ」を書く。
- `--verify`: golden検証が通らない限り次に進ませない（数値ゲート）。
- `--stop-file`: orchestrator が pending decision 起票時に `docs/decisions/.has-pending` を作る運用にして停止させる → 人間がGUIで承認 → ファイル削除で再開。
- 承認/差し戻しは **Review Console (GUI)** で（`tools/review-console/`）。

## 流れ（まとめ）
```
BMAD(brownfield) → 設計書 → [docs/design へ正規化] → GUIで承認/コメント
        ↓ approved
opencode-loop が orchestrator を周回 → dev/QA実装 → compare.py で検証
        ↓ 判断不能
decision起票 + stop-file → ループ停止 → GUIで承認 → stop-file削除 → 再開
```
本物は「書く/回す」、GUIと検証ゲートは「人が承認/数値で守る」。両方が必要。
