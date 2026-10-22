"""门禁：`GridEntity:GetGridIndex` + 7 条子类转换（批次 276，2026-10-02）。

## 这一批是什么

| API | 调用点 | 依据 |
| --- | --- | --- |
| `GridEntity:GetGridIndex()` | 4 | 读 `GridEntity + 0x28`（`kGridEntityGridIndexOffset`，早有取证） |
| `GridEntity:ToPit/ToRock/ToDoor/ToTNT/ToPoop/ToPressurePlate/ToSpikes()` | 4/4/3/2/1/1/1 | **vtable 判据**，与 `Entity:ToPlayer()` 一族逐字相同 |

★ 7 条转换的 vtable 常量**不用一条条反汇编去挖**：7 个子类的 `_ZTV` 符号全在 dynsym 里，
而「vtable 指针 = `_ZTV` 地址 **+ 0x10**」这条式子**已经被既有常量验证过**
（`kEntityPlayerVtableOffset = 0xA37110` ↔ `_ZTV…Entity_PlayerE` 在 `0xA37100`；Familiar/Tear 也一样）。

★ **命中时给的是基类 `GridEntity` 视图**（子类视图我们还没有 —— 与 `Entity:ToFamiliar()` 压 `Entity`
元表是同一个先例）。代价说清：`grid:ToRock():UpdateAnimFrame()` 这类**子类专有方法**仍然拿不到；
但语料里把转换**当真假判断**用的那些点（`if grid:ToPoop() then … elseif grid:ToTNT() then …`）
从这一批起能正常走 —— G0 里那两条子类方法也会照旧列在待办里，不会被"假装做完"。

## 本文件为什么是「真验证」

夹具里那个假网格实体的**首字是我们自己设的**（设成 Rock 的 vtable）⇒ 宿主上可以直接验：
`ToRock()` 命中、其余六条给 `nil`；`GetGridIndex()` 读出我们写进去的那个下标。
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
REMAINING_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"

GRID_WIDTH = 13
GRID_INDEX = 20

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 假房间 + 假网格实体（形状抄 `test_lua_grid_entity_fields.py`）：`Room + kRoomGridEntityTableOffset`
// 是按网格下标索引的指针表；拿到句柄才能真的把 `GridEntity:Init` 调起来。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_RoomBytes;
std::vector<unsigned char> g_EntityBytes;

constexpr std::uint32_t kGridWidth = GRID_WIDTH;
constexpr std::uint32_t kGridIndex = GRID_INDEX;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void PublishFakeRoom() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EntityBytes.assign(0x48, 0);
    WriteAt<std::uint32_t>(g_EntityBytes, kGridEntityTypeOffset, 6);
    // 首字是 vptr（`GridEntity::Init` 里 `ldr x8,[x0]` 印证）—— 设成 **Rock 子类**的 vtable，
    // 这样 `ToRock()` 应当命中、其它六条应当给 nil。
    WriteAt<std::uintptr_t>(g_EntityBytes, 0,
                            AddressOf(g_ModuleBytes) + kGridEntity_RockVtableOffset);
    WriteAt<std::uint32_t>(g_EntityBytes, kGridEntityGridIndexOffset, GRID_INDEX);
    const std::size_t tableOffset = kRoomGridEntityTableOffset + kGridIndex * sizeof(std::uintptr_t);
    g_RoomBytes.assign(tableOffset + sizeof(std::uintptr_t) + 8, 0);
    WriteAt<std::uint32_t>(g_RoomBytes, kRoomGridWidthOffset, kGridWidth);
    WriteAt<std::uintptr_t>(g_RoomBytes, tableOffset, AddressOf(g_EntityBytes));
    WriteAt<std::uintptr_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uintptr_t>(g_OwnerSlotBytes, 0, AddressOf(g_RoomBytes));
    LuaRuntime::SetEngineModuleBase(AddressOf(g_ModuleBytes));
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = reinterpret_cast<void*>(AddressOf(g_RoomBytes));
    return GameRoomObservation::Success;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    PublishFakeRoom();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script = nullptr;
    if (std::strcmp(scenario, "cast") == 0) {
        script =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local ge = Game():GetRoom():GetGridEntity(GRID_INDEX)"
            " print('B276 idx=' .. tostring(ge:GetGridIndex()))"
            " print('B276 rock=' .. type(ge:ToRock()) .. ',' .. tostring(ge:ToPoop() == nil)"
            "   .. ',' .. tostring(ge:ToPit() == nil) .. ',' .. tostring(ge:ToDoor() == nil)"
            "   .. ',' .. tostring(ge:ToTNT() == nil) .. ',' .. tostring(ge:ToPressurePlate() == nil)"
            "   .. ',' .. tostring(ge:ToSpikes() == nil))"
            " local rock = ge:ToRock()"
            " print('B276 castview=' .. tostring(rock ~= nil and rock:GetType() == ge:GetType()))"
            " print('B276 arity=' .. ok(function() return ge:GetGridIndex(1) end)"
            "   .. ',' .. ok(function() return ge:ToRock(1) end)"
            "   .. ',' .. ok(function() return ge:ToPoop(1) end))";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b272.lua");
    static_cast<void>(result);
    return 0;
}'''

HARNESS = HARNESS.replace("GRID_WIDTH", str(GRID_WIDTH)).replace("GRID_INDEX", str(GRID_INDEX))


class GridEntityCastBatch276Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b276-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario: str) -> str:
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    # ---------------------------------------------------------------- 行为（真验证）

    def test_grid_index_reads_the_field_we_wrote(self):
        """`GetGridIndex()` 必须读出夹具里写进 `+0x28` 的那个下标（20）。"""
        out = self.run_scenario("cast")
        self.assertIn("B276 idx=20", out)

    def test_only_the_matching_subclass_cast_succeeds(self):
        """★ 夹具把首字设成 **Rock** 的 vtable ⇒ 只有 `ToRock()` 该命中、其余六条该给 `nil`。

        这一格同时验三件事：vtable 常量的值对、判据是「首字相等」、不命中走 `nil`。
        """
        out = self.run_scenario("cast")
        self.assertIn("B276 rock=userdata,true,true,true,true,true,true", out)

    def test_cast_result_is_still_a_usable_grid_entity_view(self):
        """命中时给的是**基类视图** —— 它上面的 `GridEntity` 方法必须照样能用。"""
        out = self.run_scenario("cast")
        self.assertIn("B276 castview=true", out)

    def test_argument_gates(self):
        """0 参方法多给实参必须报错。"""
        out = self.run_scenario("cast")
        self.assertIn("B276 arity=false,false,false", out)

    # ---------------------------------------------------------------- 静态接线

    def test_catalog_and_binding_rows_exist(self):
        catalog = CATALOG.read_text(encoding="utf-8")
        body = REMAINING_API.read_text(encoding="utf-8")
        rows = (("GetGridIndex", 0x00AB, "GridEntityGetGridIndex"),
                ("ToPit", 0x00AC, "GridEntityToPit"), ("ToRock", 0x00AD, "GridEntityToRock"),
                ("ToDoor", 0x00AE, "GridEntityToDoor"), ("ToTNT", 0x00AF, "GridEntityToTnt"),
                ("ToPoop", 0x00B0, "GridEntityToPoop"),
                ("ToPressurePlate", 0x00B1, "GridEntityToPressurePlate"),
                ("ToSpikes", 0x00B2, "GridEntityToSpikes"))
        for name, index, cpp in rows:
            with self.subTest(name):
                self.assertIn(f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, '
                              f'"GridEntity", "{name}"', catalog)
                self.assertRegex(body, rf"\{{\s*(?i:0x0e01{index:04x}),\s*&{cpp}\s*\}}")

    def test_the_seven_vtables_come_from_one_documented_formula(self):
        """★ 7 个 vtable 常量必须在，且常量段里写着「`_ZTV` + 0x10」这条式子与它的验证锚点。"""
        constants = CONSTANTS.read_text(encoding="utf-8")
        for cls in ("GridEntity_Pit", "GridEntity_Rock", "GridEntity_Door", "GridEntity_TNT",
                    "GridEntity_Poop", "GridEntity_PressurePlate", "GridEntity_Spikes"):
            with self.subTest(cls):
                self.assertIn(f"k{cls}VtableOffset = 0x", constants)
        self.assertIn("+ 0x10", constants)
        self.assertIn("kEntityPlayerVtableOffset = 0xA37110", constants)

    def test_all_seven_casts_share_one_judgement(self):
        """七条必须共用同一个 `PushGridEntityCast()`（判据只有一份），且不命中走 `nil`。"""
        body = REMAINING_API.read_text(encoding="utf-8")
        self.assertEqual(body.count("return PushGridEntityCast(state, kGridEntity_"), 7)
        handler = body[body.index("int PushGridEntityCast("):]
        handler = handler[:handler.index("\n}\n")]
        self.assertIn("vtable != base + vtableOffset", handler)
        self.assertIn("lua_pushnil(state);", handler)


if __name__ == "__main__":
    unittest.main()
