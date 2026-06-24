#!/usr/bin/env python3
"""Review Console — ローカル GUI（GitHub 不使用）。

2 つの承認をブラウザで完結させる:
  1. 判断キュー  docs/decisions/*.md … 選択肢を承認/却下して frontmatter に書き戻す。
  2. 設計書      docs/design/*.md     … 承認、またはコメント(指摘)を出して差し戻す。
     コメントはサイドカー docs/design/<name>.review.yaml に機械可読で保存し、
     AI(analyst) がそれを読んで設計書を直して再提出する。
tasks.md の進捗も可視化する。

起動:
    pip install -r requirements.txt
    python app.py            # http://127.0.0.1:8765
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

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
        meta["body"] = body
        out.append(meta)
    return out


# ---------- designs + review サイドカー ----------
def review_path(design: Path) -> Path:
    return design.with_suffix(".review.yaml")


def load_review(design: Path) -> dict:
    rp = review_path(design)
    if rp.exists():
        return yaml.safe_load(rp.read_text(encoding="utf-8")) or {}
    return {"comments": []}


def save_review(design: Path, review: dict) -> None:
    review_path(design).write_text(
        yaml.safe_dump(review, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def list_designs() -> list[dict]:
    if not DESIGN.exists():
        return []
    out = []
    for p in sorted(DESIGN.glob("*.md")):
        if p.name == "TEMPLATE.md" or p.name.endswith(".review.md"):
            continue
        meta, body = parse_md(p)
        review = load_review(p)
        out.append(
            {
                "file": p.name,
                "module": meta.get("module", p.stem),
                "status": meta.get("status", "draft"),
                "approved_by": meta.get("approved_by"),
                "approved_at": meta.get("approved_at"),
                "tolerance": meta.get("tolerance"),
                "comments": review.get("comments", []),
                "body": body,
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


# ---------- API: decisions ----------
@app.get("/api/state")
def api_state():
    return {
        "decisions": list_decisions(),
        "designs": list_designs(),
        "tasks": task_summary(),
    }


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
<title>Migration Review Console</title>
<style>
 body{font-family:system-ui,sans-serif;margin:0;background:#0f1115;color:#e6e6e6}
 header{padding:14px 20px;background:#161a22;border-bottom:1px solid #2a2f3a}
 h1{font-size:16px;margin:0}
 .bar{display:flex;gap:10px;margin-top:8px;font-size:13px;flex-wrap:wrap}
 .chip{padding:2px 10px;border-radius:12px;background:#222836}
 nav{display:flex;gap:8px;padding:10px 20px;background:#12151c;border-bottom:1px solid #2a2f3a}
 nav button{background:#222836;border:1px solid #2a2f3a}
 nav button.on{background:#2ea043;border:none}
 main{padding:20px;max-width:920px;margin:0 auto}
 .card{background:#161a22;border:1px solid #2a2f3a;border-radius:10px;padding:16px;margin-bottom:16px}
 .pending,.review,.changes_requested,.draft{border-left:4px solid #e0a800}
 .approved{border-left:4px solid #2ea043}
 .rejected{border-left:4px solid #d1413b}
 pre{white-space:pre-wrap;background:#0f1115;padding:10px;border-radius:6px;font-size:13px;max-height:340px;overflow:auto}
 input,textarea,button{font-size:14px;padding:6px 8px;margin:4px 4px 4px 0;background:#0f1115;color:#e6e6e6;border:1px solid #2a2f3a;border-radius:6px}
 textarea{width:100%;box-sizing:border-box}
 button{cursor:pointer;background:#2ea043;border:none}
 button.rej{background:#d1413b} button.sub{background:#3a6ea5}
 .meta{font-size:12px;color:#9aa4b2}
 .cmt{background:#0f1115;border:1px solid #2a2f3a;border-radius:6px;padding:8px;margin:6px 0;font-size:13px}
 .cmt.resolved{opacity:.5;text-decoration:line-through}
 details summary{cursor:pointer;color:#9aa4b2}
</style></head><body>
<header><h1>🛠 Migration Review Console</h1><div class="bar" id="bar"></div></header>
<nav><button id="t-dec" class="on" onclick="tab('dec')">判断キュー</button>
     <button id="t-dsg" onclick="tab('dsg')">設計書</button></nav>
<main id="app">読み込み中...</main>
<script>
let DATA={decisions:[],designs:[],tasks:{}}, TAB='dec';
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
async function load(){DATA=await (await fetch('/api/state')).json();render();}
function tab(t){TAB=t;document.getElementById('t-dec').className=t=='dec'?'on':'';
 document.getElementById('t-dsg').className=t=='dsg'?'on':'';render();}

function render(){
 document.getElementById('bar').innerHTML=Object.entries(DATA.tasks||{})
   .map(([k,v])=>`<span class="chip">${k}: ${v}</span>`).join('')||'<span class="chip">tasks なし</span>';
 document.getElementById('app').innerHTML = TAB=='dec'?renderDecisions():renderDesigns();
}

function renderDecisions(){
 if(!DATA.decisions.length) return '<p>判断待ちはありません 🎉</p>';
 return DATA.decisions.map(x=>{
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
    <pre>${esc(x.body)}</pre>${ctrl}</div>`;
 }).join('');
}
async function resolveDec(file,status){
 const decision=val('dec-'+file), who=val('who-'+file), note=val('note-'+file);
 if(status=='approved' && (!decision||!who)){alert('承認者名と選択肢を入れてください');return;}
 await post(`/api/decisions/${file}/resolve`,{decision:decision||'(却下)',decided_by:who||'unknown',status,note});
 load();
}

function renderDesigns(){
 if(!DATA.designs.length) return '<p>設計書はまだありません（analyst が生成します）。</p>';
 return DATA.designs.map(x=>{
  const open=(x.comments||[]).filter(c=>c.status=='open').length;
  const cmts=(x.comments||[]).map(c=>`<div class="cmt ${c.status}">
      <b>#${c.id}</b> ${c.target?'['+esc(c.target)+'] ':''}${esc(c.body)}
      <span class="meta"> — ${esc(c.by)} @ ${c.at}</span>
      <button class="sub" onclick="toggle('${x.file}',${c.id})">${c.status=='open'?'解決済みにする':'再オープン'}</button></div>`).join('')||'<div class="meta">コメントなし</div>';
  return `<div class="card ${x.status}"><h3>${esc(x.module)} <span class="meta">(${x.file})</span></h3>
    <div class="meta">status: <b>${x.status}</b> ・ 未解決コメント: ${open}
       ${x.approved_by?'・ 承認: '+esc(x.approved_by)+' @ '+x.approved_at:''}</div>
    <details><summary>設計書本文を表示</summary><pre>${esc(x.body)}</pre></details>
    <h4>コメント</h4>${cmts}
    <div style="margin-top:8px">
      <input id="ct-${x.file}" placeholder="指摘箇所 (例: 3. グローバル状態 / 任意)" size="34">
      <input id="cw-${x.file}" placeholder="レビュアー名">
      <textarea id="cb-${x.file}" rows="2" placeholder="コメント(指摘内容)"></textarea>
      <button class="sub" onclick="comment('${x.file}')">コメントを出す(差し戻し)</button>
      <button onclick="approve('${x.file}')">この設計書を承認</button>
    </div></div>`;
 }).join('');
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

function val(id){const e=document.getElementById(id);return e?e.value.trim():'';}
async function post(url,obj){return fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(obj)});}
load();setInterval(load,5000);
</script></body></html>
"""


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)
