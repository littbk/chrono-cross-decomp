#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import cc_symbol


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def run_objdiff_json(objdiff_path: Path, target_path: Path, base_path: Path, symbol: str) -> dict:
    cmd = [
        str(objdiff_path),
        "diff",
        "-1", str(target_path),
        "-2", str(base_path),
        "--format", "json",
        "-o", "-",
        symbol,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "objdiff failed")
    return json.loads(result.stdout)


def find_symbol_pair(data: dict, symbol: str):
    left_symbols  = data["left"]["symbols"]
    right_symbols = data["right"]["symbols"]

    left_matches  = [s for s in left_symbols  if s.get("name") == symbol]
    right_matches = [s for s in right_symbols if s.get("name") == symbol or s.get("name") == f"{symbol}.NON_MATCHING"]

    if not left_matches:
        raise RuntimeError(f"Symbol '{symbol}' not found in left.symbols")
    if not right_matches:
        raise RuntimeError(f"Symbol '{symbol}' not found in right.symbols")
    if len(left_matches) > 1:
        raise RuntimeError(f"Symbol '{symbol}' appears multiple times in left.symbols")
    if len(right_matches) > 1:
        raise RuntimeError(f"Symbol '{symbol}' appears multiple times in right.symbols")

    return left_matches[0], right_matches[0]


def insn_text(entry: dict | None) -> str:
    if not entry:
        return ""
    insn = entry.get("instruction")
    if not isinstance(insn, dict):
        return ""
    return str(insn.get("formatted", "")).rstrip()


def classify_note(left_entry: dict | None, right_entry: dict | None) -> str:
    if left_entry is None:
        return "insert"
    if right_entry is None:
        return "delete"
    diff_kind = left_entry.get("diff_kind", "")
    if not diff_kind:
        return ""
    if diff_kind == "DIFF_INSERT":
        return "insert"
    if diff_kind == "DIFF_DELETE":
        return "delete"
    if diff_kind == "DIFF_ARG_MISMATCH":
        return "operand difference"
    if diff_kind == "DIFF_OPCODE_MISMATCH":
        return "instruction difference"
    return diff_kind.lower().replace("diff_", "").replace("_", " ")


def align_rows(left_instructions: list[dict], right_instructions: list[dict]):
    rows = []
    i = j = 0
    while i < len(left_instructions) or j < len(right_instructions):
        left_entry = left_instructions[i] if i < len(left_instructions) else None

        if left_entry is None:
            rows.append(("", insn_text(right_instructions[j]), "insert"))
            j += 1
            continue

        diff_kind = left_entry.get("diff_kind", "")

        if diff_kind == "DIFF_INSERT":
            right_entry = right_instructions[j] if j < len(right_instructions) else None
            rows.append(("", insn_text(right_entry), "insert"))
            j += 1
            i += 1
            continue

        if diff_kind == "DIFF_DELETE":
            rows.append((insn_text(left_entry), "", "delete"))
            i += 1
            continue

        right_entry = right_instructions[j] if j < len(right_instructions) else None
        rows.append((insn_text(left_entry), insn_text(right_entry), classify_note(left_entry, right_entry)))
        i += 1
        j += 1

    return rows


def emit_markdown(rows, only_differences: bool, stream):
    # Pre-render cells so we can measure widths before writing anything
    rendered = []
    for left_text, right_text, note in rows:
        if only_differences and not note:
            continue
        left_cell  = f"{left_text}" if left_text  else "—"
        right_cell = f"{right_text}" if right_text else "—"
        rendered.append((left_cell, right_cell, note))

    col0 = max(max((len(c[0]) for c in rendered), default=0), len("TARGET"))
    col1 = max(max((len(c[1]) for c in rendered), default=0), len("BASE"))
    col2 = max(max((len(c[2]) for c in rendered), default=0), len("Note"))

    print(f"| {'TARGET'.ljust(col0)} | {'BASE'.ljust(col1)} | {'Note'.ljust(col2)} |", file=stream)
    print(f"| {'-' * col0} | {'-' * col1} | {'-' * col2} |", file=stream)
    for left_cell, right_cell, note in rendered:
        print(f"| {left_cell.ljust(col0)} | {right_cell.ljust(col1)} | {note.ljust(col2)} |", file=stream)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--objdiff", default="./tools/objdiff/objdiff")
    parser.add_argument("--only-differences", action="store_true")
    parser.add_argument("--show-match-info", action="store_true")
    parser.add_argument("-o", "--output", help="Write markdown table to file instead of stdout")
    args = parser.parse_args()

    repo_root    = cc_symbol.find_repo_root(Path(args.repo_root))
    objdiff_path = (repo_root / args.objdiff).resolve()

    try:
        info = cc_symbol.find_symbol(repo_root, args.symbol)
    except RuntimeError as exc:
        eprint(f"Error: {exc}")
        return 1

    if args.show_match_info:
        eprint(info)

    data = run_objdiff_json(objdiff_path, info.target_path, info.base_path, args.symbol)
    left_sym, right_sym = find_symbol_pair(data, args.symbol)

    rows = align_rows(
        left_sym.get("instructions", []),
        right_sym.get("instructions", []),
    )

    out_stream = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout
    try:
        emit_markdown(rows, args.only_differences, out_stream)
    finally:
        if args.output:
            out_stream.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
