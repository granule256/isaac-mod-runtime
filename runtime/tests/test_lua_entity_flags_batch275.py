"""门禁：实体标志位的加/清两条（批次 275，2026-10-02）。

## 这一批是什么

`needs_forensics` 桶的头部两条（符号表里**没有同名函数**——因为它们在 PC 上就是**叶函数**）：

| API | 调用点 | PC 绑定函数 | 语义 |
| --- | --- | --- | --- |
| `Entity:AddEntityFlags(int Flags)` | 28 | VA `0x4122A0` | `or [ecx+0x160],eax` / `or [ecx+0x164],eax` / `ret 8` |
| `Entity:ClearEntityFlags(int Flags)` | 11 | VA `0x4122C0` | `not` + `and` 的镜像 / `ret 8` |

★ 两个关键读数：
① `ret 0x8` + 两个栈槽 ⇒ 参数在 PC 上是 **64 位整数**（32 位 x86 把 64 位实参拆成两个 dword）
⇒ 语义是**整体 64 位**的 `Flags |= v` / `Flags &= ~v`；
② **字段本体我们早就有确认证据** —— `kEntityFlagsOffset`（`Entity + 0x1B8`，64 位）是
`Entity:HasEntityFlags` 一直用的那一格（那条的注释里记着两个独立消费者）⇒
"PC 的 `+0x160` 与 Switch 的 `+0x1B8` 是同一语义字段"已经定过了，**本批不需要新偏移**。

## 本文件为什么能比前几批钉得更紧

偏移已知 + 假实体是我们**自己的内存** ⇒ 宿主上可以**真的验证读-改-写的效果**：
先用 `HasEntityFlags` 看初值，再 `Add`/`Clear`，再从 Lua 侧回读。连"高位（`1<<62`）也走 64 位"
这件事都能验 —— 那正是"不能按 int32 处理"这条判断的证据。
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
    if (std::strcmp(scenario, "flags") == 0) {
        script =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local p = Isaac.GetPlayer(0)"
            " local function has(v) return tostring(p:HasEntityFlags(v)) end"
            " print('B275 init=' .. has(1) .. ',' .. has(4) .. ',' .. has(8))"
            " p:AddEntityFlags(4)"
            " print('B275 add4=' .. has(4) .. ',' .. has(8))"
            " p:AddEntityFlags(8)"
            " print('B275 add8=' .. has(4) .. ',' .. has(8))"
            " p:ClearEntityFlags(4)"
            " print('B275 clr4=' .. has(4) .. ',' .. has(8))"
            " p:ClearEntityFlags(8)"
            " print('B275 clr8=' .. has(4) .. ',' .. has(8))"
            " local high = 1 << 62"
            " p:AddEntityFlags(high)"
            " print('B275 high=' .. has(high) .. ',' .. has(4))"
            " p:ClearEntityFlags(high)"
            " print('B275 highclear=' .. has(high))"
            " print('B275 arity=' .. ok(function() return p:AddEntityFlags() end)"
            "   .. ',' .. ok(function() return p:AddEntityFlags(1, 2) end)"
            "   .. ',' .. ok(function() return p:AddEntityFlags('x') end)"
            "   .. ',' .. ok(function() return p:ClearEntityFlags() end)"
            "   .. ',' .. ok(function() return p:ClearEntityFlags('x') end))";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b271.lua");
    static_cast<void>(result);
    return 0;
}
'''

class EntityFlagsBatch275Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b275-")
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

    # ---------------------------------------------------------------- 行为（本批能真验）

    def test_read_modify_write_actually_changes_the_field(self):
        """★ 用 `HasEntityFlags` 回读 —— 两条 API **真的**改了那一格，而且只改该改的位。"""
        out = self.run_scenario("flags")
        self.assertIn("B275 init=false,false,false", out)
        self.assertIn("B275 add4=true,false", out)
        self.assertIn("B275 add8=true,true", out)
        self.assertIn("B275 clr4=false,true", out)
        self.assertIn("B275 clr8=false,false", out)

    def test_high_bits_go_through_the_full_sixty_four(self):
        """★ `1 << 62` 也要能加能清 —— 这就是"不能按 int32 处理"那条判断的判据。

        PC 的 `EntityFlag` 里有 `1 << 62` 这类位；宿主上这一格直接验证走的是 64 位。
        """
        out = self.run_scenario("flags")
        self.assertIn("B275 high=true,false", out)
        self.assertIn("B275 highclear=false", out)

    def test_argument_gates(self):
        """0 参 / 两个参 / 非整数 —— 五条都必须报错（模组写错了，PC 也会报）。"""
        out = self.run_scenario("flags")
        self.assertIn("B275 arity=false,false,false,false,false", out)

    # ---------------------------------------------------------------- 静态接线

    def test_catalog_and_binding_rows_exist(self):
        catalog = CATALOG.read_text(encoding="utf-8")
        body = ISAAC_API.read_text(encoding="utf-8")
        for name, index, cpp in (("AddEntityFlags", 0x00A9, "EntityAddEntityFlags"),
                                 ("ClearEntityFlags", 0x00AA, "EntityClearEntityFlags")):
            with self.subTest(name):
                self.assertIn(f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, '
                              f'"Entity", "{name}"', catalog)
                self.assertRegex(body, rf"\{{\s*(?i:0x0e01{index:04x}),\s*&{cpp}\s*\}}")

    def test_no_new_offset_is_needed(self):
        """★ 这两条**没有**自己的偏移常量 —— 用的是 `HasEntityFlags` 那一格。

        判据落在实现上：处理器的读-改-写用的必须是 `kEntityFlagsOffset`，
        而且**不许**出现"为这两条新开一个偏移常量"的痕迹（那会意味着有人另外取证了一次）。
        """
        body = ISAAC_API.read_text(encoding="utf-8")
        handler = body[body.index("bool MutateEntityFlags("):]
        handler = handler[:handler.index("\n}\n")]
        self.assertIn("kEntityFlagsOffset", handler)
        constants = CONSTANTS.read_text(encoding="utf-8")
        for forbidden in ("kEntityAddEntityFlagsOffset", "kEntityClearEntityFlagsOffset"):
            self.assertNotIn(forbidden, constants)

    def test_write_goes_through_the_guarded_helpers(self):
        """★ 写引擎内存必须过"先判可写再写"那道关（与 `HUD:SetVisible` 同一口径）。

        判据：读用 `ReadEngine`、写用 `WriteEngine`（后者内部走 `IsEngineMemoryWritable`
        这条唯一实现），**不许**直接 `memcpy` 到裸地址。
        """
        body = ISAAC_API.read_text(encoding="utf-8")
        handler = body[body.index("bool MutateEntityFlags("):]
        handler = handler[:handler.index("\n}\n")]
        self.assertIn("ReadEngine(entity + kEntityFlagsOffset, &current)", handler)
        self.assertIn("WriteEngine(entity + kEntityFlagsOffset, mutate(current))", handler)
        self.assertNotIn("memcpy", handler)
        self.assertNotIn("reinterpret_cast", handler)

    def test_both_handlers_share_one_mutation_helper(self):
        """两条必须共用同一个读-改-写（只差一个 `|` / `& ~`），不各写一份。"""
        body = ISAAC_API.read_text(encoding="utf-8")
        self.assertEqual(body.count("MutateEntityFlags(entity, [flags]"), 2)
        self.assertIn("return current | flags;", body)
        self.assertIn("return current & ~flags;", body)


if __name__ == "__main__":
    unittest.main()
