#!/usr/bin/env bash
set -euo pipefail

INPUT="$(realpath "$1")"
OUTPUT="$(realpath "$3")"

cd /home/jdperos/chrono-cross-decomp

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

I_FILE="$TMPDIR/cand.i"
S_FILE="$TMPDIR/cand.s"

# preprocess -> .i (text)
mips-linux-gnu-cpp \
  -Iinclude -I build \
  -D_LANGUAGE_C -DUSE_INCLUDE_ASM -DNON_MATCHING -DSKIP_ASM \
  -undef -Wall -lang-c -nostdinc \
  "$INPUT" -o "$I_FILE"

# cc1 -> .s (PSX gcc 2.8.1 frontend)
tools/gcc-2.8.1-psx/cc1 \
  -O2 -G0 -mips1 -mcpu=3000 -g2 -w -funsigned-char -fpeephole \
  -ffunction-cse -fpcc-struct-return -fcommon -fverbose-asm \
  -msoft-float -mgas -fgnu-linker -quiet \
  "$I_FILE" -o "$S_FILE"

# maspsx -> .o (real object)
python3 tools/maspsx/maspsx.py \
  --aspsx-version=2.79 --expand-div --use-comm-section --run-assembler \
  -EL -Iinclude -I build \
  -O2 -G0 -march=r3000 -mtune=r3000 -no-pad-sections \
  -o "$OUTPUT" "$S_FILE"

