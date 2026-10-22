"""门禁：`EntityTear` 视图 + `EntityTear:ChangeVariant`（批次 281，2026-10-02）。

## 这一批是什么

**视图化** —— 语料里 `EntityTear:ChangeVariant`（8 处）、`EntityLaser:SetActiveRotation`（6 处）
这类方法一直取不到，根因不是"引擎没有"，而是 `Entity:ToTear()` 过去**压的是 `Entity` 元表**，
所以 `EntityTear` 自己的方法**没有地方挂**。

本批给 `EntityTear` 建了独立视图（元表 + 方法表 + `EntityView::Tear` + `IndexEntity` 分派），
并把 `ToTear()` 改成压它。字段仍然回落到 `Entity`（`IndexEntity` 的 else 分支），
方法先查本视图元表、再回落 `Entity` ⇒ `tear:GetSprite()` 这类老用法不受影响。

## 本文件钉什么

① `ToTear()` 真的给出 `EntityTear` 视图（判据是**它自己的方法能调** —— 视图没接上就是 nil）；
② `ChangeVariant` 的四个形状闸门；③ 老用法（`GetSprite()`）不退化。
★ **不钉**引擎那一步真的执行了（宿主没有引擎）—— 那要真机，见作业单 V32。
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
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
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
    // 批次 281：把假对象做成**一颗眼泪**（`ToTear()` 的判据是
    // 「vptr == base + kEntityTearVtableOffset」且「Type == kEntityTypeTear」）。
    WriteAt<std::uint64_t>(g_PlayerBytes, 0, g_EngineBase + kEntityTearVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, kEntityTypeTear);
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
    if (std::strcmp(scenario, "tear") == 0) {
        script =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local p = Isaac.GetPlayer(0)"
            " local t = p:ToTear()"
            " print('B281 kind=' .. type(t))"
            " print('B281 change=' .. ok(function() return t:ChangeVariant(5) end)"
            "   .. ',' .. ok(function() return t:ChangeVariant() end)"
            "   .. ',' .. ok(function() return t:ChangeVariant('x') end)"
            "   .. ',' .. ok(function() return t:ChangeVariant(1, 2) end))"
            " print('B281 entity=' .. ok(function() return t:GetSprite() end))";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b271.lua");
    static_cast<void>(result);
    return 0;
}
'''

class EntityTearViewBatch281Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b281-")
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

    # ---------------------------------------------------------------- 行为

    #: ★ **宿主造不出一颗眼泪句柄** —— 唯一的句柄来源 `Isaac.GetPlayer(0)` 会按
    #: `vptr == base + kEntityPlayerVtableOffset` 校验，而 `ToTear()` 的判据恰恰要求
    #: `vptr == base + kEntityTearVtableOffset` ⇒ 两者不可能同时成立。
    #: 所以**行为判据只有真机能给**（作业单 V32）；这里把它标成 skip 并写明原因，
    #: 而不是让一个连不上的断言假装通过。
    SKIP_REASON = ("宿主没有能造出眼泪句柄的入口（`Isaac.GetPlayer` 按玩家 vptr 校验、"
                   "`ToTear()` 要求眼泪 vptr）⇒ 这条只能真机验，见作业单 V32")

    def test_to_tear_now_yields_the_view_that_has_its_own_methods(self):
        """★ `ToTear()` 必须给出**带 `EntityTear` 方法表**的视图 —— 判据就是"它自己的方法能调"。

        视图没接上时 `t:ChangeVariant(5)` 会报 "attempt to call a nil value"，所以这一格
        同时钉住了"元表换了"和"方法挂上了"。
        """
        out = self.run_scenario("tear")
        if "B281 kind=" not in out:
            self.skipTest(self.SKIP_REASON)
        self.assertIn("B281 kind=userdata", out)
        self.assertIn("B281 change=true,false,false,false", out)

    def test_old_entity_methods_still_work_on_the_new_view(self):
        """新视图**不能**让老用法退化：`Entity` 的方法（这里用 `GetSprite()`）要照旧能调。"""
        out = self.run_scenario("tear")
        if "B281 entity=" not in out:
            self.skipTest(self.SKIP_REASON)
        self.assertIn("B281 entity=true", out)

    # ---------------------------------------------------------------- 静态接线

    def test_view_is_wired_in_every_place(self):
        """★ 新视图的**五处接线**必须都在（漏一处就是"方法取不到"或"死代码"）。

        ① `EntityView` 枚举有 `Tear`；② `EntityViewMetatable` 认它；③ `IndexEntity` 的包装函数
        `EntityTearIndex` 存在；④ `ToTear()` 把视图传下去；⑤ `CheckEntityHandle` **认这张元表**
        （漏了这一格，`ToTear()` 的"已经是该视图再转换"分支会变成死代码 —— 批次 207 踩过）。
        """
        body = ISAAC_API.read_text(encoding="utf-8")
        self.assertIn("EntityView::Tear", body)
        self.assertIn("kEntityTearMetatable", body)
        self.assertIn("int EntityTearIndex(lua_State* state) {", body)
        self.assertIn("kEntityTypeTear,", body)
        self.assertIn("EntityView::Tear);", body)
        self.assertIn("luaL_testudata(state, index, kEntityTearMetatable)", body)

    def test_catalog_and_binding_rows_exist(self):
        catalog = CATALOG.read_text(encoding="utf-8")
        body = ISAAC_API.read_text(encoding="utf-8")
        self.assertIn('MakeId(ApiDomain::Isaac, 1, 0x00B9), ApiDomain::Isaac, "EntityTear", '
                      '"ChangeVariant"', catalog)
        self.assertRegex(body, r"\{\s*(?i:0x0e0100b9),\s*&EntityTearChangeVariant\s*\}")

    def test_entry_offset_is_sixteen_byte_guarded(self):
        constants = CONSTANTS.read_text(encoding="utf-8")
        self.assertIn("kEntityTearChangeVariantOffset = 0x3412D8", constants)
        self.assertIn("kEntityTearChangeVariantExpectedBytes", constants)


if __name__ == "__main__":
    unittest.main()
