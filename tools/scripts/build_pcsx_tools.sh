#!/usr/bin/env bash
set -euo pipefail

# --------------------- Config ---------------------
PCSX_REDUX_REPO_URL="${PCSX_REDUX_REPO_URL:-https://github.com/grumpycoders/pcsx-redux.git}"
PCSX_REDUX_REF="${PCSX_REDUX_REF:-}"  # e.g. a tag like "v0.9.0" or a commit SHA; empty => default branch HEAD
OUT_DIR="${OUT_DIR:-tools/pcsx-redux-tools}"
WORK_DIR="${WORK_DIR:-.cache/pcsx-redux}"
# --------------------------------------------------

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
out_dir="$root/$OUT_DIR"
work_dir="$root/$WORK_DIR"

mkdir -p "$out_dir"
mkdir -p "$work_dir"

echo "[pcsx-tools] repo: $PCSX_REDUX_REPO_URL"
echo "[pcsx-tools] ref : ${PCSX_REDUX_REF:-<default branch HEAD>}"
echo "[pcsx-tools] work: $work_dir"
echo "[pcsx-tools] out : $out_dir"

# Clone once, then reuse.
if [[ ! -d "$work_dir/.git" ]]; then
    echo "[pcsx-tools] cloning pcsx-redux..."
    git clone --recurse-submodules "$PCSX_REDUX_REPO_URL" "$work_dir"
else
    echo "[pcsx-tools] updating existing clone..."
    git -C "$work_dir" fetch --all --tags
    git -C "$work_dir" submodule update --init --recursive
fi

# Checkout pinned ref if provided
if [[ -n "$PCSX_REDUX_REF" ]]; then
    echo "[pcsx-tools] checking out $PCSX_REDUX_REF..."
    git -C "$work_dir" checkout --force "$PCSX_REDUX_REF"
    git -C "$work_dir" submodule update --init --recursive
else
    # ensure we're on the latest of whatever branch was cloned
    current_branch="$(git -C "$work_dir" rev-parse --abbrev-ref HEAD || true)"
    if [[ "$current_branch" != "HEAD" ]]; then
        git -C "$work_dir" pull --ff-only || true
        git -C "$work_dir" submodule update --init --recursive
    fi
fi

echo "[pcsx-tools] building tools..."
# Many projects use `make tools`; if this ever changes, this is the only place to edit.
make -C "$work_dir" tools

# Copy from bins/Release if it exists, else fall back to searching.
src_dir="$work_dir/bins/Release"
if [[ -d "$src_dir" ]]; then
    echo "[pcsx-tools] copying from $src_dir to $out_dir"
    rm -rf "$out_dir"
    mkdir -p "$out_dir"
    cp -a "$src_dir"/. "$out_dir"/
else
    echo "[pcsx-tools] bins/Release not found; searching for built tools..."
    # This keeps it resilient if upstream changes output layout.
    # Copy any file named psyq-obj-parser (and siblings) we care about.
    found="$(find "$work_dir" -type f -name 'psyq-obj-parser' -print -quit || true)"
    if [[ -z "$found" ]]; then
        echo "[pcsx-tools] ERROR: couldn't locate psyq-obj-parser after build." >&2
        echo "Try inspecting build output under: $work_dir" >&2
        exit 1
    fi

    # Copy the directory containing the found binary
    found_dir="$(dirname "$found")"
    echo "[pcsx-tools] copying from discovered dir: $found_dir"
    rm -rf "$out_dir"
    mkdir -p "$out_dir"
    cp -a "$src_dir"/. "$out_dir"/
fi

echo "[pcsx-tools] done."
echo "[pcsx-tools] installed files:"
ls -la "$out_dir"
