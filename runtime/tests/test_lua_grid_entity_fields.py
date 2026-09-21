"""`GridEntity` 的**字段**面（`Position` / `VarData` / `Desc`）—— 献祭房那条 bug 的门禁。

## 这个测试解决什么问题

用户 2026-09-21 报"EID 在特殊房间（献祭房）不会有该房间的信息显示"。根因链：

1. EID 里跟"房间信息"有关的显示只有**网格实体描述**这一族，而它**只给 `GRID_SPIKES` 注册**
   （`features/eid_grid_descriptions.lua:115/133`，条件是"当前房间类型 = 献祭房(13)"）
   ⇒ 这一族只在**带刺的房间**露脸；
2. EID 每帧挑"离玩家最近的实体"时，对每个**有描述**的网格实体取位置
   （`main.lua:1491` 的 `gridEntity.Position:__sub(sourcePos)`）；
3. 而我们过去给**非门的**网格实体只挂了三个**方法**（`GetType`/`GetVariant`/`GetRNG`），
   元表的 `__index` 是一张纯方法表 ⇒ `gridEntity.Position` 是 `nil` ⇒ `nil:__sub` 抛错
   ⇒ **那一帧的描述整段不画**（不崩、屏幕上也没提示）。

PC 契约里 `GridEntity` 有这几个字段（IsaacDocs `GridEntity.md` 的 Variables）：
`Position`（`const Vector`）、`Desc`、`VarData`、`State`、`CollisionClass`。
本测试钉住我们能给的那三个（前三个），并要求**缺能力时报错而不是编值**。

## 断言口径

1. `Position` **来自引擎调用**（宿主注入替身返回"按网格下标算出来的位置"）：
   `(idx % W + 1) * 40`、`(idx / W) * 40 + 120` —— 与引擎 `Room::GetGridPosition` 的公式一致；
   我们**不自己按格子拼**，所以这里注入什么就得读到什么；
2. **引擎入口不可用时必须报错**（`pcall` 失败），不许退化成 `(0,0)`：
   编一个坐标会让 EID 挑错实体 —— 那正是"条件为假、不报错"的最难查形态；
3. `VarData` 读 `GridEntity + 0x1C`（献祭房回调紧接着要用它：`descObj.Entity.VarData + 1`）；
4. `Desc` 给已取证的三个字段（`Type`/`Variant`/`VarData`），没取证的不编；
5. **方法面不许回退**：`ge:GetType()` / `ge:GetVariant()` 仍然可用（`__index` 从表改成函数之后，
   方法表挪到了元表的 `__methods`，这条就是那个改动的回归判据）。
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import build_lua_harness
except ImportError:
    from test_support import build_lua_harness


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

#: 假网格实体：一格刺（`GridEntityType.GRID_SPIKES` = 8），`VarData` = 7（献祭房"下一次奖励"的计数）。
GRID_INDEX = 31          # 13 宽 ⇒ 格 (5,2)
GRID_WIDTH = 13
SPIKE_TYPE = 8
SPIKE_VARIANT = 0
SPIKE_VAR_DATA = 7
EXPECTED_X = (GRID_INDEX % GRID_WIDTH + 1) * 40   # 240
EXPECTED_Y = (GRID_INDEX // GRID_WIDTH) * 40 + 120  # 200


def lua_number(value: int) -> str:
    """Lua 的 `tostring` 把浮点整值打成 `240.0`（`Position` 是 float，与 `GetGridPath` 那类整数不同）。"""
    return f"{value}.0"

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_RoomBytes;
std::vector<unsigned char> g_EntityBytes;
bool g_PositionAvailable = true;

constexpr std::uint32_t kGridWidth = GRID_WIDTH;
constexpr std::uint32_t kGridIndex = GRID_INDEX;
constexpr std::uint32_t kSpikeType = SPIKE_TYPE;
constexpr std::uint32_t kSpikeVariant = SPIKE_VARIANT;
constexpr std::uint32_t kSpikeVarData = SPIKE_VAR_DATA;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

// 宿主替身：模仿引擎的公式（`Room::GetGridPosition`，证据见 `runtime_constants.hpp` 里
// `kGridEntityGridIndexOffset` 与 `kGridEntityGetPositionOffset` 两段注释）。
// 位置**由网格下标算出来**，网格实体自己只存下标 —— 所以这里读 +0x28 再算。
void FakeGetPosition(const void* entity, float* x, float* y) {
    std::uint32_t index = 0;
    std::memcpy(&index,
                reinterpret_cast<const unsigned char*>(entity) + kGridEntityGridIndexOffset,
                sizeof(index));
    const std::uint32_t column = index % kGridWidth;
    const std::uint32_t row = index / kGridWidth;
    *x = static_cast<float>(column + 1) * 40.0F;
    *y = static_cast<float>(row) * 40.0F + 120.0F;
}

void PublishFakeRoom() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EntityBytes.assign(0x48, 0);
    WriteAt<std::uint32_t>(g_EntityBytes, kGridEntityTypeOffset, kSpikeType);
    WriteAt<std::uint32_t>(g_EntityBytes, kGridEntityVariantOffset, kSpikeVariant);
    WriteAt<std::uint32_t>(g_EntityBytes, kGridEntityVarDataOffset, kSpikeVarData);
    WriteAt<std::uint32_t>(g_EntityBytes, kGridEntityGridIndexOffset, kGridIndex);
    WriteAt<std::uint32_t>(g_EntityBytes, kGridEntityRngOffset, 0x12345678u);

    // 假房间：`Room + 0x30` 是网格实体表（按网格下标索引，每项一个指针）。
    const std::size_t tableOffset = kRoomGridEntityTableOffset + kGridIndex * sizeof(std::uintptr_t);
    g_RoomBytes.assign(tableOffset + sizeof(std::uintptr_t) + 8, 0);
    WriteAt<std::uint32_t>(g_RoomBytes, kRoomGridWidthOffset, kGridWidth);
    WriteAt<std::uintptr_t>(g_RoomBytes, tableOffset, AddressOf(g_EntityBytes));

    WriteAt<std::uintptr_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uintptr_t>(g_OwnerSlotBytes, 0, AddressOf(g_RoomBytes));
    LuaRuntime::SetEngineModuleBase(AddressOf(g_ModuleBytes));
}

}  // namespace

// 覆盖共享默认桩：本场景只关心"当前房间"，游戏对象那条链用最简单的方式接上
// （与 `test_lua_room_grid.py` 同一形态）。
GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = reinterpret_cast<void*>(AddressOf(g_RoomBytes));
    return GameRoomObservation::Success;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    g_PositionAvailable = std::strcmp(scenario, "no_position") != 0;

    PublishFakeRoom();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);
    if (g_PositionAvailable) {
        LuaRuntime::SetGridEntityGetPositionHostFunction(&FakeGetPosition);
    }

    const char* script = nullptr;
    if (std::strcmp(scenario, "fields") == 0) {
        script =
            "local room = Game():GetRoom()"
            " local ge = room:GetGridEntity(GRID_INDEX)"
            " print('METHODS='..tostring(ge:GetType())..','..tostring(ge:GetVariant()))"
            " print('VARDATA='..tostring(ge.VarData))"
            " local desc = ge.Desc"
            " print('DESC='..tostring(desc.Type)..','..tostring(desc.Variant)..','"
            " ..tostring(desc.VarData))"
            " local p = ge.Position"
            " print('POS='..tostring(p.X)..','..tostring(p.Y))";
    } else if (std::strcmp(scenario, "no_position") == 0) {
        // 引擎入口不可用：`Position` 必须**报错**，不许给 (0,0)；其它字段照常可读。
        script =
            "local room = Game():GetRoom()"
            " local ge = room:GetGridEntity(GRID_INDEX)"
            " local ok, err = pcall(function() return ge.Position end)"
            " print('POSITION_OK='..tostring(ok)..' ERR='..tostring(err))"
            " print('VARDATA='..tostring(ge.VarData)..' TYPE='..tostring(ge:GetType()))";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script),
                                                         "@gridentity.lua");
    static_cast<void>(result);
    return 0;
}
'''


class LuaGridEntityFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-gridentity-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS.replace("GRID_INDEX", str(GRID_INDEX))
                                 .replace("GRID_WIDTH", str(GRID_WIDTH))
                                 .replace("SPIKE_TYPE", str(SPIKE_TYPE))
                                 .replace("SPIKE_VARIANT", str(SPIKE_VARIANT))
                                 .replace("SPIKE_VAR_DATA", str(SPIKE_VAR_DATA)),
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(self.binary), scenario], text=True, capture_output=True)

    def test_fields_come_from_the_engine_and_methods_still_work(self):
        """`Position` 来自引擎调用（注入什么读什么）；`VarData`/`Desc` 读已取证偏移。

        这条**同时**是"`__index` 由表改成函数"的回归判据：`GetType`/`GetVariant` 必须照旧可用
        （它们现在住在元表的 `__methods` 里）。
        """
        result = self.run_scenario("fields")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"METHODS={SPIKE_TYPE},{SPIKE_VARIANT}", result.stdout)
        self.assertIn(f"VARDATA={SPIKE_VAR_DATA}", result.stdout)
        self.assertIn(f"DESC={SPIKE_TYPE},{SPIKE_VARIANT},{SPIKE_VAR_DATA}", result.stdout)
        self.assertIn(f"POS={lua_number(EXPECTED_X)},{lua_number(EXPECTED_Y)}", result.stdout)

    def test_missing_engine_entry_reports_instead_of_faking_coordinates(self):
        """引擎入口不可用 ⇒ `Position` 报错（EID 会看到一行错），而不是编一个 `(0,0)`。

        编值的代价：EID 用它算"离玩家最近的刺"，恒 `(0,0)` 会让它**挑错实体**
        （"条件为假、不报错"是最难查的一类缺陷）。同一场景下 `VarData`/`GetType` 必须照常工作。
        """
        result = self.run_scenario("no_position")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("POSITION_OK=false", result.stdout)
        self.assertIn("VARDATA=", result.stdout)
        self.assertIn(f"TYPE={SPIKE_TYPE}", result.stdout)


if __name__ == "__main__":
    unittest.main()
