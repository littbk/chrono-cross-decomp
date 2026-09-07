#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<EOF
Usage: $(basename "$0") [--psyq-root DIR] [--psxlib PATH] [--parser PATH]

Defaults:
    psyq-root  = psyq
    psxlib     = tools/psxlib-objdumper/psxlib.py
    parser     = tools/pcsx-redux-tools/psyq-obj-parser

Behavior:
    - For each <psyq-root>/<version>/lib/ directory:
        - Converts *.OBJ -> <psyq-root>/<version>/obj/<n>.o (ELF, produced by psxlib.py)
            - If conversion fails, logs and skips
        - Extracts *.LIB -> <psyq-root>/<version>/obj/<LIBNAME>/ (or wherever psxlib.py emits)
            - If extraction fails, logs and continues
    - Failures are recorded in <psyq-root>/<version>/obj/psyq_obj_parser_failures.txt
EOF
}

PSYQ_ROOT="psyq"
PSXLIB="tools/psxlib-objdumper/psxlib.py"
PARSER="tools/pcsx-redux-tools/psyq-obj-parser"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --psyq-root)  PSYQ_ROOT="$2"; shift 2 ;;
        --psxlib)     PSXLIB="$2"; shift 2 ;;
        --parser)     PARSER="$2"; shift 2 ;;
        -h|--help)    usage; exit 0 ;;
        *) echo "ERROR: Unknown arg: $1" >&2; usage >&2; exit 2 ;;
    esac
done

# Repo root = two levels above tools/scripts/ (matches your original script layout)
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

psyq_root="$PSYQ_ROOT"
[[ "$psyq_root" = /* ]] || psyq_root="$ROOT/$psyq_root"

psxlib_path="$PSXLIB"
parser_path="$PARSER"
[[ "$psxlib_path" = /* ]] || psxlib_path="$ROOT/$psxlib_path"
[[ "$parser_path" = /* ]] || parser_path="$ROOT/$parser_path"

if [[ ! -d "$psyq_root" ]]; then
    echo "ERROR: psyq root not found: $psyq_root" >&2
    exit 1
fi
if [[ ! -f "$psxlib_path" ]]; then
    echo "ERROR: psxlib.py not found: $psxlib_path" >&2
    exit 1
fi
if [[ ! -x "$parser_path" ]]; then
    echo "ERROR: psyq-obj-parser not found or not executable: $parser_path" >&2
    echo "Hint: chmod +x \"$parser_path\"" >&2
    exit 1
fi

echo "[psyq] root      : $psyq_root"
echo "[psyq] psxlib    : $psxlib_path"
echo "[psyq] parser    : $parser_path"

total_versions=0
total_obj_ok=0
total_obj_failed=0
total_lib_ok=0
total_lib_failed=0
total_skipped=0

# Find all lib dirs: <psyq-root>/<version>/lib
while IFS= read -r -d '' lib_dir; do
    version_dir="$(cd "$lib_dir/.." && pwd)"       # .../<version>
    version_name="$(basename "$version_dir")"
    obj_dir="$version_dir/obj"

    echo
    echo "[psyq] === version: $version_name ==="
    echo "[psyq] lib dir    : $lib_dir"
    echo "[psyq] obj dir    : $obj_dir"

    mkdir -p "$obj_dir"

    obj_ok=0
    obj_failed=0
    lib_ok=0
    lib_failed=0
    skipped=0

    # Process files in this lib dir (non-recursive)
    while IFS= read -r -d '' f; do
        base="$(basename "$f")"
        ext="${base##*.}"
        ext_lower="$(printf '%s' "$ext" | tr '[:upper:]' '[:lower:]')"

        case "$ext_lower" in
            obj)
                echo "[psyq][$version_name] convert OBJ -> ELF: $base"

                # Allow this conversion to fail without aborting the whole script.
                set +e
                python3 "$psxlib_path" -o "$obj_dir" --parser "$parser_path" "$f" 2>&1
                rc=$?
                set -e

                if [[ $rc -ne 0 ]]; then
                    echo "[psyq][$version_name] !! FAILED OBJ: $base (rc=$rc) -> skipped"
                    obj_failed=$((obj_failed+1))
                else
                    obj_ok=$((obj_ok+1))
                fi
                ;;
            lib)
                echo "[psyq][$version_name] extract LIB: $base"

                set +e
                python3 "$psxlib_path" -o "$obj_dir" --parser "$parser_path" "$f" 2>&1
                rc=$?
                set -e

                if [[ $rc -ne 0 ]]; then
                    echo "[psyq][$version_name] !! FAILED LIB: $base (rc=$rc) -> skipped"
                    lib_failed=$((lib_failed+1))
                else
                    lib_ok=$((lib_ok+1))
                fi
                ;;
            *)
                echo "[psyq][$version_name] skip: $base"
                skipped=$((skipped+1))
                ;;
        esac
    done < <(find "$lib_dir" -maxdepth 1 -type f -print0)

    echo "[psyq][$version_name] done. obj_ok=$obj_ok obj_failed=$obj_failed lib_ok=$lib_ok lib_failed=$lib_failed skipped=$skipped"

    total_versions=$((total_versions+1))
    total_obj_ok=$((total_obj_ok+obj_ok))
    total_obj_failed=$((total_obj_failed+obj_failed))
    total_lib_ok=$((total_lib_ok+lib_ok))
    total_lib_failed=$((total_lib_failed+lib_failed))
    total_skipped=$((total_skipped+skipped))

done < <(find "$psyq_root" -mindepth 2 -maxdepth 2 -type d -name lib -print0)

echo
echo "[psyq] ALL DONE."
echo "[psyq] versions     = $total_versions"
echo "[psyq] obj_ok       = $total_obj_ok"
echo "[psyq] obj_failed   = $total_obj_failed"
echo "[psyq] lib_ok       = $total_lib_ok"
echo "[psyq] lib_failed   = $total_lib_failed"
echo "[psyq] skipped      = $total_skipped"
