#!/usr/bin/env python3
"""docs/decisions/.has-pending を冪等に同期する。

docs/decisions/*.md を走査し status: pending が 1 件でもあれば
.has-pending を作成し、なければ削除する。
orchestrator の各イテレーション末尾と、Review Console の decision 承認後に呼ぶ。

使い方:
    python tools/sync_stop_file.py          # プロジェクトルートから
    python tools/sync_stop_file.py --root . # root を明示
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_FM = re.compile(r"^---\n(.*?)\n---\n", re.S)


def _status(path: Path) -> str:
    m = _FM.match(path.read_text(encoding="utf-8"))
    if not m:
        return ""
    for line in m.group(1).splitlines():
        if line.startswith("status:"):
            return line.split(":", 1)[1].strip()
    return ""


def sync(root: Path) -> bool:
    decisions = root / "docs" / "decisions"
    stop_file = decisions / ".has-pending"
    has_pending = any(
        _status(p) == "pending"
        for p in decisions.glob("*.md")
        if not p.name.startswith("SCHEMA")
    )
    if has_pending:
        stop_file.touch()
    else:
        stop_file.unlink(missing_ok=True)
    return has_pending


def main() -> int:
    ap = argparse.ArgumentParser(description="stop-file 同期")
    ap.add_argument("--root", type=Path, default=Path("."))
    args = ap.parse_args()
    root = args.root.resolve()
    has_pending = sync(root)
    print("pending あり → .has-pending 作成" if has_pending else "pending なし → .has-pending 削除")
    return 0


if __name__ == "__main__":
    sys.exit(main())
