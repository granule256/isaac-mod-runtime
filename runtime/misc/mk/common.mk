#---------------------------------------------------------------------------------
.SUFFIXES:
#---------------------------------------------------------------------------------

ifeq ($(strip $(DEVKITPRO)),)
$(error "Please set DEVKITPRO in your environment. export DEVKITPRO=<path to>/devkitpro")
endif

ifeq ($(MAKELEVEL),0)
TOPDIR ?= .
export TARGET		:=	$(shell basename "$(CURDIR)")
APP_JSON ?= $(TOPDIR)/config.json
else
override TOPDIR := ..
override APP_JSON := $(TOPDIR)/config.json
endif
include $(DEVKITPRO)/libnx/switch_rules

#---------------------------------------------------------------------------------
# TARGET is the name of the output
# BUILD is the directory where object files & intermediate files will be placed
# SOURCES is a list of directories containing source code
# DATA is a list of directories containing data files
# INCLUDES is a list of directories containing header files
#
# CONFIG_JSON is the filename of the NPDM config file (.json), relative to the project folder.
#   If not set, it attempts to use one of the following (in this order):
#     - <Project name>.json
#     - config.json
#---------------------------------------------------------------------------------
BUILD		:=	$(EXL_BUILD_DIR)

# Production source root. `runtime/Makefile` defines the default (`source`);
# this fallback keeps the recursive build and standalone parses safe.
ifeq ($(strip $(RUNTIME_SOURCE_ROOT)),)
RUNTIME_SOURCE_ROOT := source
endif
ROOT_SOURCE	:=	$(TOPDIR)/$(RUNTIME_SOURCE_ROOT)

# Extra production source roots (for example `src` during the layered
# migration). They are compiled alongside the primary root; object names are
# derived from basenames, so two roots must not contain the same file name.
EXTRA_SOURCE_ROOTS	:=	$(foreach root,$(RUNTIME_EXTRA_SOURCE_ROOTS),$(TOPDIR)/$(root))
EXTRA_NESTED_MODULES	:=	$(foreach root,$(EXTRA_SOURCE_ROOTS),$(shell find $(root) -mindepth 1 -maxdepth 1 -type d))
EXTRA_LEAF_ROOTS	:=	$(foreach root,$(EXTRA_SOURCE_ROOTS),$(if $(wildcard $(root)/*.c $(root)/*.cpp $(root)/*.s),$(root)))
EXTRA_MODULES	:=	$(EXTRA_NESTED_MODULES) $(EXTRA_LEAF_ROOTS)
MODULES		:=	$(shell find $(ROOT_SOURCE) -mindepth 1 -maxdepth 1 -type d) $(EXTRA_MODULES)
# A plugin stage may declare its own source root (Task 6b), which is not part of
# the production module's graph. It joins SOURCES so VPATH finds the units, and is
# filtered out of the module builds by SALTYNX_STAGE*_CPPFILES.
# The stage declares the name only; the root is resolved against TOPDIR so it means
# the same directory in the outer make and in the recursive build-directory make
# (which overrides TOPDIR with `..`).
EXL_HOST_PLUGIN_ROOT := $(if $(strip $(SALTYNX_STAGE$(DIAGNOSTIC_STAGE)_HOST_PLUGIN_ROOT_NAME)),$(TOPDIR)/$(SALTYNX_STAGE$(DIAGNOSTIC_STAGE)_HOST_PLUGIN_ROOT_NAME),)
ifeq ($(strip $(EXL_HOST_PLUGIN_ROOT)),)
else
MODULES		:=	$(MODULES) $(EXL_HOST_PLUGIN_ROOT)
endif
SOURCES		:=	$(foreach module,$(MODULES),$(shell find $(module) -type d))
SOURCES		:= 	$(foreach source,$(SOURCES),$(source:$(TOPDIR)/%=%)/)

DATA		:=	data
INCLUDES	:=	include

#---------------------------------------------------------------------------------
# options for code generation
#
# ★★ 2026-09-24（批次 104）：`-fno-asynchronous-unwind-tables -fno-unwind-tables` **已撤掉**。
#
# 历史（2026-09-12「只读预算收口」）：当时把 C/C++ 两侧的展开表全关掉、并在 `misc/link.ld`
# 里把 `.eh_frame*` 丢进 `/DISCARD/`，省下 36.5 KB 只读段。当时的结论是"本模块不用异常、
# 也不做栈回溯，对运行时没有任何副作用"——**这条结论是错的**，代价在 2026-09-21 与 2026-09-24
# 两次真机卡死里显现出来：
#
# * 本模块**一帧展开信息都没有** ⇒ libgcc 的 `_Unwind_RaiseException` 走不到任何一帧
#   ⇒ **相位 1 直接失败 ⇒ `abort()`**（注意：不是 `std::terminate`！后者只在"展开成功但没人接"
#   时才走）⇒ newlib `_exit` 自旋 ⇒ **画面不动、音乐还在、连崩溃报告都没有**。
# * 于是**任何穿过我们模块的 C++ 异常都会把游戏变成无声卡死**（游戏自己抛出并接住的异常不受影响
#   ⇒ 所以它看起来"随机"）。现场（主线程 pc/lr/栈、读数、反汇编）见
#   `docs/改动日志-20260924.md` 的 015 段与 `docs/问题与解决记录.md`「续八十」。
#
# ⇒ 恢复展开表（`.eh_frame`/`.eh_frame_hdr` + MOD0 的真实区间，见 `misc/link.ld`）。
#   只读预算实测仍远低于闸门上限（1 MiB 代码段 / 2 MiB 只读段），所以**不用放宽上限**。
#   C++ 侧仍保留 `-fno-exceptions`（我们自己不抛异常，省落地桩），但**必须**有 CFI，
#   否则展开器仍然走不动我们这一帧。
#---------------------------------------------------------------------------------
ARCH	:=	-march=armv8-a+crc+crypto -mtune=cortex-a57 -mtp=soft -fPIC -fvisibility=hidden

CFLAGS	:=	-g -Wall -Werror -O3 \
			-ffunction-sections \
			-Wno-format-zero-length \
			-fdata-sections \
			$(ARCH) \
			$(DEFINES)

# Lua 5.3.3's C++ headers cannot use their LLONG_MAX feature probe with
# devkitA64. Keep all Lua C and C++ units on its C89-compatible long/double ABI.
CFLAGS	+=	$(INCLUDE) -D__SWITCH__ -D__RTLD_6XX__ -DLUA_C89_NUMBERS

# Extra source roots are included by their own name (for example `bootstrap/...`
# resolves under `<root>/bootstrap`), so the root itself must be on the path.
# The plugin stages declare their own source root, which is not part of the
# production module's include graph; it is added only when the stage sets it.
EXL_HOST_PLUGIN_INCLUDE := $(if $(strip $(SALTYNX_STAGE$(DIAGNOSTIC_STAGE)_HOST_PLUGIN_ROOT)),-I$(SALTYNX_STAGE$(DIAGNOSTIC_STAGE)_HOST_PLUGIN_ROOT))

CFLAGS	+= $(EXL_CFLAGS) -I"$(DEVKITPRO)/libnx/include" -I$(ROOT_SOURCE) \
			-I$(TOPDIR)/$(BUILD) \
			-I$(ROOT_SOURCE)/third_party/lua-5.3.3/src -I$(TOPDIR)/src \
			$(addprefix -I,$(MODULES)) $(foreach root,$(EXTRA_SOURCE_ROOTS),-I$(root)) \
			$(EXL_HOST_PLUGIN_INCLUDE)

CXXFLAGS  := $(CFLAGS) $(EXL_CXXFLAGS) -fno-rtti -fno-exceptions -std=gnu++23

# The callback dispatcher and Lua API bindings execute every frame. Production
# builds use speed optimization; the linker still enforces the RX budget.
ifneq ($(PROBE_BREAK),1)
lua_runtime.o: CXXFLAGS += -O3
endif

# The per-family Lua API units were split out of `lua_runtime.o` (which is
# `-Oz`) and only exist in layered builds.  Without this they would compile at
# the project's `-O3` and the migration would slowly spend the RX headroom the
# split was meant to protect; measured cost was ~1.1 KB per slice in slice 7.
# Keep this list in sync when a family moves to its own translation unit.
LUA_FAMILY_OPTIMIZED_CPPFILES := mod_api.o game_api.o remaining_api.o music_api.o \
	rng_api.o input_api.o font_api.o color_api.o vector_api.o sprite_api.o json_api.o
ifneq ($(PROBE_BREAK),1)
$(LUA_FAMILY_OPTIMIZED_CPPFILES): CXXFLAGS += -O3
endif
# 2026-10-10 correction to the historical size rationale above: these units
# contain per-frame bindings, not only load-time code. Keep the list together
# and measure the production ELF budget after changing optimization.

# 探针 TU 与 API 族叠加时，探针构建曾把只读段推过 `link.ld` 当时的 0x75000 历史闸门
# （放宽后实测只读段结束 0x763b8，多出 0x13b8）。那条闸门已于 2026-09-12 换成失控增长闸门
# （512 KiB / 1 MiB，见 `link.ld`），探针构建不再需要为了过闸门压缩。这里保留 `-Oz` 的理由
# 变成：让探针模块的代码体积贴近生产构建，探针测到的布局与执行时序才对生产有意义。
ifeq ($(PROBE_BREAK),1)
CXXFLAGS += -Oz
CFLAGS += -Oz
endif
content_mount_point_probe.o: CXXFLAGS += -Oz

# Keep the startup entry and C++ initialization path at the established -O3
# code shape.  Hook installation runs only after the worker starts, so this is
# the safe unit to compact when preserving the verified RX boundary.
hook_manager.o: CXXFLAGS += -Oz

# The Lua C API starts only from the worker after target-module discovery and
# Hook installation.  Compacting this C-only unit recovers RX headroom without
# changing exl_init(), .init_array, or the exl_main() startup code shape.
# 2026-10-10: Lua C API calls also occur in every frame; include lapi below.

# The remaining Lua compile-time units (lexer, parser, code generator, dump
# loaders, debug support, auxiliary/string/table libraries) run during Mod load
# or on explicit library calls, never in the per-frame interpreter loop.
# Size-optimizing them reclaims RX headroom for the layered Runtime migration
# while lvm.o stays at -O3 so the VM loop keeps its code shape.
LUA_SIZE_OPTIMIZED_CFILES := lauxlib.o lbaselib.o lcode.o lcorolib.o lctype.o ldebug.o \
	ldump.o lfunc.o llex.o lmathlib.o lmem.o lobject.o lopcodes.o lparser.o lstate.o \
	lstring.o lstrlib.o ltable.o ltablib.o ltm.o lundump.o lutf8lib.o lzio.o
LUA_HOT_CFILES := lapi.o ltable.o lstring.o lobject.o lmem.o lstate.o \
	lstrlib.o lmathlib.o ltablib.o lauxlib.o
$(filter-out $(LUA_HOT_CFILES),$(LUA_SIZE_OPTIMIZED_CFILES)): CFLAGS += -Oz
ifneq ($(PROBE_BREAK),1)
$(LUA_HOT_CFILES): CFLAGS += -O3
endif
# The historical claim above does not apply to table/string/math/auxiliary
# operations reached by per-frame mod callbacks. Probe builds retain global -Oz.

# Stage145 trace code is diagnostic-only and must remain below the verified
# default Runtime RX LOAD boundary without changing unrelated startup code.
manager_update_hook_audit.o: CXXFLAGS += -Oz
persistence_trace.o: CXXFLAGS += -Oz
saltynx_runtime_bridge.o: CXXFLAGS += -Oz

ifeq ($(PERSISTENCE_TRACE),1)
runtime_entry.o: CXXFLAGS += -Oz
endif

SPECS_PATH := $(TOPDIR)/misc/specs

ASFLAGS	:=	-g $(ARCH)
LDFLAGS     :=  -specs=$(SPECS_PATH)/$(SPECS_NAME) -g $(ARCH) -Wl,-Map,$(notdir $*.map) -nostartfiles -Wl,--eh-frame-hdr

# 2026-09-29（批次 196，L4 钩子隔离·甲案）：把本模块内的 `__cxa_throw` 调用重定向到
# `__wrap___cxa_throw`（记录抛出位置），真实现仍由 `__real___cxa_throw` 调用。
# ★ 纯链接期重定向：**不导出任何全局同名符号**、不改游戏侧符号解析（这正是用户选"甲案"的理由）。
# ★ 已实测 devkitA64 支持（`aarch64-none-elf-g++ -Wl,--wrap=__cxa_throw` 编译与链接均通过）。
LDFLAGS     +=  -Wl,--wrap=__cxa_throw

LIBS	:=	-lnx

#---------------------------------------------------------------------------------
# list of directories containing libraries, this must be the top level containing
# include and lib
#---------------------------------------------------------------------------------
LIBDIRS	:=	$(LIBNX)

#---------------------------------------------------------------------------------
# no real need to edit anything past this point unless you need to add additional
# rules for different file extensions
#---------------------------------------------------------------------------------
ifeq ($(MAKELEVEL),0)
#---------------------------------------------------------------------------------

export OUTPUT	:=	$(EXL_ARTIFACT_DIR)/$(TARGET)
export TOPDIR	:=	.

export VPATH	:=	$(foreach dir,$(SOURCES),$(TOPDIR)/$(dir)) \
			$(ROOT_SOURCE) $(foreach dir,$(DATA),$(TOPDIR)/$(dir))

export DEPSDIR	:=	$(TOPDIR)/$(BUILD)

CFILES		:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.c)))
CPPFILES	:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.cpp)))
# The guard owns these implementations in one translation unit. A public
# checkout can link the matching precompiled archive without their sources.
CPPFILES := $(filter-out notice_integrity_native.cpp title_notice_native.cpp,$(CPPFILES))
NOTICE_GUARD_LINK_INPUT :=
ifneq ($(strip $(NOTICE_GUARD_ARCHIVE)),)
NOTICE_GUARD_LINK_INPUT := $(if $(filter /%,$(NOTICE_GUARD_ARCHIVE)),$(NOTICE_GUARD_ARCHIVE),$(abspath $(TOPDIR)/$(NOTICE_GUARD_ARCHIVE)))
ifeq ($(wildcard $(NOTICE_GUARD_LINK_INPUT)),)
$(error NOTICE_GUARD_ARCHIVE does not exist: $(NOTICE_GUARD_LINK_INPUT))
endif
CPPFILES := $(filter-out notice_guard_core.cpp hook_manager.cpp mod_menu_native.cpp image_pcx_bridge_hook.cpp mod_resource_redirect.cpp mod_image_resources.cpp,$(CPPFILES))
else
ifeq ($(wildcard $(ROOT_SOURCE)/notice_guard/notice_guard_core.cpp),)
$(error Notice guard implementation is absent; provide NOTICE_GUARD_ARCHIVE)
endif
endif
SFILES		:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.s)))
BINFILES	:=	$(foreach dir,$(DATA),$(notdir $(wildcard $(dir)/*.*)))

# Task 6b: the host plugin owns a source root under `src`, so its units would
# otherwise be collected into the production module (and collide on `exl_main`).
# The plugin stages opt in explicitly, and every other build filters them out.
EXL_HOST_PLUGIN_CPPFILES := plugin_entry.cpp saltynx_symbol_resolver.cpp runtime_host_api_client.cpp saltynx_host_plugin.cpp
ifeq ($(strip $(SALTYNX_STAGE$(DIAGNOSTIC_STAGE)_HOST_PLUGIN_ROOT_NAME)),)
CPPFILES := $(filter-out $(EXL_HOST_PLUGIN_CPPFILES),$(CPPFILES))
endif

ifeq ($(SALTYNX_PLUGIN),1)
CPPFILES := $(SALTYNX_STAGE$(DIAGNOSTIC_STAGE)_CPPFILES)
CFILES := $(SALTYNX_STAGE$(DIAGNOSTIC_STAGE)_CFILES)
SFILES := $(SALTYNX_STAGE$(DIAGNOSTIC_STAGE)_SFILES)
else
CPPFILES := $(filter-out saltynx_external_plugin_probe.cpp,$(CPPFILES))
CPPFILES := $(filter-out saltynx_external_plugin_read_probe.cpp,$(CPPFILES))
CPPFILES := $(filter-out saltynx_external_plugin_write_read_probe.cpp,$(CPPFILES))
CPPFILES := $(filter-out saltynx_external_plugin_persist_probe.cpp,$(CPPFILES))
CPPFILES := $(filter-out saltynx_external_plugin_state_probe.cpp,$(CPPFILES))
CPPFILES := $(filter-out saltynx_external_plugin_state_persist_probe.cpp,$(CPPFILES))
CPPFILES := $(filter-out saltynx_external_plugin_bridge_probe.cpp,$(CPPFILES))
CPPFILES := $(filter-out saltynx_external_plugin_file_api_probe.cpp,$(CPPFILES))
CPPFILES := $(filter-out saltynx_external_plugin_runtime_io_probe.cpp,$(CPPFILES))
CPPFILES := $(filter-out saltynx_external_plugin_runtime_state_probe.cpp,$(CPPFILES))
CPPFILES := $(filter-out saltynx_external_plugin_runtime_state_persist_probe.cpp,$(CPPFILES))
CPPFILES += saltynx_runtime_bridge.cpp
CPPFILES += test_run_observer.cpp
# 2026-09-25（批次 134）：`source/` 根目录下的文件不会被上面的 wildcard 收（`SOURCES` 只含子目录），
# 必须像上面两行那样显式登记。这个 TU 负责把本模块的 `.eh_frame` 登记给展开器 ——
# 没有它，本模块里任何 C++ 异常都会走 `abort()` + `_exit` 自旋（无声卡死）。原因见该文件头部注释。
CPPFILES += eh_frame_registration.cpp
# 2026-09-29（批次 196，L4 钩子隔离·甲案）：记录 C++ 异常的**抛出位置**。
# 它必须显式登记（同上一行的理由），并且依赖链接层的 `-Wl,--wrap=__cxa_throw`（见 LDFLAGS）。
# 只记录、不改行为、不导出任何全局同名符号 —— 这是"甲案介入面小"的兑现方式。
CPPFILES += throw_forensics.cpp
# 2026-10-04（批次 363）：`ANM2::Load` 入口中继（模组覆盖本体资源的最后一环）。
# 与上面两行同一个理由 —— `source/` **根目录**下的文件不�� `SOURCES` 的 wildcard 收
# （`SOURCES` 只含各模块子目录），必须显式登记，否则会以"未定义符号"的形式在链接期暴露。
CPPFILES += anm2_load_override_hook.cpp
# 原生资源所有者适配器：source根目录同样须显式进入生产链接。
CPPFILES += native_game_resource_reload.cpp
# 2026-10-09：71内部桥同样位于source根目录，必须显式进入生产链接。
CPPFILES += room_spawn_internal_hook.cpp
# 2026-10-10：66双内部钩位于source根目录，同样必须显式进入生产链接。
CPPFILES += trinket_internal_hook.cpp
CPPFILES += clear_award_internal_hook.cpp
# 压力板字符串寿命事件位于source根目录，显式进入生产链接。
CPPFILES += pressure_plate_animation_hook.cpp
CPPFILES += main_module_load_hook.cpp
CPPFILES += entity_remove_hook.cpp cold_callbacks_internal_hook.cpp card_hook.cpp console_callback_hook.cpp
ifeq ($(PERSISTENCE_TRACE),1)
CPPFILES += persistence_trace.cpp
CPPFILES += manager_update_hook_audit.cpp
endif
ifeq ($(PERSISTENCE_EVENT_DIAGNOSTIC),1)
CPPFILES += persistence_event_journal.cpp
endif
SFILES := $(filter-out saltynx_external_plugin_crt0.s,$(SFILES))
endif

# Filesystem IPC belongs exclusively to the retained stage 4/5 diagnostics.
# Default and stage 6 Runtime packages must not link any logging backend.
ifeq ($(filter 4 5,$(DIAGNOSTIC_STAGE)),)
CFILES := $(filter-out fs_ipc.c,$(CFILES))
endif

# The Runtime opens only explicitly selected Lua libraries. Do not link the
# Lua CLI or libraries that can access the operating system.
LUA_UNSAFE_CFILES := lua.c luac.c liolib.c loslib.c loadlib.c ldblib.c linit.c
CFILES := $(filter-out $(LUA_UNSAFE_CFILES),$(CFILES))

#---------------------------------------------------------------------------------
# use CXX for linking C++ projects, CC for standard C
#---------------------------------------------------------------------------------
ifeq ($(strip $(CPPFILES)),)
#---------------------------------------------------------------------------------
	export LD	:=	$(CC)
#---------------------------------------------------------------------------------
else
#---------------------------------------------------------------------------------
	export LD	:=	$(CXX)
#---------------------------------------------------------------------------------
endif
#---------------------------------------------------------------------------------

ifneq ($(strip $(NOTICE_GUARD_ARCHIVE)),)
# Apply after explicit root-unit additions as well as wildcard discovery.
CPPFILES := $(filter-out notice_guard_core.cpp hook_manager.cpp mod_menu_native.cpp image_pcx_bridge_hook.cpp mod_resource_redirect.cpp mod_image_resources.cpp anm2_load_override_hook.cpp,$(CPPFILES))
endif
export OFILES_BIN	:=	$(addsuffix .o,$(BINFILES))
export OFILES_SRC	:=	$(CPPFILES:.cpp=.o) $(CFILES:.c=.o) $(SFILES:.s=.o)
export OFILES 	:=	$(OFILES_BIN) $(OFILES_SRC) $(NOTICE_GUARD_LINK_INPUT)
export HFILES_BIN	:=	$(addsuffix .h,$(subst .,_,$(BINFILES)))

export INCLUDE	:=	$(foreach dir,$(INCLUDES),-I$(TOPDIR)/$(dir)) \
			$(foreach dir,$(LIBDIRS),-I$(dir)/include) \
			-I$(TOPDIR)/$(BUILD) -I$(ROOT_SOURCE) \
			$(foreach root,$(EXTRA_SOURCE_ROOTS),-I$(root))

export LIBPATHS	:=	$(foreach dir,$(LIBDIRS),-L$(dir)/lib)

ifeq ($(strip $(CONFIG_JSON)),)
	jsons := $(wildcard *.json)
	ifneq (,$(findstring $(TARGET).json,$(jsons)))
		export APP_JSON := $(TOPDIR)/$(TARGET).json
	else
		ifneq (,$(findstring config.json,$(jsons)))
			export APP_JSON := $(TOPDIR)/config.json
		endif
	endif
else
	export APP_JSON := $(TOPDIR)/$(CONFIG_JSON)
endif

.PHONY: $(BUILD) clean all

# Build just the guard dependency, without linking the complete runtime. Keep
# the original object and debug data locally; only the copy in the archive is stripped.
.PHONY: notice-guard-archive
notice-guard-archive: title-notice-prepare
	@mkdir -p "$(BUILD)" "$(EXL_ARTIFACT_DIR)"
	@$(MAKE) --no-print-directory -C $(BUILD) -f ../$(MK_PATH)/common.mk notice_guard_core.o hook_manager.o mod_menu_native.o image_pcx_bridge_hook.o mod_resource_redirect.o mod_image_resources.o anm2_load_override_hook.o
	@$(AR) p "$(LIBNX)/lib/libnx.a" sha256.o > "$(EXL_ARTIFACT_DIR)/notice_guard_sha256.o"
	@guard_libc_path="$$($(CC) -print-file-name=libc.a)"; \
	  for guard_memory in memcpy memset memcmp; do \
	    $(AR) p "$$guard_libc_path" "libc_a-$$guard_memory.o" > "$(EXL_ARTIFACT_DIR)/notice_guard_$$guard_memory.o" || exit 1; \
	  done
	@$(CXX) -nostdlib -r "$(BUILD)/notice_guard_core.o" "$(BUILD)/hook_manager.o" "$(BUILD)/mod_menu_native.o" \
	  "$(BUILD)/image_pcx_bridge_hook.o" "$(BUILD)/mod_resource_redirect.o" "$(BUILD)/mod_image_resources.o" \
	  "$(BUILD)/anm2_load_override_hook.o" \
	  "$(EXL_ARTIFACT_DIR)/notice_guard_sha256.o" \
	  "$(EXL_ARTIFACT_DIR)/notice_guard_memcpy.o" "$(EXL_ARTIFACT_DIR)/notice_guard_memset.o" \
	  "$(EXL_ARTIFACT_DIR)/notice_guard_memcmp.o" -o "$(EXL_ARTIFACT_DIR)/notice_guard_core.bound.o"
	@$(PYTHON) ../tools/seal_notice_guard.py --objcopy "$(OBJCOPY)" \
	  --input "$(EXL_ARTIFACT_DIR)/notice_guard_core.bound.o" \
	  --output "$(EXL_ARTIFACT_DIR)/notice_guard_core.release.o"
	@$(AR) rcs "$(EXL_ARTIFACT_DIR)/libnotice_guard.a" "$(EXL_ARTIFACT_DIR)/notice_guard_core.release.o"

#---------------------------------------------------------------------------------
all: $(BUILD)

# 只读预算报告（2026-09-12 起）：挂在已有的模块构建步骤之后，不再往 `all` 上加新前置
# ——那会把 ELF 拉进桩工具链测试的依赖图，与 `mkdir $(BUILD)` 竞争。工具在非真实 ELF
# 产物（桩工具链的 0 字节文件）上返回 3，这里按"跳过"处理；真实产物超限仍让构建失败。
PYTHON ?= python3
READ_ONLY_BUDGET_TOOL := ../tools/runtime_layout_budget.py
# 预算闸门（2026-09-15 起）：布局工具回答"越没越限"，这个回答"还剩多少、下一批放不放得下"。
# 默认只检查"当前余量是否还在保留线之上"（`--apis 0`）；要与一批具体工作量对账时，
# 手工跑 `--apis <条数> --kind engine|field`。桩工具链产物按退出码 3 跳过（与布局工具同口径）。
BUDGET_FORECAST_TOOL := ../tools/runtime_budget_forecast.py
UNDEFINED_SYMBOL_TOOL := ../tools/check_runtime_elf_symbols.py

$(BUILD):
	@[ -d $@ ] || mkdir -p $@
	@mkdir -p "$(EXL_ARTIFACT_DIR)"
	@$(SHELL) $(SCRIPTS_PATH)/check-build-id.sh "$@" '$(EXL_CFLAGS) $(EXL_CXXFLAGS)'
	@$(MAKE) --no-print-directory -C $(BUILD) -f ../$(MK_PATH)/common.mk
	@$(PYTHON) $(READ_ONLY_BUDGET_TOOL) --elf $(OUTPUT).elf || { \
	  status=$$?; \
	  if [ $$status -eq 3 ]; then \
	    echo "只读预算：跳过 $(OUTPUT).elf（不是真实 ELF 产物，例如测试用桩工具链）"; \
	  else \
	    exit $$status; \
	  fi; \
	}
	@$(PYTHON) $(BUDGET_FORECAST_TOOL) --elf $(OUTPUT).elf --apis 0 || { \
	  status=$$?; \
	  if [ $$status -eq 3 ]; then \
	    echo "预算闸门：跳过 $(OUTPUT).elf（不是真实 ELF 产物，例如测试用桩工具链）"; \
	  else \
	    exit $$status; \
	  fi; \
	}
	@if [ "$(SALTYNX_PLUGIN)" = "1" ]; then \
	  echo "未定义符号门禁：跳过 $(OUTPUT).elf（SALTYNX_PLUGIN=1）"; \
	  echo "  本检查面向运行时模块：它要求除 3 个任天堂运行时符号外没有任何未定义引用。"; \
	  echo "  而宿主插件按设计必须恰好带 1 个未定义的 SaltySD 导入（SaltySDCore_FindSymbol），"; \
	  echo "  两条要求无交集 ⇒ 插件永远过不去。插件的未定义符号改由 post-build 的"; \
	  echo "  tools/check_saltynx_plugin_elf.py 把关（更严：还钉 relocations 与「无 .plt」）。"; \
	else \
	  $(PYTHON) $(UNDEFINED_SYMBOL_TOOL) --elf $(OUTPUT).elf || { \
	    status=$$?; \
	    if [ $$status -eq 3 ]; then \
	      echo "未定义符号门禁：跳过 $(OUTPUT).elf"> /dev/null; \
	    else \
	      exit $$status; \
	    fi; \
	  }; \
	fi
	@$(SHELL) $(SCRIPTS_PATH)/post-build.sh

#---------------------------------------------------------------------------------
clean:
	@echo clean ...
	@rm -fr $(BUILD) $(EXL_ARTIFACT_DIR)/$(TARGET).nso $(EXL_ARTIFACT_DIR)/$(TARGET).npdm $(EXL_ARTIFACT_DIR)/$(TARGET).elf


#---------------------------------------------------------------------------------
else
export OUTPUT := $(TOPDIR)/$(EXL_ARTIFACT_DIR)/$(TARGET)
export VPATH := $(foreach dir,$(SOURCES),$(TOPDIR)/$(dir)) \
	$(ROOT_SOURCE) $(foreach dir,$(DATA),$(TOPDIR)/$(dir))
export DEPSDIR := $(TOPDIR)/$(BUILD)
export INCLUDE := $(foreach dir,$(INCLUDES),-I$(TOPDIR)/$(dir)) \
	$(foreach dir,$(LIBDIRS),-I$(dir)/include) \
	-I$(TOPDIR)/$(BUILD) -I$(ROOT_SOURCE) \
	$(foreach root,$(EXTRA_SOURCE_ROOTS),-I$(root))
.PHONY:	all 

DEPENDS	:=	$(patsubst %.o,%.d,$(filter %.o,$(OFILES)))

#---------------------------------------------------------------------------------
# main targets
#---------------------------------------------------------------------------------

all	:	$(OUTPUT).nso

$(OUTPUT).nso	:	$(OUTPUT).elf $(OUTPUT).npdm
	@if [ -z "$(strip $(DIAGNOSTIC_STAGE)$(STARTUP_PROBE_STAGE))" ] && [ "$(SALTYNX_PLUGIN)" != "1" ]; then \
	  $(PYTHON) $(TOPDIR)/../tools/seal_notice_code.py --elf $(OUTPUT).elf && \
	  $(PYTHON) $(TOPDIR)/../tools/seal_notice_code.py --elf $(OUTPUT).elf --verify || exit 1; \
	fi
	@elf2nso $(OUTPUT).elf $@
	@echo built ... $(notdir $@)

$(OUTPUT).nso: $(TOPDIR)/../tools/seal_notice_code.py

$(OUTPUT).elf: $(TOPDIR)/misc/specs/$(SPECS_NAME) $(TOPDIR)/misc/link.ld $(TOPDIR)/misc/link_startup_probe_compat.ld $(OFILES)

$(OFILES_SRC)	: $(HFILES_BIN)

#---------------------------------------------------------------------------------
# you need a rule like this for each extension you use as binary data
#---------------------------------------------------------------------------------
%.bin.o	%_bin.h :	%.bin
#---------------------------------------------------------------------------------
	@echo $(notdir $<)
	@$(bin2o)

-include $(DEPENDS)

#---------------------------------------------------------------------------------------
endif
#---------------------------------------------------------------------------------------
