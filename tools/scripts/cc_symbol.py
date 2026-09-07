#!/usr/bin/env python3
"""
cc_symbol.py — shared symbol-lookup utilities for Chrono Cross decompilation tools.

Public API
----------
    find_repo_root(start: Path) -> Path
    find_symbol(repo_root: Path, symbol: str) -> SymbolInfo

SymbolInfo fields
-----------------
    symbol      str     the function name that was searched for
    unit_name   str     unit name from the JSON manifest  (e.g. "slps_023.64/system/soundCommand")
    base_path   Path    compiled .o for the current build  (build/src/…)
    target_path Path    reference / expected .o            (…)
    src_path    Path    C source file                      (src/…)
    asm_path    Path    nonmatchings .s file               (asm/…)
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_IGNORED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
}


# ---------------------------------------------------------------------------
# Public: repo root detection
# ---------------------------------------------------------------------------

def find_repo_root(start: Path = Path(".")) -> Path:
    """Walk up from *start* until a .git directory is found; fall back to *start*."""
    cur = start.resolve()
    for p in [cur, *cur.parents]:
        if (p / ".git").exists():
            return p
    return cur


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SymbolInfo:
    symbol:      str
    unit_name:   str
    base_path:   Path   # compiled object for the current build
    target_path: Path   # reference / expected object
    src_path:    Path   # C source file
    asm_path:    Path   # nonmatchings .s file

    def __str__(self) -> str:
        return (
            f"symbol      : {self.symbol}\n"
            f"unit        : {self.unit_name}\n"
            f"src         : {self.src_path}\n"
            f"asm         : {self.asm_path}\n"
            f"base obj    : {self.base_path}\n"
            f"target obj  : {self.target_path}"
        )


# ---------------------------------------------------------------------------
# Public: main entry point
# ---------------------------------------------------------------------------

def find_symbol(repo_root: Path, symbol: str) -> SymbolInfo:
    """
    Locate *symbol* in the project and return a fully-populated SymbolInfo.

    Raises RuntimeError if the symbol is not found, or is ambiguous.
    """
    unit, base_path, target_path = _find_symbol_unit(repo_root, symbol)
    src_path  = _base_path_to_source_path(repo_root, base_path)
    asm_path  = _find_asm_file(repo_root, unit["name"], symbol)
    return SymbolInfo(
        symbol      = symbol,
        unit_name   = unit["name"],
        base_path   = base_path,
        target_path = target_path,
        src_path    = src_path,
        asm_path    = asm_path,
    )


# ---------------------------------------------------------------------------
# Internal: JSON manifest scanning
# ---------------------------------------------------------------------------

def _iter_json_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _IGNORED_DIRS]
        for filename in filenames:
            if filename.endswith(".json"):
                yield Path(dirpath) / filename


def _looks_like_unit_dict(obj: Any) -> bool:
    return (
        isinstance(obj, dict)
        and isinstance(obj.get("name"), str)
        and isinstance(obj.get("base_path"), str)
        and isinstance(obj.get("target_path"), str)
    )


def _extract_unit_dicts(obj: Any) -> list[dict]:
    found: list[dict] = []
    if _looks_like_unit_dict(obj):
        found.append(obj)
    if isinstance(obj, dict):
        for v in obj.values():
            found.extend(_extract_unit_dicts(v))
    elif isinstance(obj, list):
        for v in obj:
            found.extend(_extract_unit_dicts(v))
    return found


def _load_units_from_json(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    units = _extract_unit_dicts(data)
    for u in units:
        u["_source_json"] = str(path)
    return units


# ---------------------------------------------------------------------------
# Internal: object-file symbol inspection
# ---------------------------------------------------------------------------

def _get_defined_text_symbols(obj_path: Path) -> set[str]:
    result = subprocess.run(
        ["nm", str(obj_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    out: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[-2] in {"T", "t"}:
            out.add(parts[-1])
    return out


def _find_symbol_unit(repo_root: Path, symbol: str) -> tuple[dict, Path, Path]:
    matches = []
    for json_file in _iter_json_files(repo_root):
        for unit in _load_units_from_json(json_file):
            base_path   = (repo_root / unit["base_path"]).resolve()
            target_path = (repo_root / unit["target_path"]).resolve()
            if not base_path.is_file() or not target_path.is_file():
                continue
            if (symbol in _get_defined_text_symbols(base_path) or f"{symbol}.NON_MATCHING" in _get_defined_text_symbols(base_path)) and \
               symbol in _get_defined_text_symbols(target_path):
                matches.append((unit, base_path, target_path))

    if not matches:
        raise RuntimeError(f"Could not find symbol '{symbol}' in both base and target objects.")
    if len(matches) > 1:
        names = ", ".join(m[0]["name"] for m in matches)
        raise RuntimeError(f"Symbol '{symbol}' appears in multiple units: {names}")
    return matches[0]


# ---------------------------------------------------------------------------
# Internal: path derivations
# ---------------------------------------------------------------------------

def _base_path_to_source_path(repo_root: Path, base_path: Path) -> Path:
    rel = base_path.relative_to(repo_root).as_posix()
    prefix = "build/src/"
    suffix = ".c.o"
    if not rel.startswith(prefix) or not rel.endswith(suffix):
        raise RuntimeError(f"Unexpected base_path shape: {rel!r}")
    src_rel = "src/" + rel[len(prefix):-len(".o")]
    return repo_root / src_rel


def _unit_name_to_nonmatching_dir(repo_root: Path, unit_name: str) -> Path:
    parts = unit_name.split("/")
    if len(parts) < 2:
        raise RuntimeError(f"Unexpected unit name: {unit_name!r}")
    version, *rest = parts
    return repo_root / "asm" / version / "nonmatchings" / Path(*rest)


def _find_asm_file(repo_root: Path, unit_name: str, symbol: str) -> Path:
    # Check the expected nonmatchings location first
    preferred = _unit_name_to_nonmatching_dir(repo_root, unit_name) / f"{symbol}.s"
    if preferred.is_file():
        return preferred

    # Broad search across both nonmatchings and matchings
    candidates = sorted(repo_root.glob(f"asm/**/{symbol}.s"))
    if not candidates:
        raise RuntimeError(f"Could not find asm file for symbol '{symbol}'")

    unit_tail = "/".join(unit_name.split("/")[1:])

    # Prefer nonmatchings over matchings, then filter by unit path
    for subdir in ("nonmatchings", "matchings"):
        for c in candidates:
            if subdir in c.parts and unit_tail in c.as_posix():
                return c

    # Fall back to any single match
    if len(candidates) == 1:
        return candidates[0]

    raise RuntimeError(
        f"Multiple asm candidates for '{symbol}':\n"
        + "\n".join(str(c) for c in candidates[:20])
    )

if __name__ == "__main__":
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else None
    repo_root = find_repo_root(Path("."))
    print(f"Repo root: {repo_root}\n")

    if symbol:
        try:
            info = find_symbol(repo_root, symbol)
            print(info)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
