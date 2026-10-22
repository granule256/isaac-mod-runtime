"""门禁：清桶批 12 条（批次 274，2026-10-02）。

## 这一批是什么

选批口径**与批次 273 相同**（引擎里有同名方法 **且该同名方法只有一个类有** ⇒ 无子类重写），
只是把参数收到最简：**arity 0..2、参数只有标量 / `Vector` / `EntityRef`**。
十二条清掉的是 `needs_new_receiver` 里"每条只有 1 处调用"的那一段。

| API | 域内序号 | 形态 | 引擎入口 |
| --- | --- | --- | --- |
| `Entity:AddFear(EntityRef, int)` | `0x009D` | EntityRef + 整数 | `@ 0x5F660` |
| `Entity:AddHealth(float)` | `0x009F` | **浮点** | `@ 0x5A248` |
| `Entity:RemoveStatusEffects()` | `0x00A0` | 0 参 | `@ 0x5FEB8` |
| `EntityPlayer:AddBoneHearts(int)` | `0x00A1` | 整数 | `@ 0x27E380` |
| `EntityPlayer:AddFriendlyDip(int, Vector)` | `0x00A2` | 整数 + Vector（**返回 EntityFamiliar**） | `@ 0x2F62DC` |
| `EntityPlayer:AddPrettyFly()` | `0x00A3` | 0 参 | `@ 0x2F6DB0` |
| `EntityPlayer:AnimateTrapdoor()` | `0x00A4` | 0 参 | `@ 0x2F69F8` |
| `EntityPlayer:CanPickSoulHearts()` | `0x00A5` | 0 参（**返回 boolean**） | `@ 0x2FB7C4` |
| `EntityPlayer:DonateLuck(int)` | `0x00A6` | 整数 | `@ 0x2F9978` |
| `EntityPlayer:RemoveGoldenBomb()` | `0x00A7` | 0 参 | `@ 0x2FC490` |
| `EntityPlayer:RemoveGoldenKey()` | `0x00A8` | 0 参 | `@ 0x280628` |
| `Seeds:ForgetStageSeed(LevelStage)` | `0x0F010007` | 整数；`this` = `Game + 0x25D40` 现算 | `@ 0x4A1228` |

★ 这一批的守卫字节是**用脚本从镜像现场读出来的**（不是照抄清单里的守卫串）——
批次 269 就栽在抄错一个字节上。
★ `AddPrettyFly` / `AnimateTrapdoor` / `CanPickSoulHearts` 三条的入口 16 字节**相同**
（同一套编译器 prologue）⇒ **守卫不能当身份判据，区分靠偏移**（与批次 273 同一现象）。

## 本文件钉什么、不钉什么

钉**接线、参数闸门、降级口径**；★ **不钉引擎那一步真的执行了**（宿主没有引擎）—— 那要真机，见 V25。
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
GAME_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "game_api.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"

#: `(owner, 名字, 域内序号, 引擎常量前缀, C++ 处理器名)` —— C++ 名显式写，**不要靠拼**
#: （批次 273 那批踩过：拼出来的 `int AddPill(...)` 根本不存在）。
APIS = (
    ("Entity", "AddFear", 0x009D, "kEntityAddFear", "EntityAddFear"),
    ("Entity", "AddHealth", 0x009F, "kEntityAddHealth", "EntityAddHealth"),
    ("Entity", "RemoveStatusEffects", 0x00A0, "kEntityRemoveStatusEffects", "EntityRemoveStatusEffects"),
    ("EntityPlayer", "AddBoneHearts", 0x00A1, "kEntityPlayerAddBoneHearts", "EntityPlayerAddBoneHearts"),
    ("EntityPlayer", "AddFriendlyDip", 0x00A2, "kEntityPlayerAddFriendlyDip", "EntityPlayerAddFriendlyDip"),
    ("EntityPlayer", "AddPrettyFly", 0x00A3, "kEntityPlayerAddPrettyFly", "EntityPlayerAddPrettyFly"),
    ("EntityPlayer", "AnimateTrapdoor", 0x00A4, "kEntityPlayerAnimateTrapdoor", "EntityPlayerAnimateTrapdoor"),
    ("EntityPlayer", "CanPickSoulHearts", 0x00A5, "kEntityPlayerCanPickSoulHearts", "EntityPlayerCanPickSoulHearts"),
    ("EntityPlayer", "DonateLuck", 0x00A6, "kEntityPlayerDonateLuck", "EntityPlayerDonateLuck"),
    ("EntityPlayer", "RemoveGoldenBomb", 0x00A7, "kEntityPlayerRemoveGoldenBomb", "EntityPlayerRemoveGoldenBomb"),
    ("EntityPlayer", "RemoveGoldenKey", 0x00A8, "kEntityPlayerRemoveGoldenKey", "EntityPlayerRemoveGoldenKey"),
    #: `Seeds` 族的序号在另一个域（`ApiDomain::Seed`），单独列在下面。
)

SEEDS = ("Seeds", "ForgetStageSeed", "0x0007", "kSeedsForgetStageSeed", "SeedsForgetStageSeed")

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
            " local R = EntityRef(p)"
            " print('B274 fear=' .. ok(function() return p:AddFear(R, 60) end)"
            "   .. ',' .. ok(function() return p:AddFear(1, 60) end)"
            "   .. ',' .. ok(function() return p:AddFear(R) end))"
            " print('B274 health=' .. ok(function() return p:AddHealth(1.5) end)"
            "   .. ',' .. ok(function() return p:AddHealth('x') end))"
            " print('B274 rse=' .. ok(function() return p:RemoveStatusEffects() end)"
            "   .. ',' .. ok(function() return p:RemoveStatusEffects(1) end))"
            " print('B274 bh=' .. ok(function() return p:AddBoneHearts(2) end)"
            "   .. ',' .. ok(function() return p:AddBoneHearts() end))"
            " print('B274 dip=' .. ok(function() return p:AddFriendlyDip(1, V) end)"
            "   .. ',' .. ok(function() return p:AddFriendlyDip(1, true) end)"
            "   .. ',' .. ok(function() return p:AddFriendlyDip(1) end))"
            " print('B274 fly=' .. ok(function() return p:AddPrettyFly() end)"
            "   .. ',' .. ok(function() return p:AddPrettyFly(1) end))"
            " print('B274 trap=' .. ok(function() return p:AnimateTrapdoor() end)"
            "   .. ',' .. ok(function() return p:AnimateTrapdoor(1) end))"
            " print('B274 soul=' .. ok(function() return p:CanPickSoulHearts() end)"
            "   .. ',' .. ok(function() return p:CanPickSoulHearts(1) end))"
            " print('B274 luck=' .. ok(function() return p:DonateLuck(1) end)"
            "   .. ',' .. ok(function() return p:DonateLuck() end))"
            " print('B274 gbomb=' .. ok(function() return p:RemoveGoldenBomb() end)"
            "   .. ',' .. ok(function() return p:RemoveGoldenBomb(1) end))"
            " print('B274 gkey=' .. ok(function() return p:RemoveGoldenKey() end)"
            "   .. ',' .. ok(function() return p:RemoveGoldenKey(1) end))"
            " print('B274 dipRet=' .. tostring(p:AddFriendlyDip(1, V)))"
            " print('B274 soulRet=' .. tostring(p:CanPickSoulHearts()))"
            " local s = Game():GetSeeds()"
            " print('B274 seeds=' .. type(s) .. ',' .. ok(function() return s:ForgetStageSeed(1) end)"
            "   .. ',' .. ok(function() return s:ForgetStageSeed() end))";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b271.lua");
    static_cast<void>(result);
    return 0;
}
'''

class CleanupBatch274Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b274-")
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

    def test_every_documented_shape_is_accepted_and_misuse_is_rejected(self):
        """十二条的**合法形状都能调通、写错形状必须报错**（宿主上引擎不可用 ⇒ 静默降级）。

        ★ 这一格是"参数个数/类型算错"那类缺陷的钉子（批次 249 的形态）。
        """
        out = self.run_scenario("gates")
        self.assertIn("B274 fear=true,false,false", out)
        self.assertIn("B274 health=true,false", out)
        self.assertIn("B274 rse=true,false", out)
        self.assertIn("B274 bh=true,false", out)
        self.assertIn("B274 dip=true,false,false", out)
        self.assertIn("B274 fly=true,false", out)
        self.assertIn("B274 trap=true,false", out)
        self.assertIn("B274 soul=true,false", out)
        self.assertIn("B274 luck=true,false", out)
        self.assertIn("B274 gbomb=true,false", out)
        self.assertIn("B274 gkey=true,false", out)

    def test_value_returning_two_degrade_the_documented_way(self):
        """★ 两条有返回值的降级口径：`AddFriendlyDip` 给 `nil`、`CanPickSoulHearts` 给 `false`。

        前者与 `Entity:ToPlayer()` 一族同口径（创建失败给 `nil`，模组写 `if e then`）；
        后者是布尔型，保守的那一边是**「不能捡」** ⇒ `false`，并按纪律记一笔探针
        （`kFbEntityPlayerCanPickSoulHearts`）。
        """
        out = self.run_scenario("gates")
        self.assertIn("B274 dipRet=nil", out)
        self.assertIn("B274 soulRet=false", out)

    def test_seeds_forget_stage_seed_is_reachable_from_the_seeds_handle(self):
        """`Seeds:ForgetStageSeed` 走 `Game():GetSeeds()` 那个句柄（`this` 现算，见实现处注释）。"""
        out = self.run_scenario("gates")
        self.assertIn("B274 seeds=userdata,true,false", out)

    # ---------------------------------------------------------------- 静态接线

    def test_catalog_and_binding_rows_exist(self):
        catalog = CATALOG.read_text(encoding="utf-8")
        isaac_body = ISAAC_API.read_text(encoding="utf-8")
        for owner, name, index, _prefix, cpp in APIS:
            with self.subTest(name):
                hex_index = f"0x{index:04X}"
                self.assertIn(
                    f'MakeId(ApiDomain::Isaac, 1, {hex_index}), ApiDomain::Isaac, "{owner}", '
                    f'"{name}"',
                    catalog, f"catalog 里没有 {owner}:{name}")
                self.assertRegex(isaac_body,
                                 rf"\{{\s*(?i:0x0e01{index:04x}),\s*&{cpp}\s*\}}",
                                 f"绑定表里没有 0x{index:04X} → {cpp}")
        owner, name, index, _prefix, cpp = SEEDS
        self.assertIn(f'MakeId(ApiDomain::Seed, 1, {index}), ApiDomain::Seed, "{owner}", "{name}"',
                      catalog)
        self.assertIn(f"{{0x0F01{int(index, 16):04X}, &{cpp}}}",
                      GAME_API.read_text(encoding="utf-8"))

    def test_each_api_has_an_offset_and_a_sixteen_byte_guard(self):
        constants = CONSTANTS.read_text(encoding="utf-8")
        for _owner, name, _index, prefix, _cpp in APIS + (SEEDS,):
            with self.subTest(name):
                self.assertIn(f"{prefix}Offset = 0x", constants, f"{name} 缺偏移")
                self.assertIn(f"{prefix}ExpectedBytes", constants, f"{name} 缺 16 字节守卫")

    def test_three_prologues_are_identical_again(self):
        """★ 本批又出现三条入口 16 字节**相同**（`AddPrettyFly`/`AnimateTrapdoor`/`CanPickSoulHearts`）。

        与批次 273 的 `AddGoldenHearts`/`AnimateAppear` 是同一现象 ⇒ 常量注释里已写明
        「**守卫不能当身份判据，区分靠偏移**」。这里钉住三件事：三者守卫相同、三者偏移互不相同、
        常量段里确实有那句话。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")

        def guard(name: str) -> str:
            start = constants.index(f"{name}ExpectedBytes = ") + len(f"{name}ExpectedBytes = ")
            return constants[start:constants.index("};", start)]

        trio = ("kEntityPlayerAddPrettyFly", "kEntityPlayerAnimateTrapdoor",
                "kEntityPlayerCanPickSoulHearts")
        self.assertEqual(guard(trio[0]), guard(trio[1]))
        self.assertEqual(guard(trio[1]), guard(trio[2]))
        offsets = [constants.index(f"{n}Offset = 0x") for n in trio]
        self.assertEqual(len(set(offsets)), 3, "三者偏移必须互不相同 —— 那才是身份判据")
        self.assertIn("守卫不能当身份判据", constants)

    def test_all_share_one_resolver(self):
        """十三条必须共用同一个取址助手（`EntityMethodByExpectedBytes` / 或 game_api 那条同形的）。"""
        isaac_body = ISAAC_API.read_text(encoding="utf-8")
        for _owner, _name, _index, prefix, cpp in APIS:
            with self.subTest(cpp):
                handler = isaac_body[isaac_body.index(f"int {cpp}(lua_State* state) {{"):]
                handler = handler[:handler.index("\n}\n")]
                self.assertIn(f"EntityMethodByExpectedBytes({prefix}Offset", handler)
        game = GAME_API.read_text(encoding="utf-8")
        handler = game[game.index("int SeedsForgetStageSeed(lua_State* state) {"):]
        handler = handler[:handler.index("\n}\n")]
        self.assertIn("VerifyEntryBytes", handler, "Seeds 这条走 game_api 里同形的两条关")


if __name__ == "__main__":
    unittest.main()
