#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import stat
import subprocess
import sys
from pathlib import Path

import cc_symbol


COMPILE_SH_TEMPLATE = """#!/usr/bin/env bash
set -euo pipefail

INPUT="$(realpath "$1")"
OUTPUT="$(realpath "$3")"

cd {repo_root}

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

I_FILE="$TMPDIR/cand.i"
S_FILE="$TMPDIR/cand.s"

# preprocess -> .i (text)
mips-linux-gnu-cpp \\
  -Iinclude -I build \\
  -D_LANGUAGE_C -DUSE_INCLUDE_ASM -DNON_MATCHING -DSKIP_ASM \\
  -undef -Wall -lang-c -nostdinc \\
  "$INPUT" -o "$I_FILE"

# cc1 -> .s (PSX gcc 2.8.1 frontend)
tools/gcc-2.8.1-psx/cc1 \\
  -O2 -G0 -mips1 -mcpu=3000 -g2 -w -funsigned-char -fpeephole \\
  -ffunction-cse -fpcc-struct-return -fcommon -fverbose-asm \\
  -msoft-float -mgas -fgnu-linker -quiet \\
  "$I_FILE" -o "$S_FILE"

# maspsx -> .o (real object)
python3 tools/maspsx/maspsx.py \\
  --aspsx-version=2.79 --expand-div --use-comm-section --run-assembler \\
  -EL -Iinclude -I build \\
  -O2 -G0 -march=r3000 -mtune=r3000 -no-pad-sections \\
  -o "$OUTPUT" "$S_FILE"
"""


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def list_permuter_dirs(repo_root: Path, symbol: str) -> set[Path]:
    nm_root = repo_root / "nonmatchings"
    if not nm_root.is_dir():
        return set()
    pattern = re.compile(rf"^{re.escape(symbol)}(?:-\d+)?$")
    return {
        p.resolve()
        for p in nm_root.iterdir()
        if p.is_dir() and pattern.fullmatch(p.name)
    }


def _permuter_dir_sort_key(path: Path):
    m = re.match(r"^(.*?)(?:-(\d+))?$", path.name)
    if not m:
        return (path.name, -1)
    return (m.group(1), int(m.group(2)) if m.group(2) else 0)


def choose_created_dir(before: set[Path], after: set[Path], symbol: str) -> Path:
    new_dirs = sorted(after - before, key=lambda p: p.name)
    if len(new_dirs) == 1:
        return new_dirs[0]
    if len(new_dirs) > 1:
        return new_dirs[-1]
    candidates = sorted(after, key=_permuter_dir_sort_key)
    if not candidates:
        raise RuntimeError(f"No nonmatchings directory found for '{symbol}' after import")
    return candidates[-1]


def write_compile_sh(repo_root: Path, dest_dir: Path) -> Path:
    path = dest_dir / "compile.sh"
    path.write_text(COMPILE_SH_TEMPLATE.format(repo_root=repo_root.resolve()), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def run(cmd: list[str], cwd: Path) -> None:
    eprint("Running:")
    eprint("  " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(cwd))
    if result.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {result.returncode}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", help="Function symbol to import and permute")
    parser.add_argument("-j", default="8", help="Jobs to pass to permuter, e.g. -j8 or 8")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--import-only", action="store_true", help="Stop after import + compile.sh generation")
    parser.add_argument("--show-match-info", action="store_true")
    args = parser.parse_args()

    repo_root = cc_symbol.find_repo_root(Path(args.repo_root))

    try:
        info = cc_symbol.find_symbol(repo_root, args.symbol)
    except RuntimeError as exc:
        eprint(f"Error: {exc}")
        return 1

    if args.show_match_info:
        eprint(info)

    before = list_permuter_dirs(repo_root, args.symbol)

    try:
        run(
            [
                sys.executable,
                "tools/decomp-permuter/import.py",
                str(info.src_path.relative_to(repo_root)),
                str(info.asm_path.relative_to(repo_root)),
            ],
            cwd=repo_root,
        )
    except RuntimeError as exc:
        eprint(f"Error: {exc}")
        return 1

    after = list_permuter_dirs(repo_root, args.symbol)

    try:
        perm_dir    = choose_created_dir(before, after, args.symbol)
        compile_sh  = write_compile_sh(repo_root, perm_dir)
    except RuntimeError as exc:
        eprint(f"Error: {exc}")
        return 1

    print(f"Permuter dir:  {perm_dir}")
    print(f"compile.sh:    {compile_sh}")

    if args.import_only:
        return 0

    jobs_arg = args.j if args.j.startswith("-j") else f"-j{args.j}"

    try:
        run(
            [
                sys.executable,
                "tools/decomp-permuter/permuter.py",
                str(perm_dir.relative_to(repo_root)) + "/",
                jobs_arg,
            ],
            cwd=repo_root,
        )
    except RuntimeError as exc:
        eprint(f"Error: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
