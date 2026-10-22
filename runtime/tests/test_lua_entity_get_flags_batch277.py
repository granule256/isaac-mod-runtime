"""门禁：`Entity:GetEntityFlags()`（批次 277，2026-10-02）。

## 这一条是什么

它是批次 275 那两条**写**侧（`AddEntityFlags` / `ClearEntityFlags`）的同族**读**侧 ——
原本被分在 `field_row` 桶（"引擎里没有同名访问器"），但**字段我们早就有了**：
`kEntityFlagsOffset`（`Entity + 0x1B8`，64 位），三兄弟（Get / Add / Clear）用的是**同一格**。

★ 证据链与批次 275 完全一致，再加一条：PC 的 `Entity:GetEntityFlags` 绑定函数 VA `0x4122E0`
全文是 `mov eax,[ecx+0x160]` / `mov edx,[ecx+0x164]` / `ret` —— **两个 dword 一起返回**
⇒ 它是一个 **64 位值**，与 `AddEntityFlags` 的 `ret 0x8`（64 位实参拆成两个栈槽）互为印证。

## 本文件是「真验证」

夹具把标志字预置成 `1<<62 | 5` ⇒ 宿主上直接验：
① `GetEntityFlags()` 的返回值**逐位相等**；② `HasEntityFlags` 对它的一致性；
③ 高位（`1 << 62`）也在里面（"64 位、不是 int32"）。
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
    // 批次 277：预置一个已知的标志字（`1<<62 | 5`）—— `GetEntityFlags` 必须原样读回来。
    WriteAt<std::uint64_t>(g_PlayerBytes, kEntityFlagsOffset, (1ULL << 62) | 5ULL);
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
    if (std::strcmp(scenario, "get") == 0) {
        script =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local p = Isaac.GetPlayer(0)"
            " local v = p:GetEntityFlags()"
            " print('B277 type=' .. type(v))"
            " print('B277 exact=' .. tostring(v == ((1 << 62) | 5)))"
            " print('B277 bit=' .. tostring(p:HasEntityFlags(1 << 62))"
            "   .. ',' .. tostring(p:HasEntityFlags(1)) .. ',' .. tostring(p:HasEntityFlags(2)))"
            " print('B277 arity=' .. ok(function() return p:GetEntityFlags(1) end))";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b271.lua");
    static_cast<void>(result);
    return 0;
}
'''

class EntityGetFlagsBatch277Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b277-")
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

    def test_reads_the_exact_sixty_four_bit_word(self):
        """★ 逐位相等 —— 连 `1 << 62` 这种高位也在（"64 位、不是 int32"）。"""
        out = self.run_scenario("get")
        self.assertIn("B277 type=number", out)
        self.assertIn("B277 exact=true", out)

    def test_consistent_with_has_entity_flags(self):
        """`GetEntityFlags()` 与 `HasEntityFlags()` 必须看到**同一格**（1<<62 与 1 置着、2 没置）。"""
        out = self.run_scenario("get")
        self.assertIn("B277 bit=true,true,false", out)

    def test_argument_gates(self):
        """0 参方法多给实参必须报错。"""
        out = self.run_scenario("get")
        self.assertIn("B277 arity=false", out)

    def test_wired_like_its_two_siblings(self):
        """三兄弟（Get/Add/Clear）必须挂在同一张表、用同一格、共用同一族助手。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        body = ISAAC_API.read_text(encoding="utf-8")
        self.assertIn('MakeId(ApiDomain::Isaac, 1, 0x00B3), ApiDomain::Isaac, "Entity", '
                      '"GetEntityFlags"', catalog)
        self.assertRegex(body, r"\{\s*(?i:0x0e0100b3),\s*&EntityGetEntityFlags\s*\}")
        handler = body[body.index("int EntityGetEntityFlags(lua_State* state) {"):]
        handler = handler[:handler.index("\n}\n")]
        self.assertIn("ReadEngine(entity + kEntityFlagsOffset, &flags)", handler)
        self.assertNotIn("WriteEngine", handler, "读侧不许写")
        self.assertIn("PushNativeFallbackInteger(state, kFbEntityGetEntityFlags, 0)", handler)
        #: 三个处理器都走同一个"取接收者"助手。
        self.assertGreaterEqual(body.count("EntityReceiverOrError(state,"), 3)


if __name__ == "__main__":
    unittest.main()
