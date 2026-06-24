# opencode-settings — Fortran → Python + Rust 移行基盤

800+ ファイルのレガシー Fortran を、リファクタ込みで **Python + Rust(pyo3)** に移行するための
opencode 設定・運用基盤。

**流れ**: レガシー読解 → 設計書ドラフト → **人間が GUI で承認** → 自動で実装・検証ループ →
判断不能点を decision queue に貯めて人間に相談 → 承認 → 反映 → 再開。

```
┌── Analyst ──→ 設計書ドラフト ──┐
│                               ▼
│                      [人間レビュー / 承認]  ←─ Review Console (GUI)
│                               │
│        ┌──────────────────────┘  approved
│        ▼
└─ Orchestrator ─→ Dev(実装) ─→ QA(golden検証) ─→ verified
         │                                   │ FAIL×3 / 仕様割れ
         └──────── decision 起票 ────────────┘
                        │ pending
                 [人間が GUI で承認] → 設計書反映 → 再開
```

---

## 1. 導入手順

### 1-1. opencode 本体
```bash
npm i -g opencode-ai        # または brew install sst/tap/opencode
opencode auth login         # Anthropic の鍵を設定
```

### 1-2. このリポジトリ
`opencode.json` と `AGENTS.md` を opencode が自動で読む。リポジトリ直下で `opencode` を起動するだけ。
- エージェント定義は `opencode.json` の `agent` ブロック。プロンプト実体は `prompts/*.md`。
- **モデル ID は環境に合わせて調整**: 既定は `anthropic/claude-opus-4-8`（賢いマネージャ）/ `anthropic/claude-sonnet-4-6`（作業者）の 2 モデル。`opencode models` で利用可能 ID を確認し、合わなければ差し替える。

### 1-3. 検証ツール
```bash
python --version            # 3.10+
# compare.py は標準ライブラリのみ。追加依存なし。
```

### 1-4. Review Console（承認 GUI）
```bash
cd tools/review-console
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements.txt
python app.py               # → http://127.0.0.1:8765
```
GitHub 不要・ローカル完結。pending な decision をブラウザで承認するとファイルに書き戻る。

### 1-5. 実装側ツールチェーン（Phase 2 で必要）
```bash
pip install maturin numpy   # pyo3 ビルド
# Rust: https://rustup.rs
```

---

## 2. 開発手順（運用フロー）

### Phase 0 — レガシー読解
opencode で:
```
@analyst <別リポジトリの対象 Fortran ファイル> の設計書ドラフトを TEMPLATE に従って作って
```
→ `docs/design/<module>.md` が `status: draft` で生成される。

### Phase 1 — アーキ設計
```
@architect この設計書の Rust/Python 分担と pyo3 境界を設計して、migration-map と tasks に積んで
```

### 人間レビュー（★ここが承認ゲート）— すべて Review Console (GUI) で
1. **設計書タブ**で対象設計書を開く:
   - 問題なければ **［この設計書を承認］**（→ `status: approved`、承認者を記録）。
   - 直してほしければ **指摘箇所＋コメントを入力して［コメントを出す(差し戻し)］**（→ `status: changes_requested`、サイドカー `*.review.yaml` に保存）。AI(analyst) が修正して再提出する。
2. **判断キュータブ**で pending decision を承認/却下。
3. 承認済みになると Orchestrator が `tasks.md` の該当ユニットを実装に回す。`tolerance` は設計書 frontmatter で確定しておく。

### Phase 2 — 自動ループ
opencode で `orchestrator` を primary にして:
```
tasks.md を回して。承認済みユニットを実装→golden検証し、判断が要る点は decision に積んで止めて
```
Orchestrator が dev/qa を回し、FAIL×3 または仕様割れで `docs/decisions/` に起票して停止。

### 相談 → 再開
- Review Console で decision を承認 → Orchestrator が設計書へ反映し、blocked を pending に戻して再開。
- 無人で回し続けたい場合は opencode の常駐 + 定期起動（cron 等）で `orchestrator` を周回させる。

---

## 3. ゴールデン基準の採取（重要）
レガシーの再ビルド可否に依存しない。`fixtures/golden/<unit>/expected/` に正解出力を置けばよい:
- **A**: 既存の動く実行体をブラックボックス実行して採取（推奨・コンパイラ不問）。
- **B**: チームの過去回帰出力を流用。
- **C**: Intel ifx（無償）で採取だけ行う。

`tools/verify/compare.py` は方法を問わず数値比較するだけ。詳細は `fixtures/golden/README.md`。

---

## 4. 方法論の出典
- 役割分離・brownfield（既存コード解析→設計）: BMAD-METHOD
- spec→tasks→implement の規律: GitHub Spec Kit
本リポジトリはこれらの考え方を opencode のエージェント/フローに落とし込んだもの。
