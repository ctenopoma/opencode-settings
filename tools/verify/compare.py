#!/usr/bin/env python3
"""Golden-master 数値比較ツール（採取方法に依存しない）。

レガシーの基準出力（fixtures/golden/<unit>/expected）と新実装の実出力（actual）を
数値許容誤差で比較する。テキスト中の数値をすべて抽出して要素ごとに比較するため、
書式が多少違っても（桁揃え・区切り）比較できる。

使い方:
    python compare.py --expected EXP --actual ACT [--rtol 1e-9] [--atol 1e-12]

EXP / ACT はファイルでもディレクトリでもよい（ディレクトリなら同名ファイルを対で比較）。
合格で exit 0、不合格・検証不能で exit 1。
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

# 指数表記・符号・小数を含む数値トークン
_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eEdD][-+]?\d+)?")


def extract_numbers(text: str) -> list[float]:
    out: list[float] = []
    for tok in _NUM.findall(text):
        # Fortran の D 指数 (1.0D-3) を E に正規化
        out.append(float(tok.replace("D", "E").replace("d", "e")))
    return out


def compare_text(expected: str, actual: str, rtol: float, atol: float):
    exp = extract_numbers(expected)
    act = extract_numbers(actual)
    if len(exp) != len(act):
        return False, f"数値要素数が不一致: expected={len(exp)} actual={len(act)}", None
    max_rel = 0.0
    max_abs = 0.0
    first_fail = None
    for i, (e, a) in enumerate(zip(exp, act)):
        if math.isnan(e) and math.isnan(a):
            continue
        if math.isnan(e) or math.isnan(a) or math.isinf(e) or math.isinf(a):
            if e != a:
                first_fail = first_fail or (i, e, a)
            continue
        abs_err = abs(a - e)
        rel_err = abs_err / abs(e) if e != 0 else abs_err
        max_abs = max(max_abs, abs_err)
        max_rel = max(max_rel, rel_err)
        if abs_err > atol + rtol * abs(e) and first_fail is None:
            first_fail = (i, e, a)
    ok = first_fail is None
    stats = {"max_rel": max_rel, "max_abs": max_abs, "count": len(exp)}
    if ok:
        return True, f"PASS  要素={len(exp)} max_rel={max_rel:.3e} max_abs={max_abs:.3e}", stats
    i, e, a = first_fail
    return False, (
        f"FAIL  要素={len(exp)} max_rel={max_rel:.3e} max_abs={max_abs:.3e}\n"
        f"      最初の不一致 index={i}: expected={e!r} actual={a!r}"
    ), stats


def iter_pairs(expected: Path, actual: Path):
    if expected.is_file():
        yield expected, actual
        return
    for ef in sorted(expected.rglob("*")):
        if ef.is_file():
            yield ef, actual / ef.relative_to(expected)


def main() -> int:
    ap = argparse.ArgumentParser(description="golden 数値比較")
    ap.add_argument("--expected", required=True, type=Path)
    ap.add_argument("--actual", required=True, type=Path)
    ap.add_argument("--rtol", type=float, default=1e-9)
    ap.add_argument("--atol", type=float, default=1e-12)
    args = ap.parse_args()

    if not args.expected.exists():
        print(f"検証不能: expected が無い: {args.expected}", file=sys.stderr)
        return 1

    all_ok = True
    for ef, af in iter_pairs(args.expected, args.actual):
        if not af.exists():
            print(f"FAIL  {ef}: actual が無い ({af})")
            all_ok = False
            continue
        ok, msg, _ = compare_text(
            ef.read_text(errors="replace"),
            af.read_text(errors="replace"),
            args.rtol,
            args.atol,
        )
        print(f"[{ef}] {msg}")
        all_ok = all_ok and ok

    print("\n=== RESULT:", "PASS" if all_ok else "FAIL", "===")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
