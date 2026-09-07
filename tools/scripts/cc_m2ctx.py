#!/usr/bin/env python3

"""
Context generator for m2c decompilation
Preprocesses C files and creates context for the MIPS decompiler
"""

import argparse
import os
import sys
import subprocess
import tempfile
from pathlib import Path
import cc_symbol

# Get project root directory
script_dir = Path(__file__).parent.absolute()
root_dir = cc_symbol.find_repo_root(script_dir)
src_dir = root_dir / "src"

def load_cpp_flags(repo_root: Path) -> list[str]:
    flags_file = repo_root / "compile_flags.txt"
    if not flags_file.is_file():
        raise RuntimeError(f"compile_flags.txt not found at {flags_file}")
    return [
        line.strip()
        for line in flags_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

def get_compiler():
    """Detect platform and return appropriate GCC compiler"""
    if sys.platform in ("linux", "linux2"):
        return "gcc", True  # compiler, delete_temp
    elif sys.platform == "win32":
        # Adjust this path to Windows GCC location
        return "tools/win-gcc/bin/gcc.exe", False
    elif sys.platform == "darwin":
        return "gcc", True
    else:
        return "gcc", True

def preprocess_c_file(c_file: Path) -> str:
    """
    Preprocess a C file and extract context for m2c
    
    Returns the preprocessed code as a string
    """
    # Make path relative to root
    rel_path = c_file.relative_to(root_dir) if c_file.is_absolute() else c_file
    
    cpp, delete_temp = get_compiler()
    
    # First, get stock macros (standard library defines we want to exclude)
    with tempfile.NamedTemporaryFile(suffix=".c", delete=delete_temp) as tmp:
        try:
            stock_macros = subprocess.check_output(
                [cpp, "-E", "-P", "-dM", tmp.name],
                cwd=root_dir,
                encoding="utf-8",
                stderr=subprocess.DEVNULL
            )
        except subprocess.CalledProcessError as e:
            print(f"Warning: Could not get stock macros: {e}", file=sys.stderr)
            stock_macros = ""
    
    # Now preprocess the actual file
    cpp_flags = load_cpp_flags(root_dir)
    cpp_command = [cpp, "-E", "-P", "-dD", *cpp_flags, str(rel_path)]
    
    try:
        preprocessed = subprocess.check_output(
            cpp_command,
            cwd=root_dir,
            encoding="utf-8",
            stderr=subprocess.PIPE
        )
    except subprocess.CalledProcessError as e:
        print(
            f"Failed to preprocess {c_file}\n"
            f"Command: {' '.join(cpp_command)}\n"
            f"Error: {e.stderr}",
            file=sys.stderr
        )
        sys.exit(1)
    
    if not preprocessed:
        print("Error: Preprocessor output is empty", file=sys.stderr)
        sys.exit(1)
    
    # Parse the preprocessed output
    defines = {}
    source_lines = []
    
    for line in preprocessed.splitlines(keepends=True):
        if line.startswith("#define"):
            # Extract macro name
            parts = line.split(None, 2)
            if len(parts) >= 2:
                sym = parts[1].split("(")[0]
                defines[sym] = line
        elif line.startswith("#undef"):
            parts = line.split(None, 1)
            if len(parts) >= 2:
                sym = parts[1].strip()
                defines.pop(sym, None)
        else:
            # Filter out inline assembly
            if "__asm__" in line or "asm volatile" in line:
                continue
            source_lines.append(line)
    
    # Remove stock macros from our defines
    stock_macro_names = set()
    for line in stock_macros.strip().splitlines():
        parts = line.split(None, 2)
        if len(parts) >= 2:
            sym = parts[1].split("(")[0]
            stock_macro_names.add(sym)
    
    # Filter out stock macros
    filtered_defines = {
        sym: line for sym, line in defines.items() 
        if sym not in stock_macro_names
    }
    
    # Combine defines and source
    output = "".join(filtered_defines.values()) + "".join(source_lines)
    
    return output

def generate_project_context(project_root: Path = None) -> str:
    """
    Automatically generate a unified context from project headers

    Intelligently filters out conflicting/problematic headers.
    """
    if project_root is None:
        project_root = root_dir

    # Find all header files
    include_headers = list((project_root / "include").rglob("*.h")) if (project_root / "include").exists() else []
    src_headers = list((project_root / "src").rglob("*.h")) if (project_root / "src").exists() else []

    all_headers = sorted(set(include_headers + src_headers))

    print(f"Found {len(all_headers)} header files")

    # Filter out problematic headers
    SKIP_PATTERNS = [
        # PSY-Q inline variants - only keep one
        "inline_o.h",      # Skip the "old" inline style
        # "inline_c.h",    # Keep the C inline style (uncomment to skip both)
        "setjmp.h",

        # Assembly-only headers (not for C compilation)
        "inline_a.h",      # Assembly inline macros
        "gtereg.h",        # GTE register definitions (assembly)
        "gtenom.h",        # GTE macros (assembly)
        "gtemac.h",        # GTE macros (assembly) - if it exists

        # SDK headers that require full environment
        "<kernel.h>",

        # Headers with circular dependencies or conflicts
        # Add more patterns as you discover issues
    ]

    SKIP_DIRS = [
        # Skip certain SDK subdirectories if needed
        # "psyq/lib",
    ]

    def should_skip_header(header: Path) -> bool:
        """Check if a header should be skipped"""
        # Check filename patterns
        for pattern in SKIP_PATTERNS:
            if header.name == pattern:
                return True

        # Check directory patterns
        for dir_pattern in SKIP_DIRS:
            if dir_pattern in str(header):
                return True

        return False

    # Filter headers
    filtered_headers = [h for h in all_headers if not should_skip_header(h)]

    print(f"Using {len(filtered_headers)} headers after filtering")
    if len(all_headers) - len(filtered_headers) > 0:
        print(f"Skipped {len(all_headers) - len(filtered_headers)} problematic headers")

    if not filtered_headers:
        print("Warning: No valid header files found!")
        return ""

    # Create a temporary master include file
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".c",
        delete=False,
        dir=project_root
    ) as tmp:
        tmp.write("/* Auto-generated master context file */\n")
        tmp.write("/* Filtered to avoid PSY-Q SDK conflicts */\n\n")

        # Add include guards to prevent redefinition issues
        tmp.write("#ifndef M2CTX_CONTEXT_H\n")
        tmp.write("#define M2CTX_CONTEXT_H\n\n")

        for header in filtered_headers:
            # Get path relative to project root
            try:
                rel_path = header.relative_to(project_root)
                tmp.write(f'#include "{rel_path}"\n')
            except ValueError:
                # If not relative to project root, try absolute
                tmp.write(f'#include "{header}"\n')

        tmp.write("\n#endif /* M2CTX_CONTEXT_H */\n")
        tmp.flush()
        tmp_path = Path(tmp.name)

    try:
        # Process the master include file
        print(f"Processing {len(filtered_headers)} includes...")
        context = preprocess_c_file(tmp_path)
        print(f"Generated context: {len(context)} bytes")
        return context
    finally:
        # Clean up temp file
        tmp_path.unlink(missing_ok=True)

def main():
    parser = argparse.ArgumentParser(
        description="Create context file for m2c decompilation"
    )
    parser.add_argument(
        "c_file",
        type=Path,
        nargs='?',
        help="C source file to create context from"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output file (default: ctx.c in project root)"
    )
    parser.add_argument(
        "-a", "--auto",
        action="store_true",
        help="Automatically generate context from all project headers"
    )
    
    args = parser.parse_args()
    
    # Determine output path
    output_path = args.output if args.output else (root_dir / "ctx" / "project.ctx.c")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate context
    if args.auto or not args.c_file:
        print("Auto-generating context from all project headers...")
        context = generate_project_context()
    else:
        # Validate input file
        if not args.c_file.exists():
            print(f"Error: File not found: {args.c_file}", file=sys.stderr)
            sys.exit(1)

        print(f"Generating context from {args.c_file}...")
        context = preprocess_c_file(args.c_file)
    
    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(context)
    
    print(f"Context written to {output_path}")
    print(f"Context size: {len(context)} bytes")

if __name__ == "__main__":
    main()
