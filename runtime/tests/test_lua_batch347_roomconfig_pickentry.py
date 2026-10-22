"""门禁：批次 347（2026-10-04）—— `RoomConfigSpawn:PickEntry(float r)`（2 处）+ 四件前置。

## 这一批是什么

| 件 | 内容 |
| --- | --- |
| ① | `RoomDescriptor.Data.Spawns` 从**明确空容器**（`Size=0`、`Get` 恒 `nil`）换成**真容器** |
| ② | `RoomConfigSpawn` 句柄 + 元表 + 视图（`SumWeights` / `EntryCount` 两个属性 + `PickEntry` 方法） |
| ③ | `RoomConfigEntry` 句柄 + 元表 + 视图（`Type` / `Variant` / `SubType` / `Weight` 四个属性） |
| ④ | `RoomConfigSpawn:PickEntry(float r)` **手写处理器**（真身 `@ 0x494910`，入口字 `0xA9BE7BFD`） |

依据 = `docs/取证-P组-PickEntry可执行规格-20261004e.md`（本批的完整可执行规格；
它同时更正了 J 组三处：`Spawns` 的 end/cap **不存在**（不是 vector）、`X`/`Y` **有 candidate 级偏移**、
两种 `FieldKind` **根本不存在**）。

## 本批的核心判据（宿主里可验）

1. ★★ **`Spawns` 的计数与边界**：`Size` = `Data + 0x58` 的 **u16 计数**（不是 `end - begin`）；
   `Get(0..count-1)` 给 userdata、`Get(count)` / `Get(-1)` 给 `nil`（PC 的 ArrayProxy 越界取不到）。
2. ★★ **`Variant`/`SubType` 按 i16 符号扩展**：替身放 `0xFFFF` ⇒ 读回来必须是 **`-1`**
   （PC 的类型是 `int`；若按零扩展读会答 `65535`，与 PC 不一致）—— 这条同时钉住那条 `design` 偏离。
3. ★ **两个属性**：`SumWeights`（f32 `+0x14`）与 `EntryCount`（u8 `+0x10`）取的是**那一格**。
4. ★ **`PickEntry` 的接线与闸门**：方法真的挂上了；`r` 非数值 / 缺参 / 多给都报错；
   接收者不是 `RoomConfigSpawn`（拿别的句柄当 `self`）⇒ 报错（不野读）。
5. ★ **`Data == 0` 不退化**：`Size == 0`、`Get(0) == nil`（旧空容器的行为**经同一个函数**保留）。
6. ★ **`spawn.X` 仍然是 `nil`**：PC 有这个变量，Switch 侧那两个偏移只有 `candidate` 级证据
   ⇒ 本批有意不做（已并入偏离登记）—— 这条把"我们没偷偷编一个值"钉住。

## 没验到的（真机项）

* `Data.Spawns.Size` 与**真实**房间生成表的条数一致；`Get(i):PickEntry(r)` 答出引擎真正会生成的
  候选（拿 MinimapAPI 的特殊图标路径端到端验）。
* `r` 域外不夹取 / 不报错（透传引擎）这一条：宿主里引擎调用被注入替身替代 ⇒ 只能在真机看
  「`r` 只参与 `r * SumWeights` 的比较」。
* `Variant` 超出 i16 范围的条目：真机找一个负 Variant 的生成条目，确认答 `-1` 而非 `65535`。

## ★ 关于本文件的宿主注入

`PickEntry` 在宿主里**必然降级**（没有引擎可调；而且**绝不能**让入口字核对通过 ——
那样 `AsFunction` 会把假模块块里的字节当函数跳进去）。而 ③ 的属性**只能靠真的拿到一个 Entry
句柄**才验得到 ⇒ 本批加了一个**只在宿主构建里存在**的注入点
（`SetRoomConfigSpawnPickEntryHostImplementation`，与 `isaac_api.hpp` 里那几个
`Set*HostImplementation` 同一口径）。设备构建里那段代码不参与编译。
"""

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
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
HANDLES = ROOT / "runtime" / "source" / "lua_object_handles.hpp"
DEVIATIONS = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_deviation.cpp"
REMAINING_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"

#: 替身数据（**各组刻意取不同值** ⇒ 读错格会立刻红）。
SPAWN_COUNT = 2
SPAWN0_SUM_WEIGHTS = 3.5
SPAWN0_ENTRY_COUNT = 2
SPAWN1_SUM_WEIGHTS = 1.25
SPAWN1_ENTRY_COUNT = 1
#: 条目 0 的 `Variant` 放 `0xFFFF` ⇒ **必须读成 `-1`**（i16 符号扩展那条判据的钉子）。
ENTRY0 = (5, 0xFFFF, 7, 0.25)
ENTRY1 = (9, 3, 4, 0.75)
ENTRY2 = (1, 0, 0, 1.0)

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "lua_runtime_state.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// ---- 伪造引擎内存（形状抄 `test_lua_room_descriptor.py` 的夹具）-------------------------------
//
// 解析链（与实现、与真机探针一致，**两解**）：
//   `GameOwnerSlot()`（= 模块映像 + kGameOwnerGlobalSlotOffset，是**槽的地址**）
//     → `*(槽)` = owner → `*(owner)` = Game*（= Level*）
// 描述符数组**内联在 Level 对象里**（真机布局：基址 `Level + 0x18`、步长 `0x100`）；
// 槽位的 `+0x10` 是 `RoomConfig::Room*`（= `Data`）。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerBytes;
std::vector<unsigned char> g_GamePointerBytes;
std::vector<unsigned char> g_LevelBytes;
std::vector<unsigned char> g_ConfigBytes;   // RoomConfig::Room（= Data）
std::vector<unsigned char> g_SpawnBytes;    // RoomConfig::Spawn 数组（步长 0x18）
std::vector<unsigned char> g_EntryBytes;    // RoomConfig::Entry 数组（步长 0x0C）

//: 批次 049 的成例：当前"进入格"索引；槽 0 的 GridIndex 与它相等 ⇒ 扫描直接命中。
constexpr std::uint32_t kCurrentIndex = 84;
constexpr std::uint32_t kCurrentDimension = 0;
constexpr std::uint32_t kArrayBase = 0x18;
constexpr std::uint32_t kStride = 0x100;
//: `data_missing` 场景：把当前槽的 `Data` 指针写成 0（旧空容器那条路要**经同一个函数**保留）。
bool g_ZeroDataPointer = false;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

void WriteWord(std::vector<unsigned char>& block, std::size_t offset, std::uint64_t value) {
    WriteAt(block, offset, value);
}

void WriteF32(std::vector<unsigned char>& block, std::size_t offset, float value) {
    std::memcpy(block.data() + offset, &value, sizeof(value));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

std::uintptr_t SpawnAddress(int index) {
    return AddressOf(g_SpawnBytes) + static_cast<std::size_t>(index) * kRoomConfigSpawnStride;
}

std::uintptr_t EntryAddress(int index) {
    return AddressOf(g_EntryBytes) + static_cast<std::size_t>(index) * kRoomConfigEntryStride;
}

void PublishFakeEngine() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_OwnerBytes.assign(sizeof(std::uint64_t), 0);
    g_GamePointerBytes.assign(sizeof(std::uint64_t), 0);
    g_LevelBytes.assign(0x21520, 0);
    g_ConfigBytes.assign(0x60, 0);
    g_SpawnBytes.assign(kRoomConfigSpawnStride * 2, 0);
    g_EntryBytes.assign(kRoomConfigEntryStride * 3, 0);

    WriteWord(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_GamePointerBytes));
    WriteWord(g_OwnerBytes, 0, AddressOf(g_GamePointerBytes));
    WriteWord(g_GamePointerBytes, 0, AddressOf(g_LevelBytes));

    WriteAt<std::uint32_t>(g_LevelBytes, 0x21510, 1);   // 描述符元素个数
    WriteAt<std::uint32_t>(g_LevelBytes, kLevelCurrentRoomIndexOffset, kCurrentIndex);
    WriteAt<std::uint32_t>(g_LevelBytes, kLevelCurrentRoomDimensionOffset, kCurrentDimension);

    const std::uintptr_t slot = kArrayBase + 0 * kStride;   // 槽 0 就是当前房间
    WriteAt<std::uint32_t>(g_LevelBytes, slot + 0x00, kCurrentIndex);
    WriteAt<std::uint32_t>(g_LevelBytes, slot + 0x04, kCurrentIndex);
    WriteAt<std::uint32_t>(g_LevelBytes, slot + 0x08, kCurrentIndex);   // GridIndex
    WriteWord(g_LevelBytes, slot + 0x10,
              g_ZeroDataPointer ? 0 : AddressOf(g_ConfigBytes));

    //: `Data`（`RoomConfig::Room`）：`+0x50` = Spawn 数组首地址、`+0x58` = **u16** 计数。
    WriteWord(g_ConfigBytes, kRoomConfigRoomSpawnsBeginOffset, AddressOf(g_SpawnBytes));
    WriteAt<std::uint16_t>(g_ConfigBytes, kRoomConfigRoomSpawnCountOffset, 2);

    //: Spawn 0 / Spawn 1 的三格（`+0x00/+0x02` 的 X/Y 本批不做，故意留着）。
    WriteAt<std::int16_t>(g_SpawnBytes, 0 * kRoomConfigSpawnStride + 0x00, 1);
    WriteAt<std::int16_t>(g_SpawnBytes, 0 * kRoomConfigSpawnStride + 0x02, 2);
    WriteWord(g_SpawnBytes, 0 * kRoomConfigSpawnStride + kRoomConfigSpawnEntriesOffset,
              EntryAddress(0));
    WriteAt<std::uint8_t>(g_SpawnBytes, 0 * kRoomConfigSpawnStride + kRoomConfigSpawnEntryCountOffset,
                          2);
    WriteF32(g_SpawnBytes, 0 * kRoomConfigSpawnStride + kRoomConfigSpawnSumWeightsOffset, 3.5F);

    WriteWord(g_SpawnBytes, 1 * kRoomConfigSpawnStride + kRoomConfigSpawnEntriesOffset,
              EntryAddress(2));
    WriteAt<std::uint8_t>(g_SpawnBytes, 1 * kRoomConfigSpawnStride + kRoomConfigSpawnEntryCountOffset,
                          1);
    WriteF32(g_SpawnBytes, 1 * kRoomConfigSpawnStride + kRoomConfigSpawnSumWeightsOffset, 1.25F);

    //: 条目（步长 0x0C）：`Type` i32 / `Variant` i16 / `SubType` i16 / `Weight` f32。
    //: ★ 条目 0 的 `Variant` 是 `0xFFFF` —— 按 i16 读是 `-1`，按 u16 零扩展读是 `65535`。
    WriteAt<std::int32_t>(g_EntryBytes, 0 * kRoomConfigEntryStride + kRoomConfigEntryTypeOffset, 5);
    WriteAt<std::int16_t>(g_EntryBytes, 0 * kRoomConfigEntryStride + kRoomConfigEntryVariantOffset,
                          0xFFFF);
    WriteAt<std::int16_t>(g_EntryBytes, 0 * kRoomConfigEntryStride + kRoomConfigEntrySubTypeOffset, 7);
    WriteF32(g_EntryBytes, 0 * kRoomConfigEntryStride + kRoomConfigEntryWeightOffset, 0.25F);

    WriteAt<std::int32_t>(g_EntryBytes, 1 * kRoomConfigEntryStride + kRoomConfigEntryTypeOffset, 9);
    WriteAt<std::int16_t>(g_EntryBytes, 1 * kRoomConfigEntryStride + kRoomConfigEntryVariantOffset,
                          3);
    WriteAt<std::int16_t>(g_EntryBytes, 1 * kRoomConfigEntryStride + kRoomConfigEntrySubTypeOffset, 4);
    WriteF32(g_EntryBytes, 1 * kRoomConfigEntryStride + kRoomConfigEntryWeightOffset, 0.75F);

    WriteAt<std::int32_t>(g_EntryBytes, 2 * kRoomConfigEntryStride + kRoomConfigEntryTypeOffset, 1);
    WriteF32(g_EntryBytes, 2 * kRoomConfigEntryStride + kRoomConfigEntryWeightOffset, 1.0F);

    LuaRuntime::SetEngineModuleBase(AddressOf(g_ModuleBytes));
}

}  // namespace

#if !defined(__SWITCH__)
//: 宿主替身：假装"引擎按加权选取答了一个条目" —— 只为把 `RoomConfigEntry` 视图的属性
//: （尤其 **i16 符号扩展**那条）验到。`r < 0.5` 给第 0 个条目、否则第 1 个；Spawn 1 恒给第 2 个。
const void* HostPickEntry(std::uintptr_t spawn, float r) {
    if (spawn == SpawnAddress(1)) {
        return reinterpret_cast<const void*>(EntryAddress(2));
    }
    (void)r;
    return reinterpret_cast<const void*>(r < 0.5F ? EntryAddress(0) : EntryAddress(1));
}
#endif

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    if (std::strcmp(scenario, "data_missing") == 0) {
        g_ZeroDataPointer = true;
    } else if (std::strcmp(scenario, "main") != 0) {
        return 91;
    }
    PublishFakeEngine();
    isaac::runtime::SetRoomConfigSpawnPickEntryHostImplementation(&HostPickEntry);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerBytes), 0x2222);
    std::printf("B347 base=%d\n", AddressOf(g_ModuleBytes) != 0 ? 1 : 0);

    char script[6000];
    if (std::strcmp(scenario, "data_missing") == 0) {
        const char* s =
            "local spawns = Game():GetLevel():GetCurrentRoomDesc().Data.Spawns"
            " print('B347 dm_size=' .. tostring(spawns.Size))"
            " print('B347 dm_get0=' .. tostring(spawns:Get(0)))";
        std::snprintf(script, sizeof(script), "%s", s);
    } else {
        const char* s =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local function err(f) local a,b = pcall(f); return tostring(b) end"
            " local function f3(v) return string.format('%.3f', v) end"
            " local spawns = Game():GetLevel():GetCurrentRoomDesc().Data.Spawns"
            " print('B347 size=' .. tostring(spawns.Size))"
            " print('B347 kind0=' .. type(spawns:Get(0)))"
            " print('B347 outofrange=' .. tostring(spawns:Get(2)))"
            " print('B347 negative=' .. tostring(spawns:Get(-1)))"
            " local s0 = spawns:Get(0)"
            " local s1 = spawns:Get(1)"
            " print('B347 sum0=' .. f3(s0.SumWeights))"
            " print('B347 ec0=' .. tostring(s0.EntryCount))"
            " print('B347 sum1=' .. f3(s1.SumWeights))"
            " print('B347 ec1=' .. tostring(s1.EntryCount))"
            // ★ PC 有 `X`/`Y`，本批有意不做 ⇒ 必须是 nil（不是编出来的 0）。
            " print('B347 xy=' .. tostring(s0.X) .. ',' .. tostring(s0.Y))"
            " print('B347 pffn=' .. type(s0.PickEntry))"
            " print('B347 geterr=' .. ok(function() return spawns:Get('x') end))"
            " print('B347 geterrmsg=' .. err(function() return spawns:Get('x') end))"
            // --- PickEntry：接线 + 宿主替身答出的条目属性 ---------------------------
            " local e0 = s0:PickEntry(0.1)"
            " print('B347 e0kind=' .. type(e0))"
            " print('B347 e0type=' .. tostring(e0.Type))"
            " print('B347 e0variant=' .. tostring(e0.Variant))"
            " print('B347 e0subtype=' .. tostring(e0.SubType))"
            " print('B347 e0weight=' .. f3(e0.Weight))"
            " local e1 = s0:PickEntry(0.9)"
            " print('B347 e1variant=' .. tostring(e1.Variant))"
            " print('B347 e1subtype=' .. tostring(e1.SubType))"
            " local e2 = s1:PickEntry(0.5)"
            " print('B347 e2type=' .. tostring(e2.Type))"
            " print('B347 e2weight=' .. f3(e2.Weight))"
            // --- 参数闸门（消息里必须带本 API 的名字）--------------------------------
            " print('B347 pfnone=' .. ok(function() return s0:PickEntry() end))"
            " print('B347 pferr=' .. err(function() return s0:PickEntry() end))"
            " print('B347 pfstr=' .. ok(function() return s0:PickEntry('x') end))"
            " print('B347 pftwo=' .. ok(function() return s0:PickEntry(0, 1) end))"
            // --- 接收者类型闸：把方法取出来、拿一个别的句柄当 self -------------------
            " local f = s0.PickEntry"
            " print('B347 pfrecv=' .. ok(function() return f(Vector(0, 0), 0.5) end))";
        std::snprintf(script, sizeof(script), "%s", s);
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b347.lua");
    static_cast<void>(result);
    return 0;
}
'''


class Batch347RoomConfigPickEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b347-")
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
        # ★ 批次 285 的教训：只回 stdout 时「Lua 报错」与「什么都没做」长得一样。
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主 · 真值）

    def test_spawns_is_a_real_container_with_correct_bounds(self):
        """★★ `Spawns` 的 `Size` 走 **u16 计数**（不是 `end - begin`），边界给 `nil`。"""
        out = self.run_scenario("main")
        self.assertIn("B347 base=1", out)
        self.assertIn(f"B347 size={SPAWN_COUNT}", out)
        self.assertIn("B347 kind0=userdata", out)
        self.assertIn("B347 outofrange=nil", out)
        self.assertIn("B347 negative=nil", out)
        self.assertIn("B347 geterr=false", out)
        self.assertIn("RoomConfigSpawns:Get expects an index", out)

    def test_spawn_attributes_read_the_right_cells(self):
        """★ `SumWeights`（f32 `+0x14`）与 `EntryCount`（u8 `+0x10`）取的是**那一格**。

        两个 Spawn 的四个值**刻意都不同** ⇒ 「读错格」「复用同一个偏移」都会红。
        """
        out = self.run_scenario("main")
        self.assertIn(f"B347 sum0={SPAWN0_SUM_WEIGHTS:.3f}", out)
        self.assertIn(f"B347 ec0={SPAWN0_ENTRY_COUNT}", out)
        self.assertIn(f"B347 sum1={SPAWN1_SUM_WEIGHTS:.3f}", out)
        self.assertIn(f"B347 ec1={SPAWN1_ENTRY_COUNT}", out)
        #: ★ PC 有 `X`/`Y`，Switch 侧只有 candidate 级证据 ⇒ 本批有意不做 ⇒ 必须是 `nil`。
        self.assertIn("B347 xy=nil,nil", out)

    def test_entry_view_sign_extends_the_i16_fields(self):
        """★★ 本批最要紧的一条决定：`Variant`/`SubType` **按 i16 符号扩展**。

        替身在第 0 个条目的 `Variant` 放了 `0xFFFF` ⇒ **必须读成 `-1`**（PC 的类型是 `int`）；
        若照抄既有 `ReadRoomConfigEntryFields` 的零扩展读法，这里会答 `65535`。
        """
        out = self.run_scenario("main")
        self.assertIn("B347 pffn=function", out)
        self.assertIn("B347 e0kind=userdata", out)
        self.assertIn(f"B347 e0type={ENTRY0[0]}", out)
        self.assertIn("B347 e0variant=-1", out)
        self.assertIn(f"B347 e0subtype={ENTRY0[2]}", out)
        self.assertIn(f"B347 e0weight={ENTRY0[3]:.3f}", out)
        self.assertIn(f"B347 e1variant={ENTRY1[1]}", out)
        self.assertIn(f"B347 e1subtype={ENTRY1[2]}", out)
        self.assertIn(f"B347 e2type={ENTRY2[0]}", out)
        self.assertIn(f"B347 e2weight={ENTRY2[3]:.3f}", out)

    def test_pick_entry_gates_its_arguments(self):
        """参数闸门：缺参 / 非数值 / 多给都报错；接收者不是 `RoomConfigSpawn` 也报错。"""
        out = self.run_scenario("main")
        self.assertIn("B347 pfnone=false", out)
        self.assertIn("RoomConfigSpawn:PickEntry expects a number", out)
        self.assertIn("B347 pfstr=false", out)
        self.assertIn("B347 pftwo=false", out)
        self.assertIn("B347 pfrecv=false", out)

    def test_missing_data_keeps_the_old_empty_behaviour(self):
        """★ **`Data == 0` 不退化**：`Size == 0`、`Get(0) == nil`（旧空容器的行为经同一个函数保留）。"""
        out = self.run_scenario("data_missing")
        self.assertIn("B347 base=1", out)
        self.assertIn("B347 dm_size=0", out)
        self.assertIn("B347 dm_get0=nil", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 绑定行 / 处理器 / 10 个常量 / 两个句柄与元表 / 偏离 / 契约页。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        handles = HANDLES.read_text(encoding="utf-8")
        deviations = DEVIATIONS.read_text(encoding="utf-8")
        api = REMAINING_API.read_text(encoding="utf-8")

        self.assertIn('MakeId(ApiDomain::Room, 1, 0x0038), ApiDomain::Room, "RoomConfigSpawn", '
                      '"PickEntry"', catalog)
        self.assertIn("{0x04010038, &RoomConfigSpawnPickEntry},", api)
        self.assertRegex(api, r"int RoomConfigSpawnPickEntry\(lua_State\* state\)")
        self.assertRegex(api, r"std::uintptr_t RoomConfigSpawnPickEntryMethod\(\) noexcept")
        #: ★ 反回归：它是**手写**，不许被塞进引擎方法行 / 字段行。
        self.assertNotRegex(api, r"0x04010038[^\n]*EngineCallShape")
        self.assertNotRegex(api, r"0x04010038[^\n]*FieldKind::")

        #: ★★ 关键算式：**i16 符号扩展**（`std::int16_t`），且**不复用**那份零扩展实现。
        self.assertIn("std::int16_t value = 0;   // ★ i16 ⇒ 符号扩展", api)
        #: ★ 真容器：`Get` 是**带上值的闭包**、计数走 u16。
        self.assertRegex(api, r"lua_pushcclosure\(state, &SpawnListGet, 1\)")
        self.assertRegex(api, r"std::uint16_t count = 0;")

        for needle in (
                "inline constexpr uintptr_t kRoomConfigRoomSpawnsBeginOffset = 0x50;",
                "inline constexpr uintptr_t kRoomConfigRoomSpawnCountOffset = 0x58;",
                "inline constexpr std::size_t kRoomConfigSpawnStride = 0x18;",
                "inline constexpr uintptr_t kRoomConfigSpawnEntriesOffset = 0x08;",
                "inline constexpr uintptr_t kRoomConfigSpawnEntryCountOffset = 0x10;",
                "inline constexpr uintptr_t kRoomConfigSpawnSumWeightsOffset = 0x14;",
                "inline constexpr std::size_t kRoomConfigEntryStride = 0x0C;",
                "inline constexpr uintptr_t kRoomConfigEntryWeightOffset = 0x08;",
                "inline constexpr uintptr_t kRoomConfigSpawnPickEntryOffset = 0x494910;",
                "inline constexpr std::uint32_t kRoomConfigSpawnPickEntryEntryWord = 0xA9BE7BFDu;"):
            self.assertIn(needle, constants, f"常量缺失：{needle}")

        self.assertIn('inline constexpr char kRoomConfigSpawnMetatable[] = '
                      '"IsaacRuntime.RoomConfigSpawn";', handles)
        self.assertIn('inline constexpr char kRoomConfigEntryMetatable[] = '
                      '"IsaacRuntime.RoomConfigEntry";', handles)
        self.assertIn("struct RoomConfigSpawnHandle {", handles)
        self.assertIn("struct RoomConfigEntryHandle {", handles)

        #: 偏离必须登记（12 字节 vs 16 字节 / 缺 `X`/`Y` / 普通表 vs ArrayProxy 三条合成一条）。
        self.assertIn("{0x04010038,", deviations)
        self.assertIn("ApiDeviationKind::Partial", deviations)
        self.assertIn("性质：design（主动保留的口径差异）", deviations)

        #: 两页契约页必须**在仓里**（那条偏离引的是它们的行号）。
        for page in ("RoomConfig_Spawn.md", "RoomConfig_Entry.md",
                     "CppContainer_ArrayProxy_RoomConfigSpawns.md"):
            self.assertTrue((ROOT / "tools" / "pc_contract_docs" / page).is_file(),
                            f"契约页 {page} 不在 tools/pc_contract_docs/ 下")

    def test_the_overturned_j_group_claims_are_recorded(self):
        """★★ 本批更正了 J 组三处 —— 常量段里必须写明（后人照做时按新的走）。"""
        constants = CONSTANTS.read_text(encoding="utf-8")
        for needle in ("0x494910", "0xA9BE7BFD", "0x48F914", "0x48F918", "0x45D060", "0x488B88",
                       "不是 `std::vector`", "没有 `end`/`cap`", "KAGE_LogMessage",
                       "candidate", "符号扩展"):
            self.assertIn(needle, constants, f"证据 {needle} 没有写进常量段")


if __name__ == "__main__":
    unittest.main()
