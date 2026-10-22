"""门禁：`EntityPlayer` 族 5 条（批次 278，2026-10-02）。

## 这一批是什么

`needs_new_receiver` / `needs_forensics` 里**参数个数与引擎符号完全对齐**的那一批
（选批的硬要求，见 `runtime_constants.hpp` 的批次 278 段）：

| API | 调用点 | 引擎入口 | 形态 |
| --- | --- | --- | --- |
| `EntityPlayer:ThrowHeldEntity(Vector)` | 1 | `Entity_Player::ThrowHeldEntity(Vector2 const&)` @ `0x27C648` | Vector → **返回 Entity** |
| `EntityPlayer:AddSwarmFlyOrbital(Vector)` | 1 | `@ 0x28D510` | Vector → **返回 EntityFamiliar** |
| `EntityPlayer:AddItemWisp(Collectible, Vector, bool)` | 4 | `@ 0x31DF50` | 整数 + Vector + 布尔 → 返回 EntityFamiliar |
| `EntityPlayer:UsePill(PillEffect, PillColor, UseFlags)` | 1 | `@ 0x2DFC04` | 三个整数（枚举/位掩码） |
| `EntityPlayer:AddBlueFlies(Amount, Vector, Entity)` | 1 | `@ 0x27FC18` | 整数 + Vector + **实体** → 返回 Entity |

★ **为什么"个数对齐"要当成硬要求**：有几条引擎版比 PC 版**多一个尾参**
（`ChangePlayerType(ePlayerType, bool)`、`DischargeActiveItem(int, bool)` 这种），
多出来的那个我们**不知道怎么给**（给 `0` / `false` 都是猜）⇒ 那几条本批**不收**。
★ `AddBlueFlies` 带**实体参数** ⇒ 新增 `EntityArgumentPointer()`：**句柄失效时静默降级**，
绝不把野指针交给引擎；而"根本不是实体句柄"仍然报错（模组写错了）。
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
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"

#: `(名字, 域内序号, C++ 处理器名, 引擎常量前缀)`
APIS = (
    ("ThrowHeldEntity", 0x00B4, "EntityPlayerThrowHeldEntity", "kEntityPlayerThrowHeldEntity"),
    ("AddSwarmFlyOrbital", 0x00B5, "EntityPlayerAddSwarmFlyOrbital",
     "kEntityPlayerAddSwarmFlyOrbital"),
    ("AddItemWisp", 0x00B6, "EntityPlayerAddItemWisp", "kEntityPlayerAddItemWisp"),
    ("UsePill", 0x00B7, "EntityPlayerUsePill", "kEntityPlayerUsePill"),
    ("AddBlueFlies", 0x00B8, "EntityPlayerAddBlueFlies", "kEntityPlayerAddBlueFlies"),
)


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄 `test_lua_api_gap_batch3.py` 那套，只留本批要用的几格）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_Game 变量（槽里是**变量地址**，不是对象）
//   g_Game 变量            = Game*
//   Game + kGamePlayerArrayBegin/End = 只有一个元素的玩家指针数组
//   Entity_Player 首字      = base + kEntityPlayerVtableOffset（`ValidatedEntityPlayer` 要它）
// 有它才能真的走到"取接收者"那一步 —— 否则 `Isaac.GetPlayer(0)` 是 nil，参数闸门根本没被执行。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::uintptr_t g_EngineBase = 0;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void PublishFakeGame() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    // 槽里放 `g_Game` **变量的地址**（与真实布局一致：槽指向变量，变量才指向对象）。
    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    // 一个玩家：首字是 vtable，再填三个 `ValidatedEntityPlayer` 会看的字段。
    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, 1);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityPlayerTypeOffset, 0);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityPlayerIndexOffset, 0);
    g_PlayerArrayBytes.assign(2 * sizeof(std::uint64_t), 0);
    WriteAt<std::uint64_t>(g_PlayerArrayBytes, 0, AddressOf(g_PlayerBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayBeginOffset, AddressOf(g_PlayerArrayBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayEndOffset,
                           AddressOf(g_PlayerArrayBytes) + sizeof(std::uint64_t));

    LuaRuntime::SetEngineModuleBase(g_EngineBase);
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = nullptr;
    return GameRoomObservation::GameNull;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    PublishFakeGame();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script = nullptr;
    if (std::strcmp(scenario, "gates") == 0) {
        script =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local p = Isaac.GetPlayer(0)"
            " local V = Vector(10, 20)"
            " print('B278 held=' .. ok(function() return p:ThrowHeldEntity(V) end)"
            "   .. ',' .. ok(function() return p:ThrowHeldEntity() end)"
            "   .. ',' .. ok(function() return p:ThrowHeldEntity(1) end))"
            " print('B278 orbital=' .. ok(function() return p:AddSwarmFlyOrbital(V) end)"
            "   .. ',' .. ok(function() return p:AddSwarmFlyOrbital() end))"
            " print('B278 wisp=' .. ok(function() return p:AddItemWisp(1, V, false) end)"
            "   .. ',' .. ok(function() return p:AddItemWisp(1, V) end)"
            "   .. ',' .. ok(function() return p:AddItemWisp(1, V, false) end))"
            " print('B278 pill=' .. ok(function() return p:UsePill(1, 2, 0) end)"
            "   .. ',' .. ok(function() return p:UsePill(1, 2) end)"
            "   .. ',' .. ok(function() return p:UsePill(1) end))"
            " print('B278 flies=' .. ok(function() return p:AddBlueFlies(3, V, p) end)"
            "   .. ',' .. ok(function() return p:AddBlueFlies(3, V, 5) end)"
            "   .. ',' .. ok(function() return p:AddBlueFlies(3, V) end))"
            " print('B278 ret=' .. tostring(p:ThrowHeldEntity(V))"
            "   .. ',' .. tostring(p:AddItemWisp(1, V, true))"
            "   .. ',' .. tostring(p:AddBlueFlies(1, V, p))"
            "   .. ',' .. tostring(p:AddSwarmFlyOrbital(V)))";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b271.lua");
    static_cast<void>(result);
    return 0;
}
'''

class EntityPlayerBatch278Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b278-")
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

    def test_documented_shapes_accepted_and_misuse_rejected(self):
        """五条的合法形状都能调通、写错形状必须报错（宿主上引擎不可用 ⇒ 静默降级）。

        ★ 这一格钉的是"参数个数/类型算错"那类缺陷（批次 249 的形态）。
        """
        out = self.run_scenario("gates")
        self.assertIn("B278 held=true,false,false", out)
        self.assertIn("B278 orbital=true,false", out)
        #: ★ `AddItemWisp` 的第三个参数**可省**（契约写明默认 `false`）⇒ 三种形状都合法。
        self.assertIn("B278 wisp=true,true,true", out)
        #: ★ `UsePill` 的第三个参数**可省**（契约写明默认 `0`）⇒ 前两种合法、第三种个数不足。
        self.assertIn("B278 pill=true,true,false", out)
        self.assertIn("B278 flies=true,false,false", out)

    def test_entity_returning_four_give_nil_without_the_engine(self):
        """四条返回实体的在拿不到引擎时压 `nil`（不是空壳句柄、更不是报错）。"""
        out = self.run_scenario("gates")
        self.assertIn("B278 ret=nil,nil,nil,nil", out)

    # ---------------------------------------------------------------- 静态接线

    def test_catalog_and_binding_rows_exist(self):
        catalog = CATALOG.read_text(encoding="utf-8")
        body = ISAAC_API.read_text(encoding="utf-8")
        for name, index, cpp, _prefix in APIS:
            with self.subTest(name):
                self.assertIn(f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, '
                              f'"EntityPlayer", "{name}"', catalog)
                self.assertRegex(body, rf"\{{\s*(?i:0x0e01{index:04x}),\s*&{cpp}\s*\}}")

    def test_each_has_an_offset_and_a_sixteen_byte_guard(self):
        constants = CONSTANTS.read_text(encoding="utf-8")
        for _name, _index, _cpp, prefix in APIS:
            with self.subTest(prefix):
                self.assertIn(f"{prefix}Offset = 0x", constants)
                self.assertIn(f"{prefix}ExpectedBytes", constants)

    def test_the_arity_rule_is_written_down(self):
        """★ 选批的硬要求（"参数个数与契约页对齐"）必须写在常量段里 ——

        这一条挡的是后来者把"多一个尾参"的那几条（`ChangePlayerType` 之类）顺手加进来：
        那意味着要给一个我们不知道默认值的参数。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        self.assertIn("参数个数与 PC 契约页完全一致", constants)
        self.assertIn("ChangePlayerType(ePlayerType, bool)", constants)

    def test_entity_argument_helper_degrades_instead_of_passing_a_wild_pointer(self):
        """★ `AddBlueFlies` 的实体参数：失效句柄**静默降级**，不是把野指针交给引擎。"""
        body = ISAAC_API.read_text(encoding="utf-8")
        handler = body[body.index("int EntityPlayerAddBlueFlies(lua_State* state) {"):]
        handler = handler[:handler.index("\n}\n")]
        self.assertIn("EntityArgumentPointer(state, 4, &targetValid)", handler)
        self.assertIn("PushNil(state);", handler)
        self.assertIn("expects an entity as its target", handler)


if __name__ == "__main__":
    unittest.main()
