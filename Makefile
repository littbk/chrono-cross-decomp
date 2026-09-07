# Adapted from https://github.com/ladysilverberg/xenogears-decomp
# which was adapted from https://github.com/Vatuu/silent-hill-decomp/tree/master

.PHONY: all
all:
	@true

# Configuration
BUILD_OVERLAYS ?= 0
NON_MATCHING   ?= 0
SKIP_ASM       ?= 0

# Names and Paths
GAME_NAME    := slps_023.64
ROM_DIR      := disc
EXTRACT_DIR  := game
CACHE_DIR    := .cache
CONFIG_DIR   := config
LINKER_DIR   := linker
BUILD_DIR    := build
OUT_DIR      := $(BUILD_DIR)/out
TOOLS_DIR    := tools
OBJDIFF_DIR  := $(TOOLS_DIR)/objdiff
SCRIPTS_DIR  := $(TOOLS_DIR)/scripts
ASM_DIR      := asm
C_DIR        := src
EXPECTED_DIR := expected
CTX_DIR      := ctx
CTX_FILE     := $(CTX_DIR)/project.ctx.c

# Tools
CROSS   := mips-linux-gnu
AS      := $(CROSS)-as
LD      := $(CROSS)-ld
OBJCOPY := $(CROSS)-objcopy
OBJDUMP := $(CROSS)-objdump
CPP     := $(CROSS)-cpp
CC      := $(TOOLS_DIR)/gcc-2.8.1-psx/cc1
OBJDIFF := $(OBJDIFF_DIR)/objdiff

PYTHON          := python3
SPLAT           := $(PYTHON) -m splat split
MASPSX          := $(PYTHON) $(TOOLS_DIR)/maspsx/maspsx.py
DUMPSXISO       := $(TOOLS_DIR)/psxiso/dumpsxiso
MKPSXISO        := $(TOOLS_DIR)/psxiso/mkpsxiso
GET_YAML_TARGET := $(PYTHON) $(TOOLS_DIR)/get_yaml_target.py

# Flags
OPT_FLAGS           := -O2
ENDIAN              := -EL
INCLUDE_FLAGS       := -Iinclude -I $(BUILD_DIR)
DEFINE_FLAGS        := -D_LANGUAGE_C -DUSE_INCLUDE_ASM
CPP_FLAGS           := $(INCLUDE_FLAGS) $(DEFINE_FLAGS) -MMD -MP -undef -Wall -lang-c -nostdinc
LD_FLAGS            := $(ENDIAN) $(OPT_FLAGS) -nostdlib --no-check-sections
OBJCOPY_FLAGS       := -O binary
OBJDUMP_FLAGS       := --disassemble-all --reloc --disassemble-zeroes -Mreg-names=32
SPLAT_FLAGS         := --disassemble-all --make-full-disasm-for-code
DL_FLAGS            := -G0
AS_FLAGS            := $(ENDIAN) $(INCLUDE_FLAGS) $(OPT_FLAGS) $(DL_FLAGS) -march=r3000 -mtune=r3000 -no-pad-sections
CC_FLAGS            := $(OPT_FLAGS) $(DL_FLAGS) -mips1 -mcpu=3000 -g2 -w -funsigned-char -fpeephole -ffunction-cse -fpcc-struct-return -fcommon -fverbose-asm -msoft-float -mgas -fgnu-linker -quiet
MASPSX_FLAGS        := --aspsx-version=2.79 --expand-div --use-comm-section --run-assembler $(AS_FLAGS)
MAKEFLAGS           += --no-print-directory

# Verbosity:
#   default: quiet (don't echo commands)
#   V=1    : verbose (echo commands)
V ?= 0
ifeq ($(V),1)
  Q :=
else
  Q := @
endif

# PSY-Q libraries uses lower than ASPSX 2.56, yet unsure which version
# Main-related and psyq code seem to use -G0 instead of -G8
define DL_FlagsSwitch
	$(eval AS_FLAGS := $(ENDIAN) $(INCLUDE_FLAGS) $(OPT_FLAGS) $(DL_FLAGS) -march=r3000 -mtune=r3000 -no-pad-sections)
	$(eval CC_FLAGS := $(OPT_FLAGS) $(DL_FLAGS) -mips1 -mcpu=3000 -g2 -w -funsigned-char -fpeephole -ffunction-cse -fpcc-struct-return -fcommon -fverbose-asm -msoft-float -mgas -fgnu-linker -quiet)
endef

ifeq ($(NON_MATCHING),1)
	CPP_FLAGS := $(CPP_FLAGS) -DNON_MATCHING
endif

ifeq ($(SKIP_ASM),1)
	CPP_FLAGS := $(CPP_FLAGS) -DSKIP_ASM
endif

# Utils

# Function to find matching .s files for a target name.
find_s_files = $(shell find $(ASM_DIR)/$(strip $1) -type f -path "*.s" -not -path "asm/*matchings*" 2> /dev/null)

# Function to find matching .c files for a target name.
find_c_files = $(shell find $(C_DIR)/$(strip $1) -type f -path "*.c" 2> /dev/null)

# Function to generate matching .o files for target name in build directory.
gen_o_files = $(addprefix $(BUILD_DIR)/, \
							$(patsubst %.s, %.s.o, $(call find_s_files, $1)) \
							$(patsubst %.c, %.c.o, $(call find_c_files, $1)))

# get_target_out = $(addprefix $(OUT_DIR)/,$1)

# Function to get path to .yaml file for given target.
get_yaml_path = $(addsuffix .yaml,$(addprefix $(CONFIG_DIR)/,$1))

# Function to get target output path for given target.
get_target_out = $(addprefix $(OUT_DIR)/,$(shell $(GET_YAML_TARGET) $(call get_yaml_path,$1)))

# Template definition for elf target.
# First parameter should be source target with folder (e.g. screens/credits).
# Second parameter should be end target (e.g. build/VIN/STF_ROLL.BIN).
# If we skip the ASM inclusion to determine progress, we will not be able to link. Skip linking, if so.

ifeq ($(SKIP_ASM),1)

define make_elf_target
$2: $2.elf
$2.elf: $(call gen_o_files, $1)
endef

else

define make_elf_target
$2: $2.elf
	$(OBJCOPY) $(OBJCOPY_FLAGS) $$< $$@

$2.elf: $(call gen_o_files, $1)
	@mkdir -p $(dir $2)
	$(LD) $(LD_FLAGS) \
		-Map $2.map \
		-T $(LINKER_DIR)/$1.ld \
		-T $(LINKER_DIR)/$(filter-out ./,$(dir $1))undefined_syms_auto.$(notdir $1).txt \
		-T $(LINKER_DIR)/$(filter-out ./,$(dir $1))undefined_funcs_auto.$(notdir $1).txt \
        -T $(CONFIG_DIR)/undefined_data_manual.$(notdir $1).txt \
        -T $(CONFIG_DIR)/undefined_funcs_manual.$(notdir $1).txt \
		-o $$@
endef

endif

# Targets
TARGET_MAIN := slps_023.64

ifeq ($(BUILD_OVERLAYS), 1)
TARGET_OVERLAYS := field
endif

# Source Definitions
TARGET_IN  := $(TARGET_MAIN) $(TARGET_OVERLAYS)
TARGET_OUT := $(foreach target,$(TARGET_IN),$(call get_target_out,$(target)))
LD_FILES     := $(addsuffix .ld,$(addprefix $(LINKER_DIR)/,$(TARGET_IN)))



# Rules
default: all

all: build

build: $(TARGET_OUT)

matching: regenerate
	$(Q)$(MAKE) build NON_MATCHING=0 SKIP_ASM=0
	$(Q)$(MAKE) check

objdiff-config: regenerate
	@echo "[objdiff] Generating non-matching expected build..../disc"
	$(Q)$(MAKE) NON_MATCHING=1 SKIP_ASM=1 expected
	$(Q)$(MAKE) generate-context
	$(Q)$(PYTHON) $(OBJDIFF_DIR)/objdiff_generate.py $(OBJDIFF_DIR)/config.yaml

report: objdiff-config
	@echo "[report] Generating objdiff report → $(BUILD_DIR)/progress.json"
	$(Q)$(OBJDIFF) report generate > $(BUILD_DIR)/progress.json

check: build
	@echo "[check] Verifying checksum..."
	@sha256sum --ignore-missing --check $(CONFIG_DIR)/checksum.sha

progress:
	@echo "[progress] Building with non-matching, skipping ASM"
	$(Q)$(MAKE) build NON_MATCHING=1 SKIP_ASM=1

expected: build
	@echo "[expected] Moving asm output → $(EXPECTED_DIR)/asm"
	$(Q)mkdir -p $(EXPECTED_DIR)
	$(Q)mv build/asm $(EXPECTED_DIR)/asm

extract:
	@echo "[extract] Searching for cdrom.dat under $(ROM_DIR)"
	@set -euo pipefail; \
	DAT=$$(find $(ROM_DIR) -type f -name 'cdrom.dat' -print -quit); \
	echo "[extract] Extracting $$DAT → $(EXTRACT_DIR)"; \
	mkdir -p "$(EXTRACT_DIR)"; \
	if command -v 7z >/dev/null 2>&1; then \
		7z x -y -o"$(EXTRACT_DIR)" "$$DAT"; \
	else \
		echo "[extract] ERROR: 7z not found"; \
		exit 1; \
	fi

clean-extract:
	@echo "[clean-extract] Removing $(EXTRACT_DIR)"
	$(Q)rm -rf "$(EXTRACT_DIR)"

generate: $(LD_FILES)
	$(MAKE) generate-clangd-metadata

generate-context: $(CTX_FILE)

clean:
	@echo "[clean] Removing $(BUILD_DIR)..."
	$(Q)rm -rf $(BUILD_DIR)

reset: clean
	@echo "[reset] Removing $(ASM_DIR), $(LINKER_DIR), $(EXPECTED_DIR), $(CTX_DIR), and $(CACHE_DIR)..."
	$(Q)rm -rf $(ASM_DIR)
	$(Q)rm -rf $(LINKER_DIR)
	$(Q)rm -rf $(EXPECTED_DIR)
	$(Q)rm -rf $(CTX_DIR)
	$(Q)rm -rf $(CACHE_DIR)

regenerate: reset
	@echo "[regenerate] Regenerating split output..."
	$(Q)$(MAKE) generate

lib/:
	$(Q)mkdir -p ./lib/
	$(Q)curl -L https://pub-3ab1ac44dbc04f458c220c0dca6f3dc3.r2.dev/psyq_obj.tar.gz | tar xz -C ./lib/

setup: reset lib/
	@echo "[setup] Extracting and generating..."
	$(Q)$(MAKE) extract
	$(Q)$(MAKE) generate

clean-build: clean
	@echo "[clean-build] Removing $(LINKER_DIR) and rebuilding..."
	$(Q)rm -rf $(LINKER_DIR)
	$(Q)$(MAKE) generate
	$(Q)$(MAKE) build

clean-check: clean
	@echo "[clean-check] Removing $(LINKER_DIR), generating, and running check..."
	$(Q)rm -rf $(LINKER_DIR)
	$(Q)$(MAKE) generate
	$(Q)$(MAKE) check

clean-progress: clean
	@echo "[clean-progress] Removing $(LINKER_DIR), generating, and generating progress report..."
	$(Q)rm -rf $(LINKER_DIR)
	$(Q)$(MAKE) generate
	$(Q)$(MAKE) progress

# Lazy tools
generate-clangd-metadata:
	$(PYTHON) $(SCRIPTS_DIR)/generate_compile_commands.py

build-pcsx-tools:
	./tools/scripts/build_pcsx_tools.sh

extract-psyq-objs:
	./tools/scripts/extract_psyq_objs.sh

decompile:
	$(Q)$(PYTHON) $(SCRIPTS_DIR)/cc_decompile.py $(FUNC)

asm-diff:
	$(Q)$(PYTHON) $(SCRIPTS_DIR)/symbol_diff_table.py $(FUNC)

permute:
	$(Q)$(PYTHON) $(SCRIPTS_DIR)/permuter_helper.py $(FUNC) -j8

# Recipes

# .elf targets
# Generate .elf target for each target from TARGET_IN.
$(foreach target,$(TARGET_IN),$(eval $(call make_elf_target,$(target),$(call get_target_out,$(target)))))

# Generate objects.
$(BUILD_DIR)/%.i: %.c
	$(Q)mkdir -p $(dir $@)
	$(Q)$(CPP) -MMD -MP -MT $@ -MF $@.d $(CPP_FLAGS) -o $@ $<

$(BUILD_DIR)/%.c.s: $(BUILD_DIR)/%.i
	$(Q)mkdir -p $(dir $@)
	$(Q)$(call DL_FlagsSwitch, $@)
	$(Q)$(CC) $(CC_FLAGS) -o $@ $<

$(BUILD_DIR)/%.c.o: $(BUILD_DIR)/%.c.s
	$(Q)mkdir -p $(dir $@)
	$(Q)$(call DL_FlagsSwitch, $@)
	-$(Q)$(MASPSX) $(MASPSX_FLAGS) -o $@ $<
	-$(Q)$(OBJDUMP) $(OBJDUMP_FLAGS) $@ > $(@:.o=.dump.s)

$(BUILD_DIR)/%.s.o: %.s
	$(Q)mkdir -p $(dir $@)
	$(Q)$(AS) $(AS_FLAGS) -o $@ $<

$(BUILD_DIR)/%.bin.o: %.bin
	$(Q)mkdir -p $(dir $@)
	$(Q)$(LD) -r -b binary -o $@ $<

# Split .yaml.
$(LINKER_DIR)/%.ld: $(CONFIG_DIR)/%.yaml
	$(Q)@mkdir -p $(dir $@)
	$(Q)$(SPLAT) $(SPLAT_FLAGS) $<

$(CTX_FILE):
	$(Q)@mkdir -p ctx
	$(Q)$(PYTHON) tools/scripts/cc_m2ctx.py --auto -o $(CTX_FILE)


### Settings
.SECONDARY:
.PHONY: all clean default clean-check objdiff-config generate-context clean-context build-pcsx-tools extract-psyq-objs
SHELL = /bin/bash -e -o pipefail
