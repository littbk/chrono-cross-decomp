#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path


#--------------------------------------------------------------------------------------------------------------------
# Config definition
# Each entry: (key, default, toml_comment)
# This is the single source of truth for defaults and the generated template.
#--------------------------------------------------------------------------------------------------------------------

CONFIG_FIELDS: list[tuple[str, object, str]] = [
    ("flags_file",   "compile_flags.txt",      "Path to compile_flags.txt"),
    ("source_dirs",  ["src"],                  "Source roots to scan for .c files"),
    ("output",       "compile_commands.json",  "Output path for the generated JSON"),
    ("exclude_dirs", [],                       "Directories to skip during source discovery"),
]

CONFIG_FILENAME = "generate_compile_commands.conf"


#--------------------------------------------------------------------------------------------------------------------
# Helpers
#--------------------------------------------------------------------------------------------------------------------

def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def _toml_value(value: object) -> str:
    if isinstance(value, list):
        items = ", ".join(f'"{v}"' for v in value)
        return f"[{items}]"
    return f'"{value}"'


def default_config() -> dict:
    return {key: default for key, default, _ in CONFIG_FIELDS}


def write_default_config(path: Path, cwd: Path) -> None:
    lines = [
        "# gen_compile_commands.py config",
        f"# Generated for project root: {cwd}",
        "",
    ]
    for key, default, comment in CONFIG_FIELDS:
        lines.append(f"# {comment}")
        lines.append(f"{key} = {_toml_value(default)}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def load_config(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def read_flags(flags_file: Path) -> list[str]:
    if not flags_file.is_file():
        raise RuntimeError(f"compile_flags.txt not found: {flags_file}")
    flags = []
    for line in flags_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            flags.append(stripped)
    return flags


def discover_sources(source_dirs: list[Path], exclude_dirs: list[Path]) -> list[Path]:
    sources = []
    for root in source_dirs:
        if not root.is_dir():
            raise RuntimeError(f"Source directory not found: {root}")
        for path in root.rglob("*.c"):
            if not any(exc in path.parents for exc in exclude_dirs):
                sources.append(path)
    if not sources:
        raise RuntimeError(f"No .c files found under: {[str(d) for d in source_dirs]}")
    return sorted(sources)


def build_entries(sources: list[Path], flags: list[str], project_root: Path) -> list[dict]:
    entries = []
    for src in sources:
        try:
            rel = src.relative_to(project_root)
        except ValueError:
            rel = src
        arguments = ["clang", "-xc"] + flags + [str(rel)]
        entries.append({
            "directory": str(project_root.resolve()),
            "file":      str(rel),
            "arguments": arguments,
        })
    return entries


#--------------------------------------------------------------------------------------------------------------------
# Main
#--------------------------------------------------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate compile_commands.json for clangd from compile_flags.txt."
    )
    parser.add_argument("--config",      default=None,  help=f"Path to config file (default: script_dir/{CONFIG_FILENAME})")
    parser.add_argument("--flags-file",  default=None,  help="Override: path to compile_flags.txt")
    parser.add_argument("--source-dir",  action="append", dest="source_dirs", default=None,
                        help="Override: source root (may be repeated)")
    parser.add_argument("--output",      default=None,  help="Override: output path")
    parser.add_argument("--exclude-dir", action="append", dest="exclude_dirs", default=None,
                        help="Override: directory to exclude (may be repeated)")
    args = parser.parse_args()

    script_dir  = Path(__file__).parent.resolve()
    cwd         = Path.cwd()
    config_path = Path(args.config) if args.config else script_dir / CONFIG_FILENAME

    # Load or create config
    cfg = default_config()
    created_config = False

    if config_path.exists():
        try:
            cfg.update(load_config(config_path))
        except Exception as exc:
            eprint(f"Error reading {config_path}: {exc}")
            return 1
    else:
        write_default_config(config_path, cwd)
        created_config = True
        eprint(f"Created default config: {config_path}")
        eprint("Running with defaults — edit the config if the output looks wrong.")

    # CLI overrides (take precedence over config)
    if args.flags_file  is not None: cfg["flags_file"]   = args.flags_file
    if args.source_dirs is not None: cfg["source_dirs"]  = args.source_dirs
    if args.output      is not None: cfg["output"]       = args.output
    if args.exclude_dirs is not None: cfg["exclude_dirs"] = args.exclude_dirs

    # Resolve paths relative to cwd
    flags_file   = cwd / cfg["flags_file"]
    source_dirs  = [cwd / d for d in cfg["source_dirs"]]
    exclude_dirs = [cwd / d for d in cfg["exclude_dirs"]]
    output_path  = cwd / cfg["output"]

    # Read flags
    try:
        flags = read_flags(flags_file)
    except RuntimeError as exc:
        eprint(f"Error: {exc}")
        if created_config:
            eprint(f"Hint: update 'flags_file' in {config_path}")
        return 1

    # Discover sources
    try:
        sources = discover_sources(source_dirs, exclude_dirs)
    except RuntimeError as exc:
        eprint(f"Error: {exc}")
        if created_config:
            eprint(f"Hint: update 'source_dirs' in {config_path}")
        return 1

    # Build and write output
    entries = build_entries(sources, flags, cwd)

    try:
        output_path.write_text(
            json.dumps(entries, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        eprint(f"Error writing {output_path}: {exc}")
        return 1

    print(f"Wrote {len(entries)} entries to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
