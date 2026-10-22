"""门禁：`MusicManager:Disable()` / `Enable()` / `IsEnabled()`（批次 305，2026-10-03）。

## 这一批是什么

| API | 契约 | 引擎侧 | 形状 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `MusicManager:Disable()` | `MusicManager.md:40/42` `void Disable ( )` | `Music + 0x3F0` 写 0 | 字段行 `BoolWriteConst`（`offset2` = 0）/ 返回 0 值 | 1 |
| `MusicManager:Enable()` | `MusicManager.md:50/52` `void Enable ( )` | 同一格写 1 | 字段行 `BoolWriteConst`（`offset2` = 1）/ 返回 0 值 | 1 |
| `MusicManager:IsEnabled()` | `MusicManager.md:80/82` `boolean IsEnabled ( )` | 同一格读 | 字段行 `Bool` / 返回 1 值 | 1 |

★ 三条在 PC 上都是 `Music + 0x328` 的**一个字节**，三条绑定本体各只有**一条指令**
（`tools/pc_exe_binding.py <名字> --disasm`）：

    7fac20  mov byte ptr [ecx + 0x328], 0x1   ; Enable()
    7fac30  mov byte ptr [ecx + 0x328], 0x0   ; Disable()
    7fac40  mov al, byte ptr [ecx + 0x328]    ; IsEnabled()

⇒ 三条都**不收实参**、也不调引擎函数 ⇒ 走**字段数据行**（0 字节代码），
不需要"引擎方法行"（那种要符号 + 参数契约，这里引擎根本没有 `Music::Disable()` 这种成员名）。

## 为什么是 `+0x3F0` 而不是 PC 的 `+0x328`

★ **数值不许平移**（布局差异）。Switch 侧两条独立证据指向同一格、语义同向
（详见 `runtime_constants.hpp` 的批次 305 段）：

* **具名写入方 = 构造函数** `Music::Music() @ 0x423FBC`：`mov w8,#0x1` + `strb w8,[x19,#0x3f0]`
  ⇒ 默认**启用**（与 PC "引擎起来就是启用"一致）；
* **具名消费者 = `Music::Update()` 的闸**：`ldrb w8,[x0,#0x3f0]` + `cbnz → 去更新音乐`
  ⇒ 「非 0 才更新」与 PC 的 `Enable ⇒ 1` 同向。

能互相印证的只有「同一个字节、1 = 启用、0 = 停用、构造默认 1」这套语义 —— 偏移本身靠 Switch 侧。

## 新的 `FieldKind::BoolWriteConst`

前两条是**写侧**、而且**连实参都没有**（PC 的绑定体内嵌了常量 0/1）⇒ 既有的种类都不合用：
`BoolBitWrite` 要一个位值实参、`U32OrWithArg` 要一个掩码实参、`ColorModWrite` 要一个 `Color`。
所以新开 `BoolWriteConst = 16`：**常量在 `row->offset2`**、走 `WriteField`（受保护写原语）、
返回 **0 个值**（并与其余写侧 kind 一起进 `RowReturnsNoValues` 的早退分支）。

## 宿主验到了什么、没验到什么

* **验到**（字段行没有入口指纹 ⇒ 伪造内存里的字节真被读写）：
  - ★★ **写进了"Manager 派生的那个 Music 对象"那一格**：夹具按
    `模块槽 → Manager* → Manager + kManagerMusicOffset` 三级摆好，脚本只调 API，
    **C++ 侧直接读那个字节** ⇒ "写到别处去了"会红；
  - ★ **`IsEnabled()` 读的是内存**：初始字节摆 0 它答 `false`、摆 1 它答 `true`
    （专抓「照 PC 语义硬答常量」这类错法）；
  - ★ **往返**：`true → Disable() → false → Enable() → true`，且 `Disable`/`Enable`
    都返回 **0 个值**（PC 是 `void`）；
  - ★ **反回归（本批最想要的一条）**：把 `Disable` 那一行的 `offset2` 改成 1 ⇒
    两个写侧 API 都写 1 ⇒ 行为用例必须变红（见存档 README 的反证记录）；
  - **参数闸门**：`Disable(1)` / `Enable(1)` 必须报错，消息里现拼出 `MusicManager:Disable`；
  - **拿不到 Manager**：`Disable()`/`Enable()` 返回 **0 个值**、不抛错；
    `IsEnabled()` 答 **`false`（布尔、不是 nil）** —— 与 PC 的返回类型一致。
* **没验**：真机上这一格就是"音乐启用"开关（宿主里"偏移对不对"是同一张表的两处引用同一个常量，
  自己证不了自己）⇒ 真机项 = 作业单 **V55**。
"""

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import build_lua_harness
except ImportError:
    from test_support import build_lua_harness

SOURCE = Path(__file__).resolve().parent.parent / "source"
ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
MUSIC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "music_api.cpp"
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
FIELD_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "field_api.hpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
LAYOUT_MUSIC = ROOT / "tools" / "layout_tables" / "music.json"
LAYOUT_TOOL = ROOT / "tools" / "build_layout_table.py"
FIELD_ROWS_TEST = ROOT / "runtime" / "tests" / "test_field_api_rows.py"
LEDGER = ROOT / "tools" / "api_definition_of_done.json"

#: 本批三条 API 的目录序号 / 契约页:行。
APIS = (
    ("Disable", 0x0011, "MusicManager.md:40"),
    ("Enable", 0x0012, "MusicManager.md:50"),
    ("IsEnabled", 0x0013, "MusicManager.md:80"),
)
OFFSET_NAME = "kMusicEnabledOffset"
#: 夹具里那一格的初始值（1 = 启用，与 `Music::Music()` 构造出来的值一致）。
ENABLED = 1
DISABLED = 0


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 265 的 `Isaac.GetSoundIdByName` 用例，那是同一条"全局 Manager"链）：
//   模块块[base + kGameManagerGlobalSlotOffset] = &g_ManagerSlotBytes（槽里放的是**变量地址**）
//   g_ManagerSlotBytes                          = Manager*
//   Manager + kManagerMusicOffset               = Music 对象（`Manager` 的**内嵌子对象**）
//   Music  + kMusicEnabledOffset                = 本批读写的那个字节
//
// ★ `FieldReceipt::Music`（批次 239 立）就是这条链 —— 它**不从 Lua 栈上取接收者**
//   （`MusicManager()` 在 Lua 里是空占位句柄），所以夹具必须摆好这三跳，
//   否则用例只会验到"接收者解析不到"那条降级路径、验不到真正的读写。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_ManagerSlotBytes;
std::vector<unsigned char> g_ManagerBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::uintptr_t g_EngineBase = 0;

//: 模块块要盖住 `g_Manager` 那个全局槽（`0xAAC648` 附近）。
static_assert(kGameManagerGlobalSlotOffset + sizeof(std::uint64_t) <= 0xB00000,
              "fake module block sizing assumption changed");

//: `Music` 对象必须在 `Manager` 内部（`kManagerMusicOffset`），而"启用"字节又必须在 `Music` 内部。
static_assert(kManagerMusicOffset > 0 && kMusicEnabledOffset > 0,
              "both offsets must be positive");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

//: 读"那一格"—— ★ **C++ 侧独立读**（不经过 Lua、也不经过运行时的任何一层）。
std::uint8_t ReadEnabledByte() {
    return g_ManagerBytes[kManagerMusicOffset + kMusicEnabledOffset];
}

void PublishFakeManager(std::uint8_t enabled, bool publishManager) {
    g_ModuleBytes.assign(kGameManagerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_ManagerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_ManagerBytes.assign(kManagerMusicOffset + kMusicEnabledOffset + sizeof(std::uint8_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    g_ManagerBytes[kManagerMusicOffset + kMusicEnabledOffset] = enabled;
    WriteAt<std::uint64_t>(g_ManagerSlotBytes, 0, AddressOf(g_ManagerBytes));
    //: `publishManager == false` 造"拿不到 Manager"（槽里的指针是 0）。
    WriteAt<std::uint64_t>(g_ModuleBytes, kGameManagerGlobalSlotOffset,
                           publishManager ? AddressOf(g_ManagerSlotBytes) : 0);

    LuaRuntime::SetEngineModuleBase(g_EngineBase);
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = nullptr;
    return GameRoomObservation::GameNull;
}

int main(int argc, char** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc != 2) return 90;
    const char* scenario = argv[1];

    std::uint8_t enabled = 1;
    bool publishManager = true;
    const char* script = nullptr;

    // 每条场景里的 Lua 打印都用 `B305 ` 前缀，`value()` 按行取。
    static const char* kInitial =
        "local music = MusicManager()"
        " print('B305 kind=' .. type(music))"
        " print('B305 fn=' .. type(music.IsEnabled) .. ',' .. type(music.Disable) .. ','"
        " .. type(music.Enable))"
        " local a = music:IsEnabled()"
        " print('B305 initial=' .. tostring(a) .. ',' .. type(a))";
    // `Disable`：只调一次，C++ 侧直接读那一格（断言落点）。
    static const char* kDisable =
        "local music = MusicManager()"
        " print('B305 ret=' .. select('#', music:Disable()))";
    // `Enable`：先读一次（证明 `IsEnabled` 读的是内存、不是常量），再写。
    static const char* kEnable =
        "local music = MusicManager()"
        " local before = music:IsEnabled()"
        " print('B305 before=' .. tostring(before))"
        " print('B305 ret=' .. select('#', music:Enable()))";
    // 往返：true → Disable → false → Enable → true。
    static const char* kRoundtrip =
        "local music = MusicManager()"
        " print('B305 a=' .. tostring(music:IsEnabled()))"
        " print('B305 r1=' .. select('#', music:Disable()))"
        " print('B305 b=' .. tostring(music:IsEnabled()))"
        " print('B305 r2=' .. select('#', music:Enable()))"
        " print('B305 c=' .. tostring(music:IsEnabled()))";
    // 参数闸门：三条都不收实参。
    static const char* kArgs =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function msg(f) return tostring(select(2, pcall(f))) end"
        " local music = MusicManager()"
        " print('B305 disable1=' .. ok(function() return music:Disable(1) end))"
        " print('B305 disable1msg=' .. msg(function() return music:Disable(1) end))"
        " print('B305 enable1=' .. ok(function() return music:Enable(1) end))"
        " print('B305 enable1msg=' .. msg(function() return music:Enable(1) end))"
        " print('B305 isenabled1=' .. ok(function() return music:IsEnabled(1) end))"
        " print('B305 isenabled1msg=' .. msg(function() return music:IsEnabled(1) end))"
        // 合法的零参调用要真的放行（否则上面几条"报错"可能是"一律报错"造成的假绿）。
        " print('B305 disableok=' .. ok(function() return music:Disable() end))"
        " print('B305 enableok=' .. ok(function() return music:Enable() end))"
        " print('B305 isenabledok=' .. ok(function() return music:IsEnabled() end))";
    // 拿不到 Manager：两条写侧返回 0 个值、不抛错；读侧答 `false`（布尔，不是 nil）。
    static const char* kNoManager =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local music = MusicManager()"
        " print('B305 dok=' .. ok(function() return music:Disable() end))"
        " print('B305 dret=' .. select('#', music:Disable()))"
        " print('B305 eok=' .. ok(function() return music:Enable() end))"
        " print('B305 eret=' .. select('#', music:Enable()))"
        " local v = music:IsEnabled()"
        " print('B305 iok=true')"
        " print('B305 ival=' .. tostring(v) .. ',' .. type(v))";

    if (std::strcmp(scenario, "initial") == 0) {
        script = kInitial;
    } else if (std::strcmp(scenario, "initial_off") == 0) {
        script = kInitial; enabled = 0;
    } else if (std::strcmp(scenario, "disable") == 0) {
        script = kDisable;
    } else if (std::strcmp(scenario, "enable") == 0) {
        script = kEnable; enabled = 0;
    } else if (std::strcmp(scenario, "roundtrip") == 0) {
        script = kRoundtrip;
    } else if (std::strcmp(scenario, "args") == 0) {
        script = kArgs;
    } else if (std::strcmp(scenario, "nomanager") == 0) {
        script = kNoManager; publishManager = false;
    } else {
        return 91;
    }

    PublishFakeManager(enabled, publishManager);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b305.lua");
    static_cast<void>(result);
    //: ★ 结账时**独立读一次那一格**（不经过 Lua）—— 这是"到底写没写、写成了几"的判据。
    std::printf("B305 byte=%u\n", static_cast<unsigned>(ReadEnabledByte()));
    return 0;
}
'''


class MusicEnabledBatch305Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b305-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario):
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    @staticmethod
    def value(out, label):
        match = re.search(rf"^{re.escape(label)}=(\S+)$", out, re.M)
        if match is None:
            raise AssertionError(f"输出里没有 {label} 那一行：\n{out}")
        return match.group(1)

    # ---------------------------------------------------------------- 行为（宿主）

    def test_is_enabled_reads_the_byte_instead_of_a_constant(self):
        """★ `IsEnabled()` 读的是**内存里那一格**，不是照 PC 语义硬答。

        夹具把那一格摆成 1 与 0 各跑一次：1 ⇒ `true`、0 ⇒ `false`。
        ★ 若实现写成"恒 `true`"或"恒 `false`"，两次里必有一次红。
        """
        out = self.run_scenario("initial")
        self.assertIn("B305 kind=userdata", out)
        self.assertIn("B305 fn=function,function,function", out)
        self.assertIn("B305 initial=true,boolean", out)
        self.assertEqual(self.value(out, "B305 byte"), "1")

        out = self.run_scenario("initial_off")
        self.assertIn("B305 initial=false,boolean", out)
        self.assertEqual(self.value(out, "B305 byte"), "0")

    def test_disable_writes_zero_into_the_music_object(self):
        """★★ `Disable()` 把那一格写成 **0**，写的是**接收者自己**（Manager 派生的 Music）。

        ★ C++ 侧直接读那一格（`B305 byte`）—— "写到别处去了" 或 "没写" 都会红。
        """
        out = self.run_scenario("disable")
        self.assertEqual(self.value(out, "B305 byte"), str(DISABLED))
        self.assertEqual(self.value(out, "B305 ret"), "0", "PC 是 `void` ⇒ 必须返回 0 个值")

    def test_enable_writes_one_into_the_music_object(self):
        """★★ `Enable()` 把那一格写成 **1**（初值摆 0 ⇒ 只有真写了才会变 1）。"""
        out = self.run_scenario("enable")
        self.assertIn("B305 before=false", out)
        self.assertEqual(self.value(out, "B305 ret"), "0", "PC 是 `void` ⇒ 必须返回 0 个值")
        self.assertEqual(self.value(out, "B305 byte"), str(ENABLED))

    def test_disable_enable_round_trip(self):
        """★★ 端到端往返：`true → Disable() → false → Enable() → true`，两个写侧各 0 个返回值。

        ★ 这一条抓的是"两条写侧写进了同一个值"（例如 `offset2` 都用 1）——
        那样 `b` 会是 `true`（Disable 没写 0）⇒ 红。
        """
        out = self.run_scenario("roundtrip")
        self.assertIn("B305 a=true", out)
        self.assertIn("B305 r1=0", out)
        self.assertIn("B305 b=false", out)
        self.assertIn("B305 r2=0", out)
        self.assertIn("B305 c=true", out)
        self.assertEqual(self.value(out, "B305 byte"), str(ENABLED))

    def test_argument_gate(self):
        """三条都**不收实参**：多给一个必须报错、消息里现拼出 `owner:name`；零参必须放行。"""
        out = self.run_scenario("args")
        self.assertIn("B305 disable1=false", out)
        self.assertIn("MusicManager:Disable accepts no arguments", out)
        self.assertIn("B305 enable1=false", out)
        self.assertIn("MusicManager:Enable accepts no arguments", out)
        self.assertIn("B305 isenabled1=false", out)
        self.assertIn("MusicManager:IsEnabled accepts no arguments", out)
        self.assertIn("B305 disableok=true", out)
        self.assertIn("B305 enableok=true", out)
        self.assertIn("B305 isenabledok=true", out)
        #: 被拒的调用不许写内存（夹具初值是 1 ⇒ 仍是 1）。
        self.assertEqual(self.value(out, "B305 byte"), str(ENABLED))

    def test_missing_manager_degrades_per_pc_return_type_without_erroring(self):
        """★ 拿不到 `Manager` ⇒ **不报错**，按 PC 的返回类型降级。

        * 两条**写侧**（`void`）⇒ 返回 **0 个值**（`RowReturnsNoValues` 那条早退分支）
          —— 改之前通用分支会多压一个降级值返回 1，`select('#', …)` 会从 0 变 1；
        * 读侧（`boolean`）⇒ 答 **`false`**，而且必须是**布尔**（nil 会让模组 `if x then` 判错、
          甚至把整条回调摘掉）。
        """
        out = self.run_scenario("nomanager")
        self.assertIn("B305 dok=true", out)
        self.assertEqual(self.value(out, "B305 dret"), "0")
        self.assertIn("B305 eok=true", out)
        self.assertEqual(self.value(out, "B305 eret"), "0")
        self.assertIn("B305 ival=false,boolean", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行形状 / 新 kind / 早退分支 / 偏移常量字面值。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        music = MUSIC_API.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        header = FIELD_HEADER.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        for name, index, _page in APIS:
            with self.subTest(api=f"MusicManager:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Music, 1, 0x{index:04X}), ApiDomain::Music, "MusicManager", '
                    f'"{name}"',
                    catalog, f"目录里没有 MusicManager:{name}（域内序号 0x{index:04x}）")

        #: 数据行形状：写侧两条是 `BoolWriteConst` + `offset2` 0/1；读侧是 `Bool`。
        self.assertRegex(
            music,
            rf"\{{\s*(?i:0x06010011),\s*{OFFSET_NAME},\s*(?:0x00|0),\s*"
            rf"FieldKind::BoolWriteConst,\s*FieldMissing::False,\s*FieldReceipt::Music,\s*0xFF\}}",
            "Disable 的数据行缺失或形状不对")
        self.assertRegex(
            music,
            rf"\{{\s*(?i:0x06010012),\s*{OFFSET_NAME},\s*(?:0x01|1),\s*"
            rf"FieldKind::BoolWriteConst,\s*FieldMissing::False,\s*FieldReceipt::Music,\s*0xFF\}}",
            "Enable 的数据行缺失或 `offset2` 不是 1")
        self.assertRegex(
            music,
            rf"\{{\s*(?i:0x06010013),\s*{OFFSET_NAME},\s*(?:0x00|0),\s*"
            rf"FieldKind::Bool,\s*FieldMissing::False,\s*FieldReceipt::Music,\s*0xFF\}}",
            "IsEnabled 的数据行缺失或形状不对")
        #: ★ 反回归：这三条**不许**被塞进引擎方法行表（引擎里没有同名成员函数）。
        self.assertNotRegex(music, rf"0x0601001[123][^\n]*EngineCallShape")
        #: 三条一起挂到同一个 owner 上（少挂一条就是"方法不存在"）。
        self.assertIn("kMusicFieldApis", music)
        self.assertRegex(music, r"sizeof\(kMusicFieldApis\) / sizeof\(kMusicFieldApis\[0\]\)")

        #: 新 kind 登记 + 共享处理器认它 + 进"返回 0 个值"的早退分支。
        self.assertRegex(header, rf"BoolWriteConst\s*=\s*16,")
        self.assertIn("case FieldKind::BoolWriteConst", isaac)
        self.assertRegex(isaac, r"RowReturnsNoValues\(FieldKind kind\)[\s\S]{0,260}BoolWriteConst")
        #: 写侧必须走受保护写原语（不是裸 `memcpy` / 裸指针赋值）。
        block = isaac[isaac.index("case FieldKind::BoolWriteConst"):]
        block = block[:block.index("case FieldKind::ColorModWrite")]
        self.assertIn("engine_memory::WriteField", block, "写侧必须走 `WriteField`")
        self.assertIn("IsEngineMemoryWritable", block, "写侧必须过 `IsEngineMemoryWritable`")

        #: ★ 偏移常量写死（接线用例的职责就是钉**字面值**；行为用例钉"行指向哪一格"）。
        self.assertRegex(constants,
                         rf"inline constexpr uintptr_t {OFFSET_NAME}\s*=\s*0x3F0;")
        #: ★★ 反回归：**不许平移 PC 的 `0x328`**，而且那句话要留在常量旁边。
        self.assertNotRegex(constants, rf"inline constexpr uintptr_t {OFFSET_NAME}\s*=\s*0x328;")
        self.assertIn("0x328", constants, "取证里必须留下 PC 的 `+0x328`（两条独立证据的对照）")
        self.assertIn("不许平移", constants, "必须写明「偏移不许平移」这条纪律")

    def test_layout_row_is_confirmed_with_named_consumers(self):
        """★ 布局表那一行必须 `confirmed`，且带**具名**写入方与消费者（作业单 G4 的前置动作）。"""
        table = json.loads(LAYOUT_MUSIC.read_text(encoding="utf-8"))
        self.assertEqual(table["struct"], "Music")
        rows = {row["name"]: row for row in table["rows"]}
        self.assertIn("Enabled", rows, "布局表里没有 Enabled 行")
        row = rows["Enabled"]
        self.assertEqual(row["confidence"], "confirmed")
        self.assertEqual(row["offset"], 0x3F0)
        self.assertEqual(row["width"], 1)
        kinds = [entry["kind"] for entry in row["evidence"]]
        self.assertIn("semantic", kinds, "Enabled 行缺少取值锚点（semantic 证据）")
        cited = [entry["function"] for entry in row["evidence"]]
        for function in (
                "_ZN15IsaacRepentance5MusicC2Ev",      # 构造函数（具名写入方 + 取值锚点）
                "_ZN15IsaacRepentance5Music6UpdateEv"):  # Update 里的闸（具名消费者）
            self.assertIn(function, cited, f"Enabled 行缺少 {function} 的证据")

    def test_layout_evidence_reproduces_against_the_fixed_nro(self):
        """布局表的每条证据都要能重新反汇编核对（`--verify`）。"""
        nro = ROOT / (
            "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
            "/Program #0/1/.nro/Repentance.nro")
        if not nro.is_file():
            self.skipTest("仓库里没有游戏镜像（公开仓库不带游戏资源）")
        result = subprocess.run(
            ["python3", str(LAYOUT_TOOL), "--table", str(LAYOUT_MUSIC), "--verify"],
            text=True, capture_output=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("通过", result.stdout)

    def test_music_api_file_is_registered_in_the_field_row_gate(self):
        """★★ 忘了登记 `music_api.cpp` 那张表 ⇒ 整个文件对门禁**隐形**（静默）。

        `test_field_api_rows.py` 是"哪些 TU 里有字段数据行、各自允许哪些 owner"的**唯一**台账；
        新开一张表必须同时改它（`ROW_TABLES`）与 `OWNERS_BY_RECEIPT`。这一条把"漏登记"钉成红。
        """
        gate = FIELD_ROWS_TEST.read_text(encoding="utf-8")
        self.assertIn("kMusicFieldApis", gate, "门禁里没登记 kMusicFieldApis")
        self.assertIn('"Music": {"MusicManager"}', gate, "OWNERS_BY_RECEIPT 里没加 Music")
        self.assertRegex(gate, r'"Music"\s*:\s*0x06', "域字节没登记（新 owner 会被判 not in catalog）")
        self.assertRegex(gate, r'"Music"\s*:\s*0x1000', "偏移上限没登记（0x3F0 会被判越界）")

    def test_definition_of_done_rows_carry_the_layout_field(self):
        """★ 每条 API 的 `provenance.field` 必须指向布局表那一行（`engine_field` 的硬要求）。

        ★ `rows` 是**字典**（`"owner:name"` → 四栏），不是列表 —— 按 key 找即可。
        """
        ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
        rows = ledger["rows"]
        for api_name, _index, _page in APIS:
            with self.subTest(api=api_name):
                key = f"MusicManager:{api_name}"
                self.assertIn(key, rows, f"台账里没有 {key}")
                provenance = rows[key].get("provenance") or {}
                self.assertEqual(provenance.get("kind"), "engine_field",
                                 f"{key} 的 provenance 必须是 engine_field")
                self.assertEqual(provenance.get("field"), "Music.Enabled",
                                 f"{key} 的 provenance.field 必须是 Music.Enabled")
                self.assertIn("kMusicEnabledOffset", provenance.get("offsets", []),
                              f"{key} 的 provenance.offsets 必须列出偏移常量")
                boundary = rows[key].get("boundary") or {}
                self.assertEqual(boundary.get("judgement"),
                                 "runtime/tests/test_lua_batch305_music_enabled.py",
                                 f"{key} 的边界判据必须指向本批用例")


if __name__ == "__main__":
    unittest.main()
