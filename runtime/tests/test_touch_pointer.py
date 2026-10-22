"""门禁：批次 192「触摸屏 → 指针」不许悄悄退化。

## 为什么要有它

PC 的 `Input.GetMousePosition` / `Input.IsMouseBtnPressed` 原先恒 `(0,0)` / 恒 `false`
（批次 041 登记为"平台固有、永远消不掉"）。后果是**第三方模组里所有"鼠标悬停才显示"的交互
在真机上是死的** —— EID 的 `EID:handleHoverHUD()`（`main.lua:1050`）与
`EID:renderHUDLocationIndicators()`（`main.lua:1024`）永远触发不了；
2026-09-28 用户实测"屏幕上什么都没看到"，查证后确认就是这条路
（我先前把 `EID.HUDElements` 误当成"口袋物品栏"，见当天日志 §190）。

批次 192 把**触摸屏**接成指针源（用户指令「把 PC 的鼠标操作映射成 NS 的触屏操作」）。

## 这一层能验什么、验不了什么（★ 别把它当"真值已被证明"）

* **能验**：接线在不在；宿主机（没有触摸屏）上是不是**老实回答"没按下"**；
  诊断量会不会被写；`Reset` 的边界对不对；`__aarch64__` 守卫生效（不在 x86 上拉 libnx）。
* **验不了**：触摸坐标的真值与换算 —— **只能真机**（与"引擎返回值对不对"同一性质）。
  ⇒ 本批刻意**不做坐标换算**，先把原始值读出来（`g_TouchPointerLastRawX/Y`）。
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LUA_API = ROOT / "runtime" / "src" / "interfaces" / "lua"
SOURCE = ROOT / "runtime" / "src"
INPUT_API = LUA_API / "input_api.cpp"
TOUCH_HEADER = LUA_API / "touch_pointer.hpp"
DEVIATION = LUA_API / "api_deviation.cpp"
STUB_LEDGER = ROOT / "tools" / "lua_api_stub_ledger.json"

#: 宿主机上跑的小夹具：验"没有触摸屏时"的行为与计数器的边界（真值只能真机）。
HARNESS = r'''
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#include "interfaces/lua/touch_pointer.hpp"

using namespace isaac::runtime;

int main() {
    int failures = 0;
    auto check = [&](bool ok, const char* what) {
        if (!ok) { std::printf("FAIL %s\n", what); ++failures; }
    };

    // ---- 1) 没有触摸时：必须回"没按下"，且**不许编造坐标**（两个平台都要成立）。
    const TouchPointerSnapshot first = ReadTouchPointer();
    check(!first.pressed, "must report not-pressed when there is no touch");
    check(first.rawX == 0 && first.rawY == 0, "must not invent coordinates");

    // ---- 2) 平台分档：宿主机是**惰性桩**，目标平台才真的去读 hid。
#if defined(__SWITCH__)
    check(g_TouchPointerPollFrames.load() == 1, "device: poll frame counter must advance");
    check(g_TouchPointerScanAttempts.load() == 1, "device: mapping scan runs on the first read");
    check(g_TouchPointerInitState.load() !=
              static_cast<std::uint32_t>(TouchPointerInitState::kNotTried),
          "device: state must leave kNotTried after the first read");
    ReadTouchPointer();
    check(g_TouchPointerPollFrames.load() == 2, "device: poll frames must accumulate");
#else
    // 宿主机的桩**什么都不做** —— 连计数器都不动，免得"宿主用例绿了"被误读成
    // "触摸真的通了"（真值只能真机）。
    check(g_TouchPointerPollFrames.load() == 0, "host: stub must stay inert");
    check(g_TouchPointerScanAttempts.load() == 0, "host: must not scan");
    check(g_TouchPointerInitState.load() ==
              static_cast<std::uint32_t>(TouchPointerInitState::kNotTried),
          "host: must stay kNotTried");
#endif

    // ---- 3) Reset 的**边界**（本批次最容易写错的地方）：
    // 先人为写满，再看 Reset 清了什么、**没清**什么。这样两个平台都能验同一条契约。
    g_TouchPointerPollFrames.store(5);
    g_TouchPointerTouchFrames.store(3);
    g_TouchPointerLastRawX.store(111);
    g_TouchPointerLastRawY.store(222);
    g_TouchPointerLastCount.store(1);
    // 扫描结果写一个哨兵：那块映射是**进程级**的，Reset 不许把它清掉
    // （否则下一次读会白扫一遍映射表 = 几十万次内核查询）。
    g_TouchPointerInitState.store(9);
    g_TouchPointerScanAttempts.store(7);
    g_TouchPointerShmemLow.store(0xBEEF);
    ResetTouchPointer();
    check(g_TouchPointerPollFrames.load() == 0, "reset clears poll frames");
    check(g_TouchPointerTouchFrames.load() == 0, "reset clears touch frames");
    check(g_TouchPointerLastRawX.load() == 0 && g_TouchPointerLastRawY.load() == 0,
          "reset clears the last position");
    check(g_TouchPointerInitState.load() == 9, "reset must NOT touch the init state");
    check(g_TouchPointerScanAttempts.load() == 7, "reset must NOT forget the scan result");
    check(g_TouchPointerShmemLow.load() == 0xBEEF, "reset must NOT drop the found mapping");

    // ---- 4) ★★ 判据：只有**真的 lifo** 才算数。
    // 批次 192 的真机事故：判据只是"17 个条目的点数都在 0..16"，于是**一块零页**被认成了
    // 触摸屏共享内存（读数里报"找到共享内存"、基址 0x4cc64f000，`--read` 一看整段全 0）。
    // 这一段用合成缓冲喂**同一个判据**（同一套常量），把当时那种页钉死为"不许通过"。
    {
        using namespace isaac::runtime::touch_pointer_detail;
        std::vector<std::uint8_t> page(kMinimumSharedMemoryBytes + 0x100, 0);
        const std::uintptr_t base = reinterpret_cast<std::uintptr_t>(page.data());
        auto read64 = [&page, base](std::uintptr_t address, std::uint64_t fallback) {
            const std::uintptr_t offset = address - base;
            if (offset + 8 > page.size()) { return fallback; }
            std::uint64_t value = 0;
            std::memcpy(&value, page.data() + offset, 8);
            return value;
        };
        auto read32 = [&page, base](std::uintptr_t address, std::uint32_t fallback) {
            const std::uintptr_t offset = address - base;
            if (offset + 4 > page.size()) { return fallback; }
            std::uint32_t value = 0;
            std::memcpy(&value, page.data() + offset, 4);
            return value;
        };
        auto put64 = [&page](std::uintptr_t offset, std::uint64_t value) {
            std::memcpy(page.data() + offset, &value, 8);
        };
        auto put32 = [&page](std::uintptr_t offset, std::uint32_t value) {
            std::memcpy(page.data() + offset, &value, 4);
        };
        const std::uintptr_t lifo = kTouchScreenLifoOffset;
        const std::uintptr_t bufferCount = lifo + kHeaderBufferCountOffset;

        // 4a) ★★ 这一条就是批次 192 的误报：整块零页**绝不能**被判成 lifo。
        check(!LooksLikeTouchScreenLifo(read64, read32, base, page.size()),
              "an all-zero page must never look like the touchscreen lifo");

        // 4b) 补上 `buffer_count = 17` 之后就该成立（它是**建表时写死**的，与有没有触摸无关）。
        put64(bufferCount, 17);
        check(LooksLikeTouchScreenLifo(read64, read32, base, page.size()),
              "buffer_count == 17 is what makes a mapping the touchscreen lifo");

        // 4c) 只差这一个字段就不再成立 ⇒ 它是**硬判据**，不是陪衬。
        put64(bufferCount, 16);
        check(!LooksLikeTouchScreenLifo(read64, read32, base, page.size()),
              "buffer_count must be exactly 17");
        put64(bufferCount, 17);

        // 4d) 环形下标越界（tail）与超过环容量（count）都要判否。
        put64(lifo + kHeaderTailOffset, kLifoEntryCount);
        check(!LooksLikeTouchScreenLifo(read64, read32, base, page.size()),
              "tail must stay inside the ring");
        put64(lifo + kHeaderTailOffset, 0);
        put64(lifo + kHeaderCountOffset, kLifoEntryCount + 1);
        check(!LooksLikeTouchScreenLifo(read64, read32, base, page.size()),
              "count must not exceed the ring");
        put64(lifo + kHeaderCountOffset, 0);

        // 4e) 任何一个条目的"点数"越界 ⇒ 整块判否（原判据保留，作为第二道）。
        put32(kTouchScreenStorageOffset + 3 * kLifoEntryStride + kEntryCountOffset, 17);
        check(!LooksLikeTouchScreenLifo(read64, read32, base, page.size()),
              "an out-of-range touch count must reject the whole page");
        put32(kTouchScreenStorageOffset + 3 * kLifoEntryStride + kEntryCountOffset, 0);

        // 4f) 长度不够 ⇒ 判否（**先**过长度检查再去读，否则会读到映射外 ⇒ Data Abort）。
        check(!LooksLikeTouchScreenLifo(read64, read32, base, kMinimumSharedMemoryBytes - 1),
              "a mapping too short for the whole lifo must be rejected");

        // ---- 5) 取"最新条目" + **x/y 必须读在 libnx 的字段上**（批次 192 在这里错位了一个字段）
        // `HidTouchState = u64 delta_time; u32 attributes; u32 finger_id; u32 x; u32 y; ...`
        const std::uintptr_t entry5 = kTouchScreenStorageOffset + 5 * kLifoEntryStride;
        const std::uintptr_t entry9 = kTouchScreenStorageOffset + 9 * kLifoEntryStride;
        // 条目 5：新（sampling=100）；条目 9：旧（sampling=50）
        put64(entry5 + kEntrySamplingOffset, 100);
        put32(entry5 + kEntryCountOffset, 1);
        put64(entry9 + kEntrySamplingOffset, 50);
        put32(entry9 + kEntryCountOffset, 1);
        // ★ 五个相邻字段各写**互不相同**的哨兵：只有偏移对，读到的才正好是 x 与 y。
        // 批次 192 把 x 读在 `+12`（那是 finger_id）、把 y 读在 `+16`（那是 x）——
        // 下面这两个断言当时会红。
        put32(entry5 + kEntryTouch0Offset + 0, 0xAAAA0000);  // u64 delta_time 的后半
        put32(entry5 + kEntryTouch0Offset + 8, 0xAAAA0008);  // attributes
        put32(entry5 + kEntryTouch0Offset + 12, 0xAAAA000C); // finger_id
        put32(entry5 + kEntryTouch0Offset + 16, 0xAAAA0010); // x ← 必须读到这个
        put32(entry5 + kEntryTouch0Offset + 20, 0xAAAA0014); // y ← 与这个
        put32(entry5 + kEntryTouch0Offset + 24, 0xAAAA0018); // diameter_x（错位时会被当成 y）
        std::uint32_t pickedX = 0;
        std::uint32_t pickedY = 0;
        std::uint32_t pickedCount = 7;
        std::uint32_t pickedIndex = 7;
        std::uint64_t pickedSampling = 0;
        check(ReadNewestTouchFrom(read64, read32, base, &pickedX, &pickedY, &pickedCount,
                                  &pickedIndex, &pickedSampling),
              "a lifo with samples must yield one entry");
        check(pickedIndex == 5, "must pick the entry with the largest sampling number");
        check(pickedSampling == 100, "must report the newest sampling number");
        check(pickedCount == 1, "must report the touch count of the newest entry");
        check(pickedX == 0xAAAA0010 && pickedY == 0xAAAA0014,
              "x/y must be read from HidTouchState +16/+20 (not +12/+16)");

        // 5b) 采样号为 0 的条目**不算数** —— 那是"这块内存没在被写"的证据。
        // 把新的那条清零之后，被选中的应当是**另一条**（槽位 9），而不是"读失败"。
        put32(entry9 + kEntryTouch0XOffset, 0xBBBB0010);
        put64(entry5 + kEntrySamplingOffset, 0);
        check(ReadNewestTouchFrom(read64, read32, base, &pickedX, &pickedY, &pickedCount,
                                  &pickedIndex, &pickedSampling)
                  && pickedIndex == 9 && pickedX == 0xBBBB0010,
              "entries without a sampling number must be ignored");
        // 两条都没有采样号 ⇒ 一条都不该给出（调用方据此判"这块内存是死的"）。
        put64(entry9 + kEntrySamplingOffset, 0);
        check(!ReadNewestTouchFrom(read64, read32, base, &pickedX, &pickedY, &pickedCount,
                                   &pickedIndex, &pickedSampling),
              "a lifo whose entries all have sampling 0 must report nothing");
        put64(entry5 + kEntrySamplingOffset, 100);
        put64(entry9 + kEntrySamplingOffset, 50);

        // 5c) 最新条目 count == 0 ⇒ 传得出"点数 0"（调用方据此回"没按下"，**不是**读失败）。
        put32(entry5 + kEntryCountOffset, 0);
        check(ReadNewestTouchFrom(read64, read32, base, &pickedX, &pickedY, &pickedCount,
                                  &pickedIndex, &pickedSampling) && pickedCount == 0,
              "a newest entry with zero touches must still be reported as such");
    }

    // ---- 6) 换算口径的**值**（格式与"引擎口径"的一致性：0.375，不是我们拍的数）。
    {
        using namespace isaac::runtime::touch_pointer_detail;
        check(kPanelToRenderScaleX == 0.375F && kPanelToRenderScaleY == 0.375F,
              "panel->render scale must be 0.375");
        check(kPanelToRenderScaleX == kRenderWidth / kTouchPanelWidth
                  && kPanelToRenderScaleY == kRenderHeight / kTouchPanelHeight,
              "the scale must stay derived from the panel/screen constants, not a magic number");
    }

    if (failures != 0) {
        std::printf("TOUCH_POINTER_CHECKS_FAILED %d\n", failures);
        return 1;
    }
    std::printf("TOUCH_POINTER_CHECKS_PASSED\n");
    return 0;
}
'''


#: 布局夹具：**编译期**把每个偏移钉死。
#: 为什么不用文本匹配（`assertIn("kTouchScreenStorageOffset = 0x420", ...)`）：那样一旦有人把常量
#: 改写成**等价的算式**（本批就把它写成了 `kTouchScreenLifoOffset + kLifoHeaderBytes`），
#: 断言会因为"字面量没了"而红 —— 那是**假红**；反过来，值真的算错了文本匹配也未必抓得住。
#: `static_assert` 钉的是**值**，正是"口径"本身该被钉的方式。
LAYOUT_HARNESS = r'''
#include <cstdint>
#include "interfaces/lua/touch_pointer.hpp"

namespace detail = isaac::runtime::touch_pointer_detail;

//: 口径来源：libnx 头文件 + `libnx.a` 里 `hidGetTouchScreenStates` 的反汇编（文件头有出处）。
static_assert(detail::kTouchScreenLifoOffset == 0x400, "lifo sits at +0x400");
static_assert(detail::kLifoHeaderBytes == 0x20, "HidCommonLifoHeader is 4 u64");
static_assert(detail::kTouchScreenStorageOffset == 0x420, "entries start right after the header");
static_assert(detail::kLifoEntryCount == 17, "17 lifo entries");
static_assert(detail::kLifoEntryStride == 0x298, "entry = u64 + HidTouchScreenState(0x290)");
static_assert(detail::kHeaderBufferCountOffset == 8, "buffer_count is the 2nd u64 of the header");
static_assert(detail::kHeaderTailOffset == 16, "tail is the 3rd u64");
static_assert(detail::kHeaderCountOffset == 24, "count is the 4th u64");
static_assert(detail::kExpectedBufferCount == 17, "buffer_count is pinned to the entry count");
static_assert(detail::kEntrySamplingOffset == 8, "the state follows the outer sampling number");
static_assert(detail::kEntryCountOffset == 16, "count is state+8");
static_assert(detail::kEntryTouch0Offset == 24, "touches[0] is state+0x10");
static_assert(detail::kTouchFieldXOffset == 16, "x follows u64 delta_time + attributes + finger_id");
static_assert(detail::kTouchFieldYOffset == 20, "y is right after x");
static_assert(detail::kEntryTouch0XOffset == 40, "entry+40 is x");
static_assert(detail::kEntryTouch0YOffset == 44, "entry+44 is y");
static_assert(detail::kMinimumSharedMemoryBytes == 0x420 + 17 * 0x298,
              "the whole lifo must fit inside the mapping");

//: 换算口径（2026-09-28 独立核实）：面板硬编码 1280×720、引擎逻辑屏幕 480×270 ⇒ 0.375。
//: 来源：`DeviceTouchscreen::GetTouchPanelWidth/Height`（0x4fcd6c/0x4fcd74）反编译即
//: `return 0x500;` / `return 0x2d0;`；`0xa386c0`/`0xa386c4` = 480.0f/270.0f。
static_assert(detail::kTouchPanelWidth == 1280.0F && detail::kTouchPanelHeight == 720.0F,
              "the touch panel is hardcoded 1280x720 in the engine");
static_assert(detail::kRenderWidth == 480.0F && detail::kRenderHeight == 270.0F,
              "the engine's logical screen is 480x270");
static_assert(detail::kPanelToRenderScaleX == 0.375F, "480 / 1280");
static_assert(detail::kPanelToRenderScaleY == 0.375F, "270 / 720");

int main() { return 0; }
'''


def host_compiler() -> str | None:
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return found
    return None


def body_of(source: str, name: str) -> str:
    """返回处理器**定义**的函数体（必须带 ` {` 找，否则会命中同名前置声明）。"""
    start = source.index(f"int {name}(lua_State* state) {{")
    return source[start:source.index("\n}\n", start)]


def code_of(source: str) -> str:
    """只保留代码、剔掉 `//` 行注释。

    ★ 为什么必须剔：本项目的注释里**大量引用被禁止的写法**（"不许 include
    `<switch/services/hid.h>`"、"不能用 `__aarch64__`"…）⇒ 直接对全文断言 `assertNotIn`
    会被**解释这些话的注释本身**判红，而那与实现无关。断言要盯的是**代码**。
    """
    return "\n".join(line.split("//", 1)[0] for line in source.splitlines())


def function_body(source: str, name: str) -> str:
    """返回 `name(` 那次定义到**列 0 的 `}`** 之间的正文（C++ 的通用取法）。

    `body_of` 是给 Lua 处理器写的（签名固定 `int X(lua_State* state) {`）；
    头文件里的 `inline` 函数用它取不到，所以另给这一个。
    """
    start = source.index(f"{name}(")
    #: 跳过参数表与限定符，从函数体那个 `{` 开始
    brace = source.index("{", start)
    end = source.index("\n}\n", brace)
    return source[brace:end]


class TouchPointerBehaviourTests(unittest.TestCase):
    """宿主机上能验的那一半（真值只能真机）。"""

    def test_host_semantics(self):
        compiler = host_compiler()
        if compiler is None:
            self.skipTest("宿主机没有 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="isaac-touch-pointer-") as directory:
            workdir = Path(directory)
            source = workdir / "harness.cpp"
            source.write_text(HARNESS.lstrip(), encoding="utf-8")
            binary = workdir / "harness"
            build = subprocess.run(
                [compiler, "-std=c++23", "-Wall", "-Wextra", "-Werror", "-I", str(SOURCE),
                 str(source), "-o", str(binary)],
                text=True, capture_output=True,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("TOUCH_POINTER_CHECKS_PASSED", run.stdout)


class TouchPointerLayoutTests(unittest.TestCase):
    """布局口径：**编译期**钉死每一个偏移（值，而不是字面量的写法）。"""

    def test_the_layout_is_pinned_at_compile_time(self):
        compiler = host_compiler()
        if compiler is None:
            self.skipTest("宿主机没有 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="isaac-touch-layout-") as directory:
            workdir = Path(directory)
            source = workdir / "layout.cpp"
            source.write_text(LAYOUT_HARNESS.lstrip(), encoding="utf-8")
            build = subprocess.run(
                [compiler, "-std=c++23", "-Wall", "-Wextra", "-Werror", "-I", str(SOURCE),
                 str(source), "-o", str(workdir / "layout")],
                text=True, capture_output=True,
            )
            self.assertEqual(build.returncode, 0,
                             "布局断言没过（改偏移就会红）：\n" + build.stdout + build.stderr)


class TouchPointerWiringTests(unittest.TestCase):
    """接线与判据（文本）。"""

    @classmethod
    def setUpClass(cls):
        cls.header = TOUCH_HEADER.read_text(encoding="utf-8")
        #: 断言一律用**剔掉注释**的版本（注释里会引用被禁止的写法，见 `code_of`）。
        cls.header_code = code_of(cls.header)
        cls.input_api = INPUT_API.read_text(encoding="utf-8")
        cls.deviation = DEVIATION.read_text(encoding="utf-8")

    def test_no_libnx_hid_header_and_no_switch_crt0_pull(self):
        """**不许**引 libnx 的 hid 头，也不许调 libnx 的 hid 函数。

        ★ 两条都是 2026-09-28 实测撞出来的（顺序就是当时撞的顺序）：
          ① 引 `<switch/services/hid.h>` ⇒ 它带的 `result.h` 与 exlaunch 的同名宏/枚举冲突，
             `-Werror` 下 300 余条 `redefined` / `conflicts with a previous declaration`；
          ② 绕开 ①、改成自己声明并调 `hidGetTouchScreenStates` ⇒ 链进 libnx 的 `hid.o` ⇒
             它要 `appletGetAppletResourceUserId` ⇒ `applet.o` ⇒ `envSetExitFuncPtr` ⇒ `env.o`
             ⇒ `__nx_exit` ⇒ **`switch_crt0.o`** ⇒ `relocation R_AARCH64_PREL32 ... can not be
             used when making a shared object`（我们是被注入的模块，用的是 exlaunch 的 CRT）。
        """
        self.assertNotIn("switch/services/hid.h", self.header_code)
        self.assertNotIn("hidGetTouchScreenStates", self.header_code)
        self.assertNotIn("hidInitializeTouchScreen", self.header_code)
        #: 只许用仓库里 vendored 的那份（`MemoryInfo`/`Perm_R`/`svcQueryMemory` 由它提供），
        #: 而不是 devkitpro 的 `<switch.h>`。
        self.assertIn('#include "lib/nx/nx.h"', self.header_code)
        self.assertNotIn("<switch.h>", self.header_code)

    def test_the_guard_is_switch_and_never_aarch64(self):
        """守卫必须是 `__SWITCH__`，**不能**是 `__aarch64__`。

        ★ 这条是踩过才知道的：**Apple Silicon 的 macOS 上也定义 `__aarch64__`**，
        用它会去拉 libnx 头 ⇒ 宿主机编译直接 `fatal error: file not found`（本批第一版就是这么错的）。
        本项目"只在 Switch 上引 libnx"的既有写法是 `__SWITCH__`
        （构建显式传入：`runtime/misc/mk/common.mk:98`）。
        """
        self.assertIn("#if defined(__SWITCH__)", self.header_code)
        self.assertNotIn("#if defined(__aarch64__)", self.header_code)

    def test_the_shared_memory_layout_is_pinned(self):
        """布局常量之间的**关系**（值本身由 `LayoutHarness` 在编译期钉死，见那一类）。

        来源（文件头写着，可复核）：devkitPro 里 libnx 的头文件 + `libnx.a` 里
        `hidGetTouchScreenStates` 的反汇编，互证。`sizeof(HidCommonLifoHeader)=0x20`、
        `sizeof(HidTouchScreenStateAtomicStorage)=0x298`、`sizeof(HidTouchScreenState)=0x290`。
        """
        self.assertIn("kTouchScreenStorageOffset = kTouchScreenLifoOffset + kLifoHeaderBytes",
                      self.header_code)
        self.assertIn("kExpectedBufferCount = kLifoEntryCount", self.header_code)
        self.assertIn("kEntryTouch0XOffset = kEntryTouch0Offset + kTouchFieldXOffset",
                      self.header_code)
        self.assertIn("kEntryTouch0YOffset = kEntryTouch0Offset + kTouchFieldYOffset",
                      self.header_code)

    def test_the_signature_logic_stays_outside_the_switch_guard(self):
        """★ 判据与"取最新条目"必须留在 `__SWITCH__` **外面**，否则宿主门禁编不到它。

        这条由批次 192 的事故倒逼：那次误报是**纯逻辑错**（判据太弱 ⇒ 把一块零页认成触摸屏），
        而逻辑当时在守卫里面 ⇒ "零页会不会被认成触摸屏"这件事在本地**根本无法被测试**。
        """
        code = self.header_code
        device_reader = code.index("ReadU32(std::uintptr_t address")
        for name in ("LooksLikeTouchScreenLifo", "ReadNewestTouchFrom"):
            self.assertLess(code.index(name), device_reader,
                            f"{name} 必须在 `__SWITCH__` 外面（宿主可测）")

    def test_a_short_mapping_is_never_read(self):
        """★ 会崩的那一步：只有映射**长度够**时才去读它的条目。

        读映射外会 `Data Abort`。所以长度检查必须排在**任何读**之前（现在它同时是
        `buffer_count` 那条硬判据的前置）。
        """
        body = code_of(function_body(self.header, "LooksLikeTouchScreenLifo"))
        self.assertIn("kMinimumSharedMemoryBytes", body)
        self.assertLess(body.index("kMinimumSharedMemoryBytes"), body.index("readU32"))

    def test_only_readable_mappings_are_considered(self):
        """只认可读的映射（`Perm_R`）—— 不可读的段摸一下就是 `Data Abort`。"""
        self.assertIn("info.perm & Perm_R", self.header_code)
        self.assertIn("R_FAILED(svcQueryMemory", self.header_code)

    def test_the_two_mouse_apis_read_the_touch_screen(self):
        for name in ("InputGetMousePosition", "InputIsMouseBtnPressed"):
            body = body_of(self.input_api, name)
            self.assertIn("ReadTouchPointer()", body, name)

    def test_no_mouse_api_returns_a_written_off_constant(self):
        """不许再出现"恒 (0,0)" / "恒 false" 那种写死的返回值（批次 128 钉错方向的教训）。"""
        for name in ("InputGetMousePosition", "InputIsMouseBtnPressed"):
            body = body_of(self.input_api, name)
            self.assertNotIn("0.0F, 0.0F", body, name)
            # 控制台独占输入时的有条件屏蔽，不是设备查询恒假。
            body = body.replace("if (console::ConsoleCapturesInput()) { lua_pushboolean(state, 0); return 1; }", "")
            self.assertNotIn("lua_pushboolean(state, 0)", body, name)

    def test_the_hot_path_still_never_raises(self):
        """两条都在每帧路径上 ⇒ 除"参数个数不对"外不许有第二种抛错（否则整条回调被摘掉）。"""
        self.assertEqual(body_of(self.input_api, "InputGetMousePosition").count("luaL_error"), 1)

    def test_the_pointer_is_converted_by_the_shared_transform(self):
        """★ 换算**不再硬编码系数**，而是走与 `Isaac.ScreenToWorld` 共用的那一段。

        ★★ 2026-09-29（批次 195）改写（这是批次 193 的一处**错误**的更正）：
        批次 193 把指针换算写成 `raw * 0.375`（= 480/1280）。**0.375 是"画布"系数，不是掌机的
        渲染平面系数** —— 掌机可见渲染平面是 **426×240**（系数 426/1280 = 0.3328），而且
        `WIDTH`/`HEIGHT`/`POINTSCALE` 三个都是**运行期全局**（`ResizeWindow` 会改它们）
        ⇒ 任何硬编码的系数都会在掌机上算错。

        现在 `Input.GetMousePosition(true)` 直接把**窗口像素（= 触摸面板原始读数）**交给
        `Isaac.ScreenToWorld` 那条共用算式（`TransformScreenToWorldPosition`，与
        `Isaac.ScreenToWorld`、`Room:GetWorldToScreenPosition` 同一份实现）。
        判据：**API 层不许再出现任何换算系数**，一个数都不许写。
        """
        body = body_of(self.input_api, "InputGetMousePosition")
        self.assertIn("TransformScreenToWorldPosition", body)
        self.assertNotIn("kPanelToRenderScaleX", body)
        self.assertNotIn("kPanelToRenderScaleY", body)
        # 代码里（注释除外）一个换算系数都不许有。
        code = code_of(body)
        for forbidden in ("0.375", "0.3328", "480.0F", "270.0F", "426.0F", "240.0F"):
            self.assertNotIn(forbidden, code, forbidden)

    def test_the_world_coord_half_is_no_longer_a_stub(self):
        """★ 2026-09-29（批次 195）改写：那对耦合已经随两条真实现一起消失。

        原判据（批次 193）是把"`gameCoords` 两种都给同一个值"这条偏离与
        `Isaac.WorldToScreen` 的恒等桩**绑在一起** —— 当时模组的
        `Isaac.WorldToScreen(Input.GetMousePosition(true))` 之所以正确，**只因为**两侧都是恒等。

        现在（批次 195）两条都是真变换：
          * `Input.GetMousePosition(true)` = **世界坐标** = `Isaac.ScreenToWorld(窗口像素)`；
          * `Isaac.WorldToScreen` = 引擎 `GetRenderPosition(pos, true)` + 两个相机偏移；
        ⇒ `WorldToScreen(GetMousePosition(true))` 变成 `W2S ∘ S2W`，仍是正确组合，但**不再是
        "两个恒等凑出来"**。本条按当时的说明改写：台账里不再有 `Isaac:WorldToScreen` 那条，
        而 `GetMousePosition` 必须走那条共用变换。
        """
        ledger = json.loads(STUB_LEDGER.read_text(encoding="utf-8"))
        self.assertNotIn(
            "Isaac:WorldToScreen", ledger["rows"],
            "`Isaac.WorldToScreen` 已经是真实现（真调引擎 GetRenderPosition）⇒ 它不该再出现在"
            "安全桩台账里。")
        body = body_of(self.input_api, "InputGetMousePosition")
        self.assertIn("TransformScreenToWorldPosition", body)

    def test_losing_position_is_not_reported_as_movement(self):
        """没有触摸时必须返回**上一次**位置 —— GoodTrip 靠"与上一帧的距离"判拖拽。

        恒 0 会让它永远判"没动过"（这正是批次 041 那条偏离的后果描述）。
        """
        self.assertIn("g_TouchPointerLastRawX.load()", self.header_code)
        self.assertIn("g_TouchPointerLastRawY.load()", self.header_code)

    def test_the_deviations_were_reclassified_from_platform_to_debt(self):
        """残留那条偏离必须仍是"可还的欠账"（批次 192 从 `platform` 改档过来）。

        ★ 这条防止"改完实现忘了改台账"：台账还写着 platform，读数里的"风险面"就会继续
        把它们说成"再怎么继续做工作也消不掉"，下一轮又会得出"不用做"的结论。
        """
        # ★ 批次 195：`0x09010007` 那条（`GetMousePosition`）**偏离已还清、条目删除**
        # （两种 `gameCoords` 都按 PC 语义实现了）⇒ 这里只剩 `IsMouseBtnPressed` 那一条。
        for api_id in ("0x09010008",):
            start = self.deviation.index("{" + api_id + ",")
            block = self.deviation[start:start + 3000]
            self.assertIn("debt", block, api_id)
            # 也不许再留"平台固有"的**定性**（原文案里那句"再怎么继续做工作也消不掉"）。
            self.assertNotIn("只能恒给 (0,0)，再怎么继续做工作也消不掉", block, api_id)

    def test_the_reclassification_says_why(self):
        """改档必须写明理由（"hid 权限本来就在、缺的不是权限是没做"）——否则下一个人会改回去。"""
        start = self.deviation.index("{0x09010008,")
        block = self.deviation[start:start + 4000]
        self.assertIn("触摸屏", block)
        self.assertIn("平台固有", block)  # 要提到"原来是这么登记的"


if __name__ == "__main__":
    unittest.main()