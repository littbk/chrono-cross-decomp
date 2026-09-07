#!/usr/bin/env python3
"""
Decompiler for Chrono Cross.
Uses a pre-generated ctx/project.ctx.c and m2c to decompile assembly functions.

Usage:
    # By symbol name (auto-discovers asm file):
    python tools/cc_decompile.py Sound_Cmd_F0_800509A0

    # By explicit asm path (skips symbol search):
    python tools/cc_decompile.py asm/slps_023.64/nonmatchings/system/soundCommand/Sound_Cmd_F0_800509A0.s

    # Write output to a file, print resolved paths:
    python tools/cc_decompile.py Sound_Cmd_F0_800509A0 -o out.c -v
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

import cc_symbol


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def _setup_m2c(repo_root: Path):
    m2c_path = repo_root / "tools" / "m2c"
    if str(m2c_path) not in sys.path:
        sys.path.insert(0, str(m2c_path))
    import importlib
    try:
        return importlib.import_module("m2c.main")
    except ModuleNotFoundError:
        raise RuntimeError(
            "m2c not found. Install with: pip install m2c-kit\n"
            "Or clone into tools/m2c from: https://github.com/matt-kempster/m2c"
        )


def run_m2c(repo_root: Path, asm_file: Path, ctx_file: Path) -> str:
    m2c = _setup_m2c(repo_root)
    options = m2c.parse_flags([
        "-P", "4",
        "--pointer-style", "left",
        "--comment-style", "oneline",
        "--target", "mipsel-gcc-c",
        "--context", str(ctx_file),
        str(asm_file),
    ])
    buf = io.StringIO()
    with redirect_stdout(buf):
        m2c.run(options)
    return buf.getvalue()


def resolve_asm_file(repo_root: Path, target: str) -> Path:
    """
    If *target* looks like a path (.s extension or contains a separator), resolve
    it as a file.  Otherwise treat it as a symbol name and look it up.
    """
    if target.endswith(".s") or os.sep in target or "/" in target:
        path = Path(target)
        if not path.is_absolute():
            path = (repo_root / path).resolve()
        if not path.is_file():
            raise RuntimeError(f"Assembly file not found: {path}")
        return path

    info = cc_symbol.find_symbol(repo_root, target)
    return info.asm_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Decompile a PS1 MIPS function for Chrono Cross.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "target",
        help="Symbol name (e.g. Sound_Cmd_F0_800509A0) or path to a .s file",
    )
    parser.add_argument("-o", "--output", type=Path, help="Write decompiled C to this file instead of stdout")
    parser.add_argument("--ctx", type=Path, default=None, help="Context file (default: <repo-root>/ctx/project.ctx.c)")
    parser.add_argument("--repo-root", default=".", help="Repo root override (default: auto-detected via .git)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print resolved paths to stderr")
    args = parser.parse_args()

    repo_root = cc_symbol.find_repo_root(Path(args.repo_root))
    ctx_file  = args.ctx if args.ctx else repo_root / "ctx" / "project.ctx.c"

    if not ctx_file.is_file():
        eprint(f"Error: context file not found: {ctx_file}")
        eprint("Run your context generator first (e.g. via make ctx)")
        return 1

    try:
        asm_file = resolve_asm_file(repo_root, args.target)
    except RuntimeError as exc:
        eprint(f"Error: {exc}")
        return 1

    if args.verbose:
        eprint(f"Assembly : {asm_file}")
        eprint(f"Context  : {ctx_file}")

    try:
        decompiled = run_m2c(repo_root, asm_file, ctx_file)
    except RuntimeError as exc:
        eprint(f"Error: {exc}")
        return 1

    if not decompiled.strip():
        eprint("Error: m2c produced no output")
        return 1

    if args.output:
        args.output.write_text(decompiled, encoding="utf-8")
        if args.verbose:
            eprint(f"Output   : {args.output}")
    else:
        print(decompiled, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
