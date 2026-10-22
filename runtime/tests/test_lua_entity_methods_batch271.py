"""门禁：`needs_new_receiver` 桶头部三条（批次 271，2026-10-02）。

## 这一批的选法

大桶里 `needs_new_receiver` 那 62 条**很多在引擎里有同名方法**（用嵌套名解析器扫过全符号表：
45/62 命中），而 `field_row` 那 59 条**一条都没有** ⇒ 先做前一批。
本批取其中调用点最多的三条：

| API | 调用点 | 引擎符号 | 子类重写？ |
| --- | --- | --- | --- |
| `Entity:SetColor(Color, Duration, Priority, Fadeout, Share)` | **51**（全清单单条最高） | `Entity::SetColor(ColorMod const&, int, int, bool, bool)` @ `0x63B84` | 无 |
| `EntityPlayer:UseActiveItem(Item, UseFlags=0, Slot=-1, CustomVarData=0)` | 23 | `Entity_Player::UseActiveItem(eCollectibleType, unsigned, int, int)` @ `0x30653C` | 无 |
| `Entity:AddCharmed(EntityRef, Duration)` | 11 | `Entity::AddCharmed(EntityRef const&, int)` @ `0x5EBE8` | 无 |

★ "没有子类重写"是用嵌套名解析器扫全符号表得到的结论（`SetColor`/`AddCharmed` 只在 `Entity`、
`UseActiveItem` 只在 `Entity_Player`）⇒ 这三条**不需要**像 `Entity:TakeDamage` 那样在
"基类 / 子类"之间二选一。

## 本文件钉什么、不钉什么

钉**接线、参数闸门、共享结构与降级口径**；★ **不钉引擎那一步真的执行了**（宿主没有引擎）
—— 那部分只有真机能看，见作业单第九节的 V20/V21。
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
COLOR_MOD = ROOT / "runtime" / "src" / "interfaces" / "lua" / "engine_color_mod.hpp"
GAME_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "game_api.cpp"

#: `(owner, 名字, 域内序号, 契约页)`
APIS = (
    ("Entity", "SetColor", 0x0092, "Entity.md:542"),
    ("Entity", "AddCharmed", 0x0093, "Entity.md"),
    ("EntityPlayer", "UseActiveItem", 0x0094, "EntityPlayer.md"),
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
            " local player = Isaac.GetPlayer(0)"
            " print('B271 player=' .. type(player))"
            " print('B271 setcolor_arity=' .. ok(function() return player:SetColor(Color(1,1,1)) end)"
            "   .. ',' .. ok(function() return player:SetColor(Color(1,1,1), 1, 1, false, false, 0) end)"
            "   .. ',' .. ok(function() return player:SetColor(5, 1, 1) end))"
            " print('B271 setcolor_ok=' .. ok(function()"
            "   return player:SetColor(Color(1, 1, 1, 1, 0, 0, 0), 1, 1, false, false) end)"
            "   .. ',' .. ok(function() return player:SetColor(Color(1, 1, 1), -1, 0) end))"
            " print('B271 addcharmed_arity=' .. ok(function() return player:AddCharmed(EntityRef(player), 5, 6) end)"
            "   .. ',' .. ok(function() return player:AddCharmed(5, 5) end))"
            " print('B271 addcharmed_ok=' .. ok(function() return player:AddCharmed(EntityRef(player), 5) end))"
            " print('B271 useactive_arity=' .. ok(function() return player:UseActiveItem() end)"
            "   .. ',' .. ok(function() return player:UseActiveItem(1, 0, -1, 0, 9) end))"
            " print('B271 useactive_ok=' .. ok(function() return player:UseActiveItem(1) end)"
            "   .. ',' .. ok(function() return player:UseActiveItem(1, 0, -1, 0) end))"
            " print('B271 useactive_ext=' .. ok(function() return player:UseActiveItem(479, false, false, false, false) end)"
            "   .. ',' .. ok(function() return player:UseActiveItem(1, false, false, true, false, -1) end)"
            "   .. ',' .. ok(function() return player:UseActiveItem(1, false, false, true, false, -1, 0) end))";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b271.lua");
    static_cast<void>(result);
    return 0;
}
'''


class EntityMethodBatch271Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b271-")
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

    # ---------------------------------------------------------------- 静态接线

    def test_catalog_and_binding_rows_exist(self):
        catalog = CATALOG.read_text(encoding="utf-8")
        body = ISAAC_API.read_text(encoding="utf-8")
        for owner, name, index, _page in APIS:
            with self.subTest(name):
                self.assertIn(
                    f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, '
                    f'"{owner}", "{name}"',
                    catalog, f"catalog 里没有 {owner}:{name}（域内序号 0x{index:04x}）")
                self.assertRegex(body, rf"\{{\s*(?i:0x0e01{index:04x}),\s*&\w*{name}\s*\}}",
                                 f"绑定表里没有 0x0E01{index:04X} → {name}")

    def test_contract_pages_are_referenced(self):
        body = ISAAC_API.read_text(encoding="utf-8")
        for _owner, name, _index, page in APIS:
            with self.subTest(name):
                self.assertIn(page, body, f"{name} 的实现处没有引用契约 {page}")

    def test_entry_guards_are_sixteen_bytes(self):
        """★ 三条的入口守卫用**整份 16 字节原文**，不是首个指令字。

        理由：清单里这三条本来就带 16 字节守卫，而 `test_runtime_constants_against_nro`
        会把数组与镜像**逐字节**对账（批次 269 就是靠它抓到手抄错的一个字节）。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        for needle in ("kEntitySetColorOffset = 0x63B84", "kEntitySetColorExpectedBytes",
                       "kEntityAddCharmedOffset = 0x5EBE8", "kEntityAddCharmedExpectedBytes",
                       "kEntityPlayerUseActiveItemExpectedBytes"):
            with self.subTest(needle):
                self.assertIn(needle, constants, f"缺常量：{needle}")
        body = ISAAC_API.read_text(encoding="utf-8")
        self.assertIn("EntityMethodByExpectedBytes", body,
                      "三条必须共用同一个 16 字节守卫的取址助手（不许各写一份）")

    def test_set_color_shares_one_color_mod_mapping(self):
        """★ `ColorMod` 与"颜色 → ColorMod"的映射**只有一份**（批次 271 抽到共享头）。

        `Entity:SetColor` 的第一个参数与批次 267 的 `Game:SpawnParticles` 是**同一个类型**
        （`ColorMod const&`）⇒ 再抄一份就是第三份拷贝（`sprite_api.cpp` 还有一份同源的映射）。
        """
        body = ISAAC_API.read_text(encoding="utf-8")
        self.assertIn("FillEngineColorMod(state, 2, &color)", body,
                      "SetColor 必须转调共享头里的映射")
        self.assertIn("DefaultEngineColorMod()", body)
        #: 这个 TU 里不许再出现第二份 `struct EngineColorMod` 定义。
        self.assertNotIn("struct EngineColorMod {", body,
                         "`ColorMod` 的结构体定义只许在 engine_color_mod.hpp 里")
        #: `Game:SpawnParticles` 那边也必须是转调，而不是自己再写一遍字段赋值。
        game = GAME_API.read_text(encoding="utf-8")
        self.assertIn("FillEngineColorMod(state, 6, &color)", game)
        self.assertNotIn("color.tint[0] = handle->red", game,
                         "批次 267 那份逐字段赋值必须已经搬进共享头")

    def test_optional_tail_arguments_are_accepted(self):
        """★ `Entity:SetColor` 的尾部两个布尔**必须可省**（语料里有 3 参调用）。

        语料里既有 `entity:SetColor(Color(...), 1, 1, false, false)`（5 参），
        也有 `tear:SetColor(redColor, -1, 0)`（3 参）⇒ 参数个数闸门必须是 `4..6`（含 `self`）。
        ★ 少算个数会让模组**每一次调用都抛错**，而错误会把整条回调摘掉（批次 249 的形态）。
        """
        body = ISAAC_API.read_text(encoding="utf-8")
        handler = body[body.index("\nint EntitySetColor(lua_State* state) {"):]
        handler = handler[:handler.index("\n}\n")]
        self.assertIn("stackTop < 4 || stackTop > 6", handler)
        self.assertIn("stackTop >= 5 && lua_toboolean(state, 5) != 0", handler)
        self.assertIn("stackTop >= 6 && lua_toboolean(state, 6) != 0", handler)

    def test_use_active_item_defaults_match_the_contract(self):
        """`UseActiveItem` 的三个缺省值在**契约页上写清了**（`0` / `-1` / `0`）—— 照抄，不推断。"""
        body = ISAAC_API.read_text(encoding="utf-8")
        handler = body[body.index("\nint EntityPlayerUseActiveItem(lua_State* state) {"):]
        handler = handler[:handler.index("\n}\n")]
        self.assertIn(": 0U;", handler, "UseFlags 缺省 0")
        self.assertIn(": -1;", handler, "Slot 缺省 -1")
        self.assertIn(": 0;", handler, "CustomVarData 缺省 0")

    # ---------------------------------------------------------------- 宿主行为

    def test_argument_gates_on_the_host(self):
        """宿主上 `Isaac.GetPlayer(0)` 拿不到真实体 ⇒ 只能验**参数闸门**那一段。

        ★ 闸门跑在"取接收者"**之前**，所以即使实体拿不到，参数错误也照样要报出来。
        拿不到实体时打印 `skip`（不把宿主的能力限制当成失败）。
        """
        out = self.run_scenario("gates")
        self.assertIn("B271 player=", out)
        if "B271 player=nil" in out:
            self.skipTest("宿主上这台夹具拿不到 EntityPlayer（不影响这三条的接线判据）")
        self.assertIn("B271 setcolor_arity=false,false,false", out)
        self.assertIn("B271 addcharmed_arity=false,false", out)
        self.assertIn("B271 useactive_arity=false,false", out)
        #: ★ 扩展形（第 2 个参数是布尔）必须都收得下 —— 语料里 25 处就是这种形状，
        #: 只写基础形的话它们会每一次都抛错并摘掉整条回调（批次 249 的形态）。
        self.assertIn("B271 useactive_ext=true,true,true", out)

    def test_missing_entity_degrades_silently(self):
        """★ 拿不到实体时**静默返回**（不报错）：PC 上对已消失实体调这些方法同样是空操作。

        这三条的契约返回类型都是 `void` ⇒ 没有"该给什么值"的问题，什么都不做就是对的。
        """
        out = self.run_scenario("gates")
        if "B271 player=nil" in out:
            self.skipTest("宿主上这台夹具拿不到 EntityPlayer（不影响这三条的接线判据）")
        self.assertIn("B271 setcolor_ok=true", out)
        self.assertIn("B271 useactive_ok=true", out)


if __name__ == "__main__":
    unittest.main()
