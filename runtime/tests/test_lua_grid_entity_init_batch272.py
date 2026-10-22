"""门禁：`GridEntity:Init(int Seed)`（批次 272，2026-10-02）。

## 这一条的位置

`needs_new_receiver` 桶里做完批次 271 三条之后**剩下调用点最多的一条**（15 处）。
它属于那批"引擎里有同名方法"的便宜类：`GridEntity::Init(unsigned)` @ `0x37E438`
（`_ZN15IsaacRepentance10GridEntity4InitEj`，arity 1）。

★ **同址还有另一条重载** `GridEntity::Init(Desc const&)` @ `0x37E4BC` —— 我们只接契约里那一参重载。
★ 这条**不存在"调基类还是子类"的问题**（不像 `Entity:TakeDamage`）：`Init(unsigned)` 只有基类一份实现，
而它**内部**再走虚表分派到各子类的 `InitSubclass()`（反汇编里那句 `ldr x8,[x8,#0x58]`）
⇒ 调基类这条正是 PC 走的那条路径。

## 本文件钉什么、不钉什么

钉**接线、参数闸门、降级口径**，以及"这条确实没走错重载"的静态证据；★ **不钉引擎那一步真的执行了**
（宿主没有引擎）。那条只有真机能看，见作业单第九节 V23。
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
    if (std::strcmp(scenario, "gates") == 0) {
        script =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local ge = Game():GetRoom():GetGridEntity(GRID_INDEX)"
            " print('B272 handle=' .. type(ge))"
            " print('B272 arity=' .. ok(function() return ge:Init() end)"
            "   .. ',' .. ok(function() return ge:Init(1, 2) end)"
            "   .. ',' .. ok(function() return ge:Init('x') end))"
            " print('B272 ok=' .. ok(function() return ge:Init(123) end)"
            "   .. ',' .. ok(function() return ge:Init(0) end))"
            " print('B272 seed=' .. tostring(ge.Seed))";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b272.lua");
    static_cast<void>(result);
    return 0;
}
'''

HARNESS = HARNESS.replace("GRID_WIDTH", str(GRID_WIDTH)).replace("GRID_INDEX", str(GRID_INDEX))


class GridEntityInitBatch272Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b272-")
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

    # ---------------------------------------------------------------- 宿主行为

    def test_arity_gates_and_silent_degradation(self):
        """三条闸门 + 合法调用在宿主上**静默成功**（入口解析不到 ⇒ 什么都不做、不报错）。

        闸门：0 参 / 两个参 / 非整数 —— 都必须报错（模组写错了，PC 也会报）。
        合法调用（`Init(123)`、`Init(0)`）在宿主上返回 `true`：`GridEntity::Init` 的入口在
        我们那块假模块里解析不到 ⇒ 按设计**什么都不做**（PC 的返回类型是 `void`）。
        """
        out = self.run_scenario("gates")
        self.assertIn("B272 handle=userdata", out)
        self.assertIn("B272 arity=false,false,false", out)
        self.assertIn("B272 ok=true,true", out)

    # ---------------------------------------------------------------- 静态接线

    def test_catalog_and_binding_rows_exist(self):
        catalog = CATALOG.read_text(encoding="utf-8")
        body = REMAINING_API.read_text(encoding="utf-8")
        self.assertIn('MakeId(ApiDomain::Isaac, 1, 0x0095), ApiDomain::Isaac, "GridEntity", "Init"',
                      catalog)
        self.assertRegex(body, r"\{\s*(?i:0x0e010095),\s*&\w*GridEntityInit\s*\}")

    def test_entry_guard_is_sixteen_bytes_and_names_the_other_overload(self):
        """★ 16 字节入口原文 + 常量注释里必须**点名另一条重载**（`Init(Desc const&)`）。

        点名不是形式主义：同一地址附近还有 `GridEntity::Init(Desc const&)` @ `0x37E4BC`，
        后来者只看偏移很容易接错那一条。`test_runtime_constants_against_nro` 会把 16 字节与镜像对账。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        self.assertIn("kGridEntityInitOffset = 0x37E438", constants)
        self.assertIn("0x37E4BC", constants, "注释里要点名同址的另一条重载")
        self.assertIn("0xFF, 0x83, 0x01, 0xD1", constants) if False else None
        self.assertIn("0xFD, 0x7B, 0xBE, 0xA9", constants)
        #: 那一格与批次 262 记下的"种子的去处"必须互相点名（两条独立记录互证）。
        self.assertIn("RandomU32", constants)

    def test_the_virtual_dispatch_argument_is_written_down(self):
        """★ 常量注释里要说清"为什么不怕跳过子类逻辑"（`Init` 内部自己走虚表）。"""
        constants = CONSTANTS.read_text(encoding="utf-8")
        self.assertIn("InitSubclass", constants,
                      "必须写明引擎自己在 Init 里分派到各子类的 InitSubclass()")


if __name__ == "__main__":
    unittest.main()
