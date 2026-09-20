"""门族门禁：`Room:GetDoor(slot)` 与 `GridEntity_Door` 的字段（批次 078，2026-09-19）。

## 为什么有这条门禁

`Room:GetDoor` 从批次 046 起一直是"恒返回 nil"的降级，而 GoodTrip 的**连通图完全建立在它之上**
（`floor.sweep_doors()` → `floor.linked()` → `rules.check_teleble()`）。返回 nil 时连通图为空，
传送只能靠临时钉子 `AllowAnyRoom = true` 撑住 —— 那个钉子的副作用正是**能传送到没去过的房间**
（用户实测反馈）。把门族做实，钉子才能撤掉。

真机取证（`runtime_constants.hpp` 的门族那一段有完整证据）：
* `Room + 0xE70 + slot*4` = 该槽位门的**网格下标**（`Room::GetDoorSlotPosition` 读的就是它）；
* `Room + 0x30` = 网格实体表 ⇒ `GridEntity_Door*`；
* 门字段：`Variant +0x10`、`Type +0x18`、`CurrentRoomType +0x1A4`、`TargetRoomType +0x1A8`、
  `Direction +0x1AC`、标志字 `+0x318`。

宿主上跑真实 Lua 脚本，核对：字段值来自**我们指定的那三个偏移**、非法/空槽位给 nil、
方法调用能落到 `GridEntity` 那一族（`GetVariant()`），以及"引擎不可用时 `Position` 给 nil 而不是报错"。
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import layered_lua_runtime_sources
except ImportError:
    from test_support import layered_lua_runtime_sources


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

GameIsPausedObservation ObserveGameIsPaused(uintptr_t, uintptr_t) {
    return GameIsPausedObservation::OwnerUnreadable;
}
GameLevelStageObservation ReadCurrentGameLevelStage(uintptr_t, std::uint32_t*) {
    return GameLevelStageObservation::GameUnreadable;
}
GameItemPoolObservation ReadCurrentGameItemPool(uintptr_t, void**) {
    return GameItemPoolObservation::GameUnreadable;
}
GameIsGreedModeObservation ObserveGameIsGreedMode(uintptr_t, uintptr_t) {
    return GameIsGreedModeObservation::MethodUnavailable;
}
GameIsAscentObservation ObserveLevelIsAscent(uintptr_t, uintptr_t) {
    return GameIsAscentObservation::MethodUnavailable;
}
GameRoomObservation ReadCurrentGameRoomType(uintptr_t, std::uint32_t*) {
    return GameRoomObservation::RoomUnreadable;
}

namespace {

//: 伪造的 `Room`（只要覆盖到 `+0xE70 + 8*4` 那张"槽位 → 网格下标"表）与一个门对象。
std::vector<unsigned char> g_RoomBytes;
std::vector<unsigned char> g_DoorBytes;
std::vector<unsigned char> g_ClosedDoorBytes;

constexpr std::size_t kDoorObjectTable = 0xE30;      // `Room + 0xE30 + slot*8` = 门对象
//: `Room + 0xE70 + slot*4`（"槽位 → 网格下标"表）本用例用不到（取门走 `+0xE30`），
//: 但 Room 块要够大，免得越界读落到别的映射上。
constexpr std::size_t kRoomBytesSize = kDoorObjectTable + 8 * sizeof(std::uint64_t) + 8;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

void WriteWord(std::vector<unsigned char>& block, std::size_t offset, std::uint64_t value) {
    WriteAt(block, offset, value);
}

void PublishDoor() {
    g_RoomBytes.assign(kRoomBytesSize, 0);
    g_DoorBytes.assign(0x400, 0);

    // 门对象（偏移全部来自 `runtime_constants.hpp` 门族那一段的取证）：
    //   `Type` = 7（GridEntityType.DOOR，**+0x08**）、`Variant` = 8（隐藏门，+0x10）、
    //   `VarData` = 3（+0x1C）、`CurrentRoomType` = 1、`TargetRoomType` = 10（诅咒房）、
    //   `Direction` = 2、`TargetRoomIndex` = 42（+0x30C）、标志 bit4 = 1（开着）。
    WriteAt<std::uint32_t>(g_DoorBytes, 0x08, 7);
    WriteAt<std::uint32_t>(g_DoorBytes, 0x10, 8);
    WriteAt<std::uint32_t>(g_DoorBytes, 0x1C, 3);
    WriteAt<std::uint32_t>(g_DoorBytes, 0x1A0, 0);
    WriteAt<std::uint32_t>(g_DoorBytes, 0x1A4, 1);
    WriteAt<std::uint32_t>(g_DoorBytes, 0x1A8, 10);
    WriteAt<std::uint32_t>(g_DoorBytes, 0x1AC, 2);
    WriteAt<std::uint32_t>(g_DoorBytes, 0x30C, 42);
    WriteAt<std::uint32_t>(g_DoorBytes, 0x318, 0x10);

    // 槽位 0 有门（`Room + 0xE30`）；槽位 1 放一扇"关着的门"（标志 bit4 = 0、variant = 3）；
    // 其余槽位留 0 ⇒ "这个槽位没有门"。
    const auto doorAddress = static_cast<std::uint64_t>(
        reinterpret_cast<std::uintptr_t>(g_DoorBytes.data()));
    WriteWord(g_RoomBytes, kDoorObjectTable, doorAddress);
    g_ClosedDoorBytes.assign(0x400, 0);
    WriteAt<std::uint32_t>(g_ClosedDoorBytes, 0x08, 7);
    WriteAt<std::uint32_t>(g_ClosedDoorBytes, 0x10, 3);
    WriteAt<std::uint32_t>(g_ClosedDoorBytes, 0x318, 0x00);
    WriteWord(g_RoomBytes, kDoorObjectTable + sizeof(std::uint64_t),
              static_cast<std::uint64_t>(
                  reinterpret_cast<std::uintptr_t>(g_ClosedDoorBytes.data())));
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t ownerSlot, void** room) {
    if (ownerSlot != 0x1111 || room == nullptr) {
        return GameRoomObservation::OwnerUnreadable;
    }
    *room = g_RoomBytes.data();
    return GameRoomObservation::Success;
}

int main() {
    PublishDoor();
    // 真实路径：与其它 Lua runtime harness 同一套绑定（owner 槽 0x1111）。
    LuaRuntime::SetGameBindings(0x1111, 0x2222);
    const char* script =
        "local mod=RegisterMod('Probe',1);"
        " mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE,function()"
        "  local room = Game():GetRoom()"
        "  local door = room:GetDoor(0)"
        "  print('KIND='..type(door))"
        "  print('TARGET_TYPE='..tostring(door.TargetRoomType))"
        "  print('CURRENT_TYPE='..tostring(door.CurrentRoomType))"
        "  print('DIRECTION='..tostring(door.Direction))"
        // 批次 079：`IsOpen` 是**方法**（PC 的签名就是 `boolean IsOpen()`），必须能这样调。
        "  print('IS_OPEN='..tostring(door:IsOpen()))"
        "  print('IS_OPEN_KIND='..type(door.IsOpen))"
        "  print('DESC_KIND='..type(door.Desc))"
        "  print('DESC_VARIANT='..tostring(door.Desc.Variant))"
        "  print('DESC_TYPE='..tostring(door.Desc.Type))"
        "  print('TARGET_INDEX='..tostring(door.TargetRoomIndex))"
        "  print('VAR_DATA='..tostring(door.VarData))"
        "  print('DESC_VAR_DATA='..tostring(door.Desc.VarData))"
        // 方法必须能落到 `GridEntity` 那一族（PC 里门同时是 GridEntity）。
        "  print('METHOD_VARIANT='..tostring(door:GetVariant()))"
        // 引擎调用不可用（宿主）时 `Position` 给 nil，但**不许报错**。
        "  print('POSITION='..tostring(door.Position))"
        // 空槽位与越界槽位都要给 nil，不是一个空对象。
        "  print('CLOSED_OPEN='..tostring(room:GetDoor(1):IsOpen()))"
        "  print('EMPTY_SLOT='..tostring(room:GetDoor(2)))"
        "  print('OUT_OF_RANGE='..tostring(room:GetDoor(9)))"
        " end)";
    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@door.lua");
    if (result != LuaRuntime::LuaInitResult::Success) {
        std::printf("DOOR_FAIL init=%d\n", static_cast<int>(result));
        return 2;
    }
    LuaRuntime::DispatchPreGetCollectible(nullptr, 0, 0, 1, 0);
    if (LuaRuntime::TakeCallbackError()) {
        std::printf("DOOR_FAIL callback error\n");
        return 3;
    }
    return 0;
}
'''


class LuaRoomGetDoorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-door-")
        temporary = Path(cls.temporary.name)
        compatibility = temporary / "compatibility"
        compatibility.mkdir()
        (compatibility / "stdfloat").write_text(
            "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n"
        )
        harness = temporary / "door_harness.cpp"
        harness.write_text(HARNESS.lstrip(), encoding="utf-8")
        lua_root = SOURCE / "third_party/lua-5.3.3/src"
        excluded = {"lua.c", "luac.c", "liolib.c", "loslib.c", "loadlib.c", "ldblib.c", "linit.c"}
        objects = []
        for source in sorted(lua_root.glob("*.c")):
            if source.name in excluded:
                continue
            output = temporary / f"{source.stem}.o"
            build = subprocess.run(
                ["cc", "-std=c99", "-w", "-DLUA_C89_NUMBERS", "-I", str(lua_root),
                 "-c", str(source), "-o", str(output)], text=True, capture_output=True)
            if build.returncode != 0:
                raise AssertionError(build.stdout + build.stderr)
            objects.append(output)
        cls.binary = temporary / "door_harness"
        build = subprocess.run(
            ["c++", "-std=c++23", "-Wall", "-Wextra", "-Werror", "-DLUA_C89_NUMBERS",
             "-DEXL_LAYERED_RUNTIME=1", "-DEXL_LOAD_KIND=Module", "-DEXL_LOAD_KIND_ENUM=2",
             "-DEXL_PROGRAM_ID=0", "-I", str(compatibility), "-I", str(SOURCE),
             "-I", str(SOURCE.parent / "src"), "-I", str(lua_root), str(harness),
             *(str(path) for path in layered_lua_runtime_sources(SOURCE)),
             *(str(path) for path in objects), "-lm", "-o", str(cls.binary)],
            text=True, capture_output=True)
        if build.returncode != 0:
            raise AssertionError(build.stdout + build.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def output(self) -> str:
        result = subprocess.run([str(self.binary)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_door_fields_come_from_their_own_offsets(self):
        """字段逐个钉住 —— 防"整批偏移错位"这种界面上看不出异常的错。"""
        out = self.output()
        for expected in ("KIND=userdata", "TARGET_TYPE=10", "CURRENT_TYPE=1", "DIRECTION=2",
                         "IS_OPEN=true", "IS_OPEN_KIND=function", "DESC_KIND=table",
                         "DESC_VARIANT=8", "DESC_TYPE=7",
                         "TARGET_INDEX=42", "VAR_DATA=3", "DESC_VAR_DATA=3"):
            with self.subTest(expected=expected):
                self.assertIn(expected, out)

    def test_door_is_also_a_grid_entity(self):
        """PC 里门**同时是** `GridEntity` ⇒ `door:GetVariant()` 必须能用。

        判据：`__index` 是函数时，字段答不上要落到 `GridEntity` 的方法表 —— 漏掉这一步，
        模组调 `door:GetType()` 会得到 "attempt to call a nil value"。
        """
        out = self.output()
        self.assertIn("METHOD_VARIANT=8", out)

    def test_empty_and_out_of_range_slots_are_nil(self):
        """没有门的槽位给 nil（不是空对象），越界槽位也 nil（PC 的 `GetDoorSlotPosition` 同判）。"""
        out = self.output()
        self.assertIn("CLOSED_OPEN=false", out)
        self.assertIn("EMPTY_SLOT=nil", out)
        self.assertIn("OUT_OF_RANGE=nil", out)

    def test_position_degrades_without_an_engine(self):
        """宿主没有引擎 ⇒ `Position` 给 nil，但**不许报错**（真机上它是引擎给的坐标）。"""
        out = self.output()
        self.assertIn("POSITION=nil", out)
        self.assertNotIn("DOOR_FAIL", out)


if __name__ == "__main__":
    unittest.main()
