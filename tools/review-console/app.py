#!/usr/bin/env python3
"""Review Console — ローカル GUI（GitHub 不使用）。

2 つの承認をブラウザで完結させる:
  1. 判断キュー  docs/decisions/*.md … 選択肢を承認/却下して frontmatter に書き戻す。
  2. 設計書      docs/design/*.md     … 承認、またはコメント(指摘)を出して差し戻す。
     コメントはサイドカー docs/design/<name>.review.yaml に機械可読で保存し、
     AI(analyst) がそれを読んで設計書を直して再提出する。
tasks.md の進捗も可視化する。

UX 方針:
  - 画面を勝手に書き換えない。ファイル変化は /api/version の監視で検知し、
    「更新あり」バナーを出すだけ。反映するかは人間が決める（入力中の取りこぼし防止）。
  - 設計書は Markdown としてレンダリングし、節へジャンプできる。
  - コメントは節見出しに紐づけ、クリックで該当箇所へスクロール&ハイライト。
  - analyst が直して再提出したら、前回レビュー時点との差分を表示する。

起動:
    pip install -r requirements.txt
    python app.py            # http://127.0.0.1:8765
"""
from __future__ import annotations

import datetime as dt
import difflib
import hashlib
import re
from pathlib import Path

import markdown as md_lib
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
DECISIONS = ROOT / "docs" / "decisions"
DESIGN = ROOT / "docs" / "design"
TASKS = ROOT / "tasks.md"

app = FastAPI(title="Migration Review Console")

_FM = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


# ---------- 共通: markdown frontmatter ----------
def parse_md(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    m = _FM.match(text)
    if not m:
        return {}, text
    return (yaml.safe_load(m.group(1)) or {}), m.group(2).strip()


def write_md(path: Path, meta: dict, body: str) -> None:
    fm = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
    path.write_text("---\n" + fm + "---\n\n" + body.strip() + "\n", encoding="utf-8")


def today() -> str:
    return dt.date.today().isoformat()


# ---------- markdown レンダリング + 節抽出 ----------
def render_markdown(body: str, key: str = "") -> tuple[str, list[dict]]:
    """body を HTML に変換し、`## ` レベルの節 [{id, name}] を返す。
    見出し id は key で名前空間化して、複数カードを並べても衝突しないようにする。
    """
    m = md_lib.Markdown(extensions=["tables", "fenced_code", "toc"])
    html = m.convert(body)
    prefix = re.sub(r"[^A-Za-z0-9_-]", "-", key)

    sections: list[dict] = []

    def walk(tokens: list[dict]) -> None:
        for t in tokens:
            if t.get("level") == 2:
                sections.append({"id": t["id"], "name": t["name"]})
            walk(t.get("children", []))

    walk(getattr(m, "toc_tokens", []))

    # 見出し id を名前空間化（toc が付けた id だけを対象に置換）
    for s in sections:
        old = f'id="{s["id"]}"'
        new_id = f"{prefix}__{s['id']}" if prefix else s["id"]
        html = html.replace(old, f'id="{new_id}"', 1)
        s["id"] = new_id
    return html, sections


# ---------- decisions ----------
def list_decisions() -> list[dict]:
    if not DECISIONS.exists():
        return []
    out = []
    for p in sorted(DECISIONS.glob("*.md")):
        if p.name == "SCHEMA.md":
            continue
        meta, body = parse_md(p)
        meta["file"] = p.name
        meta["body_html"], _ = render_markdown(body, p.stem)
        out.append(meta)
    return out


# ---------- designs + review サイドカー ----------
def review_path(design: Path) -> Path:
    return design.with_suffix(".review.yaml")


def snapshot_path(design: Path) -> Path:
    """人間が最後にレビューした時点の本文スナップショット（差分表示用）。"""
    return design.with_suffix(".snapshot.md")


def load_review(design: Path) -> dict:
    rp = review_path(design)
    if rp.exists():
        return yaml.safe_load(rp.read_text(encoding="utf-8")) or {}
    return {"comments": []}


def save_review(design: Path, review: dict) -> None:
    review_path(design).write_text(
        yaml.safe_dump(review, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def save_snapshot(design: Path, body: str) -> None:
    snapshot_path(design).write_text(body.strip() + "\n", encoding="utf-8")


def load_snapshot(design: Path) -> str | None:
    sp = snapshot_path(design)
    return sp.read_text(encoding="utf-8").strip() if sp.exists() else None


def make_diff(old: str, new: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            old.splitlines(), new.splitlines(),
            fromfile="前回レビュー時", tofile="現在", lineterm="", n=2,
        )
    )


def list_designs() -> list[dict]:
    if not DESIGN.exists():
        return []
    out = []
    for p in sorted(DESIGN.glob("*.md")):
        if (
            p.name == "TEMPLATE.md"
            or p.name.endswith(".review.md")
            or p.name.endswith(".snapshot.md")
        ):
            continue
        meta, body = parse_md(p)
        review = load_review(p)
        body_html, sections = render_markdown(body, p.stem)
        snap = load_snapshot(p)
        updated = snap is not None and snap.strip() != body.strip()
        out.append(
            {
                "file": p.name,
                "module": meta.get("module", p.stem),
                "status": meta.get("status", "draft"),
                "approved_by": meta.get("approved_by"),
                "approved_at": meta.get("approved_at"),
                "tolerance": meta.get("tolerance"),
                "comments": review.get("comments", []),
                "body_html": body_html,
                "sections": sections,
                "updated_since_review": updated,
                "diff": make_diff(snap, body) if updated else "",
            }
        )
    return out


def task_summary() -> dict:
    if not TASKS.exists():
        return {}
    counts: dict[str, int] = {}
    for line in TASKS.read_text(encoding="utf-8").splitlines():
        for state in ("pending", "in-progress", "verified", "blocked"):
            if re.search(rf"\|\s*{state}\s*\|", line):
                counts[state] = counts.get(state, 0) + 1
    return counts


def version_sig() -> str:
    """関連ファイルの mtime から軽量な署名を作る。変化検知だけに使う。"""
    parts: list[str] = []
    for d in (DECISIONS, DESIGN):
        if d.exists():
            for p in sorted(d.glob("*")):
                if p.is_file():
                    parts.append(f"{p.name}:{p.stat().st_mtime_ns}")
    if TASKS.exists():
        parts.append(f"tasks:{TASKS.stat().st_mtime_ns}")
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()


# ---------- API models ----------
class Approval(BaseModel):
    decision: str
    decided_by: str
    status: str = "approved"
    note: str = ""


class DesignApprove(BaseModel):
    reviewer: str


class Comment(BaseModel):
    by: str
    body: str
    target: str = ""  # 指摘箇所（節見出しなど・任意）


# ---------- API: state / version ----------
@app.get("/api/state")
def api_state():
    return {
        "version": version_sig(),
        "decisions": list_decisions(),
        "designs": list_designs(),
        "tasks": task_summary(),
    }


@app.get("/api/version")
def api_version():
    return {"version": version_sig()}


# ---------- API: decisions ----------
@app.post("/api/decisions/{file}/resolve")
def api_resolve(file: str, body: Approval):
    if ".." in file or "/" in file:
        raise HTTPException(400, "bad name")
    path = DECISIONS / file
    if not path.exists():
        raise HTTPException(404, "not found")
    meta, md = parse_md(path)
    meta.update(
        status=body.status,
        decision=body.decision,
        decided_by=body.decided_by,
        decided_at=today(),
    )
    if body.note:
        md += f"\n\n> 承認メモ: {body.note}"
    write_md(path, meta, md)
    return {"ok": True}


# ---------- API: designs ----------
def _design(file: str) -> Path:
    if ".." in file or "/" in file:
        raise HTTPException(400, "bad name")
    path = DESIGN / file
    if not path.exists():
        raise HTTPException(404, "not found")
    return path


@app.post("/api/designs/{file}/approve")
def api_design_approve(file: str, body: DesignApprove):
    path = _design(file)
    meta, md = parse_md(path)
    meta["status"] = "approved"
    meta["approved_by"] = body.reviewer
    meta["approved_at"] = today()
    write_md(path, meta, md)
    review = load_review(path)
    review["status"] = "approved"
    save_review(path, review)
    save_snapshot(path, md)  # この版を「人間が見た最新」として記録
    return {"ok": True}


@app.post("/api/designs/{file}/comment")
def api_design_comment(file: str, body: Comment):
    path = _design(file)
    review = load_review(path)
    comments = review.setdefault("comments", [])
    cid = (max([c.get("id", 0) for c in comments], default=0)) + 1
    comments.append(
        {
            "id": cid,
            "target": body.target,
            "body": body.body,
            "by": body.by,
            "at": today(),
            "status": "open",
        }
    )
    review["status"] = "changes_requested"
    save_review(path, review)
    # 設計書本体の status も差し戻しに（承認済みでない限り）
    meta, md = parse_md(path)
    if meta.get("status") != "approved":
        meta["status"] = "changes_requested"
        write_md(path, meta, md)
    save_snapshot(path, md)  # コメント時点の版を記録 → 次回再提出との差分が出る
    return {"ok": True, "id": cid}


@app.post("/api/designs/{file}/comment/{cid}/toggle")
def api_toggle_comment(file: str, cid: int):
    path = _design(file)
    review = load_review(path)
    for c in review.get("comments", []):
        if c.get("id") == cid:
            c["status"] = "resolved" if c.get("status") == "open" else "open"
    save_review(path, review)
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


HTML = r"""
<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Migration Review Console</title>
<style>
 :root{--bg:#0f1115;--panel:#161a22;--line:#2a2f3a;--ink:#e6e6e6;--mut:#9aa4b2;
       --ok:#2ea043;--warn:#e0a800;--bad:#d1413b;--blue:#3a6ea5}
 *{box-sizing:border-box}
 body{font-family:system-ui,sans-serif;margin:0;background:var(--bg);color:var(--ink)}
 header{padding:14px 20px;background:var(--panel);border-bottom:1px solid var(--line);
        position:sticky;top:0;z-index:5}
 h1{font-size:16px;margin:0}
 .bar{display:flex;gap:8px;margin-top:8px;font-size:13px;flex-wrap:wrap;align-items:center}
 .chip{padding:2px 10px;border-radius:12px;background:#222836}
 .chip.todo{background:#3a2b00;color:#ffd970}
 nav{display:flex;gap:8px;padding:10px 20px;background:#12151c;
     border-bottom:1px solid var(--line);align-items:center;flex-wrap:wrap;
     position:sticky;top:55px;z-index:5}
 nav button{background:#222836;border:1px solid var(--line);position:relative}
 nav button.on{background:var(--ok);border:none}
 nav .spacer{flex:1}
 nav label{font-size:13px;color:var(--mut);display:flex;align-items:center;gap:5px;cursor:pointer}
 .badge{display:inline-block;min-width:18px;padding:0 5px;margin-left:6px;border-radius:9px;
        background:var(--bad);color:#fff;font-size:11px;line-height:18px;text-align:center}
 .banner{display:none;align-items:center;gap:10px;padding:8px 20px;background:#13314a;
         border-bottom:1px solid #1d4a6e;font-size:13px;position:sticky;top:103px;z-index:4}
 .banner.show{display:flex}
 main{padding:20px;max-width:1180px;margin:0 auto}
 .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;
       padding:16px;margin-bottom:16px}
 .pending,.review,.changes_requested,.draft{border-left:4px solid var(--warn)}
 .approved{border-left:4px solid var(--ok)}
 .rejected{border-left:4px solid var(--bad)}
 .meta{font-size:12px;color:var(--mut)}
 input,textarea,select,button{font-size:14px;padding:6px 8px;margin:4px 4px 4px 0;
        background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:6px}
 textarea{width:100%}
 button{cursor:pointer;background:var(--ok);border:none}
 button.rej{background:var(--bad)} button.sub{background:var(--blue)}
 button.ghost{background:#222836;border:1px solid var(--line)}
 /* 目次 */
 .toc{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}
 .toc a{font-size:12px;color:#bcd;background:#1b2330;border:1px solid var(--line);
        padding:2px 8px;border-radius:10px;text-decoration:none}
 .toc a:hover{background:#243049}
 /* 設計書本文（markdown） */
 .doc{background:var(--bg);border:1px solid var(--line);border-radius:8px;
      padding:6px 18px;max-height:62vh;overflow:auto;line-height:1.7}
 .doc h1{font-size:19px} .doc h2{font-size:16px;border-bottom:1px solid var(--line);padding-bottom:4px;margin-top:20px}
 .doc h3{font-size:14px} .doc code{background:#0b0d11;padding:1px 5px;border-radius:4px}
 .doc pre{background:#0b0d11;padding:10px;border-radius:6px;overflow:auto}
 .doc table{border-collapse:collapse;width:100%;margin:8px 0;font-size:13px}
 .doc th,.doc td{border:1px solid var(--line);padding:6px 8px;text-align:left}
 .doc th{background:#1b2330}
 .doc :target, .doc .flash{animation:flash 2s ease}
 @keyframes flash{0%{background:#5a4a00}30%{background:#5a4a00}100%{background:transparent}}
 /* コメント */
 .cmt{background:var(--bg);border:1px solid var(--line);border-radius:6px;
      padding:8px;margin:6px 0;font-size:13px}
 .cmt.resolved{opacity:.5}
 .cmt.resolved .cbody{text-decoration:line-through}
 .cmt .tgt{color:#9cf;cursor:pointer;text-decoration:underline}
 /* 差分 */
 .diff{font-family:ui-monospace,monospace;font-size:12px;background:var(--bg);
       border:1px solid var(--line);border-radius:6px;padding:8px;max-height:40vh;overflow:auto}
 .dl{white-space:pre-wrap}
 .dl.add{color:#7ee787} .dl.del{color:#ff9492} .dl.hd{color:var(--mut)}
 details summary{cursor:pointer;color:var(--mut)}
 .warnpill{background:#3a2b00;color:#ffd970;padding:2px 8px;border-radius:10px;font-size:12px}
</style></head><body>
<header><h1>🛠 Migration Review Console</h1><div class="bar" id="bar"></div></header>
<nav>
 <button id="t-dec" class="on" onclick="tab('dec')">判断キュー<span class="badge" id="b-dec"></span></button>
 <button id="t-dsg" onclick="tab('dsg')">設計書<span class="badge" id="b-dsg"></span></button>
 <span class="spacer"></span>
 <label><input type="checkbox" id="onlyTodo" onchange="toggleTodo()"> 要対応のみ</label>
 <button class="ghost" onclick="load()">🔄 更新</button>
</nav>
<div class="banner" id="banner">
 <span>🔄 ファイルが更新されました（AI が設計書を直したか、別画面で操作されました）。</span>
 <button class="sub" onclick="load()">反映する</button>
 <button class="ghost" onclick="dismissBanner()">あとで</button>
</div>
<main id="app">読み込み中...</main>
<script>
let DATA={decisions:[],designs:[],tasks:{},version:""};
let TAB='dec', VERSION="", ONLY_TODO=false;

function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function val(id){const e=document.getElementById(id);return e?e.value.trim():'';}
async function post(url,obj){return fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(obj)});}

// ----- 要対応の判定 -----
function decTodo(x){return (x.status||'pending')=='pending';}
function dsgTodo(x){
 const open=(x.comments||[]).filter(c=>c.status=='open').length;
 return x.status!='approved' || open>0 || x.updated_since_review;
}
function counts(){
 return {dec:DATA.decisions.filter(decTodo).length,
         dsg:DATA.designs.filter(dsgTodo).length};
}

// ----- UI 状態の保存/復元（再描画でチラつかせない） -----
function captureUI(){
 const open=new Set();
 document.querySelectorAll('details[open][id]').forEach(d=>open.add(d.id));
 return {y:window.scrollY, open};
}
function restoreUI(s){
 s.open.forEach(id=>{const d=document.getElementById(id);if(d)d.open=true;});
 window.scrollTo(0,s.y);
}

// ----- データ取得（人間の操作 or 明示更新のときだけ） -----
async function load(){
 const s=captureUI();
 DATA=await (await fetch('/api/state')).json();
 VERSION=DATA.version; dismissBanner();
 render(); restoreUI(s);
}
function tab(t){TAB=t;document.getElementById('t-dec').className=t=='dec'?'on':'';
 document.getElementById('t-dsg').className=t=='dsg'?'on':'';render();}
function toggleTodo(){ONLY_TODO=document.getElementById('onlyTodo').checked;render();}

function render(){
 const c=counts();
 document.getElementById('b-dec').textContent=c.dec||'';
 document.getElementById('b-dsg').textContent=c.dsg||'';
 document.getElementById('b-dec').style.display=c.dec?'inline-block':'none';
 document.getElementById('b-dsg').style.display=c.dsg?'inline-block':'none';
 const tasks=Object.entries(DATA.tasks||{}).map(([k,v])=>`<span class="chip">${k}: ${v}</span>`).join('');
 document.getElementById('bar').innerHTML=
   `<span class="chip todo">要対応 判断:${c.dec} / 設計書:${c.dsg}</span>`+(tasks||'<span class="chip">tasks なし</span>');
 document.getElementById('app').innerHTML = TAB=='dec'?renderDecisions():renderDesigns();
}

// ----- 判断キュー -----
function renderDecisions(){
 let items=DATA.decisions.slice();
 if(ONLY_TODO) items=items.filter(decTodo);
 items.sort((a,b)=>(decTodo(b)?1:0)-(decTodo(a)?1:0));
 if(!items.length) return '<p>表示できる判断はありません 🎉</p>';
 return items.map(x=>{
  const st=x.status||'pending';
  const ctrl = st=='pending' ? `<div>
     <input id="who-${x.file}" placeholder="承認者名">
     <input id="dec-${x.file}" placeholder="採用する選択肢 (例: B)" value="${x.recommendation||''}">
     <input id="note-${x.file}" placeholder="メモ(任意)" size="28">
     <button onclick="resolveDec('${x.file}','approved')">承認</button>
     <button class="rej" onclick="resolveDec('${x.file}','rejected')">却下</button></div>`
   : `<div class="meta">decision: ${esc(x.decision)} / by ${esc(x.decided_by)} @ ${x.decided_at||''}</div>`;
  return `<div class="card ${st}"><h3>#${x.id||''} ${esc(x.title||x.file)}</h3>
    <div class="meta">status: ${st} ・ 推奨: ${esc(x.recommendation)||'-'} ・ ${x.file}</div>
    <details id="det-dec-${x.file}"><summary>内容を表示</summary><div class="doc">${x.body_html||''}</div></details>
    ${ctrl}</div>`;
 }).join('');
}
async function resolveDec(file,status){
 const decision=val('dec-'+file), who=val('who-'+file), note=val('note-'+file);
 if(status=='approved' && (!decision||!who)){alert('承認者名と選択肢を入れてください');return;}
 await post(`/api/decisions/${file}/resolve`,{decision:decision||'(却下)',decided_by:who||'unknown',status,note});
 load();
}

// ----- 設計書 -----
function renderDesigns(){
 let items=DATA.designs.slice();
 if(ONLY_TODO) items=items.filter(dsgTodo);
 items.sort((a,b)=>{
   const ao=(a.comments||[]).filter(c=>c.status=='open').length;
   const bo=(b.comments||[]).filter(c=>c.status=='open').length;
   return (dsgTodo(b)-dsgTodo(a)) || (bo-ao);
 });
 if(!items.length) return '<p>表示できる設計書はありません（analyst が生成します）。</p>';
 return items.map(x=>{
  const open=(x.comments||[]).filter(c=>c.status=='open').length;
  const toc=(x.sections||[]).map(s=>`<a href="#" onclick="jump('${s.id}');return false">${esc(s.name)}</a>`).join('');
  const cmts=(x.comments||[]).map(c=>{
    const sec=(x.sections||[]).find(s=>s.name===c.target);
    const tgt=c.target?(sec?`<span class="tgt" onclick="jump('${sec.id}')">📍 ${esc(c.target)}</span> `:'['+esc(c.target)+'] '):'';
    return `<div class="cmt ${c.status}">
      <b>#${c.id}</b> ${tgt}<span class="cbody">${esc(c.body)}</span>
      <span class="meta"> — ${esc(c.by)} @ ${c.at}</span>
      <button class="sub" onclick="toggle('${x.file}',${c.id})">${c.status=='open'?'解決済みにする':'再オープン'}</button></div>`;
  }).join('')||'<div class="meta">コメントなし</div>';
  const updated=x.updated_since_review?`<span class="warnpill">⚠ 前回レビュー後に更新されています</span>`:'';
  const diff=x.diff?`<details id="det-diff-${x.file}"><summary>前回レビューからの変更を表示</summary>
     <div class="diff">${diffHtml(x.diff)}</div></details>`:'';
  const opts=['<option value="">（全体）</option>'].concat(
     (x.sections||[]).map(s=>`<option value="${esc(s.name)}">${esc(s.name)}</option>`)).join('');
  return `<div class="card ${x.status}"><h3>${esc(x.module)} <span class="meta">(${x.file})</span></h3>
    <div class="meta">status: <b>${x.status}</b> ・ 未解決コメント: ${open}
       ${x.approved_by?'・ 承認: '+esc(x.approved_by)+' @ '+x.approved_at:''} ${updated}</div>
    ${diff}
    <div class="toc">${toc}</div>
    <details id="det-body-${x.file}" open><summary>設計書本文</summary>
      <div class="doc" id="doc-${x.file}">${x.body_html||''}</div></details>
    <h4>コメント</h4>${cmts}
    <div style="margin-top:8px">
      <select id="ct-${x.file}" title="指摘する節">${opts}</select>
      <input id="cw-${x.file}" placeholder="レビュアー名">
      <textarea id="cb-${x.file}" rows="2" placeholder="コメント(指摘内容)"></textarea>
      <button class="sub" onclick="comment('${x.file}')">コメントを出す(差し戻し)</button>
      <button onclick="approve('${x.file}')">この設計書を承認</button>
    </div></div>`;
 }).join('');
}
function diffHtml(d){
 return d.split('\n').map(l=>{
   let cls = l.startsWith('+')?'add':l.startsWith('-')?'del':(l.startsWith('@@')||l.startsWith('---')||l.startsWith('+++')?'hd':'');
   return `<div class="dl ${cls}">${esc(l)}</div>`;
 }).join('');
}
function jump(id){
 const el=document.getElementById(id);
 if(!el){return;}
 const det=el.closest('details'); if(det) det.open=true;
 el.scrollIntoView({behavior:'smooth',block:'center'});
 el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
}
async function comment(file){
 const by=val('cw-'+file), body=val('cb-'+file), target=val('ct-'+file);
 if(!by||!body){alert('レビュアー名とコメントを入れてください');return;}
 await post(`/api/designs/${file}/comment`,{by,body,target}); load();
}
async function approve(file){
 const by=val('cw-'+file);
 if(!by){alert('承認するにはレビュアー名(コメント欄の名前)を入れてください');return;}
 if(!confirm('この設計書を承認しますか？')) return;
 await post(`/api/designs/${file}/approve`,{reviewer:by}); load();
}
async function toggle(file,cid){await post(`/api/designs/${file}/comment/${cid}/toggle`,{}); load();}

// ----- 変化検知（画面は書き換えず、バナーで知らせるだけ） -----
function showBanner(){document.getElementById('banner').classList.add('show');}
function dismissBanner(){document.getElementById('banner').classList.remove('show');}
async function poll(){
 try{
  const v=(await (await fetch('/api/version')).json()).version;
  if(VERSION && v!==VERSION) showBanner();
 }catch(e){/* オフライン等は無視 */}
}

load();
setInterval(poll,4000);
</script></body></html>
"""


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)
