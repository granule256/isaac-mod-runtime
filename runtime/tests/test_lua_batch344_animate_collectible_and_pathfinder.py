"""门禁：批次 344（2026-10-04）—— `EntityPlayer:AnimateCollectible` + `PathFinder:HasPathToPos`。

## 这一批是什么

| API | 处数 | 机制 | Switch 落点 |
| --- | --- | --- | --- |
| `EntityPlayer:AnimateCollectible(Collectible, AnimName?, SpriteAnimName?)` | **2** | **手写处理器**（字符串实参 + 两个**非空**字符串缺省） | 引擎**改名**后的 `Entity_Player::AnimatePickup(eCollectibleType, char const*, char const*) @ 0x2DD150` |
| `PathFinder:HasPathToPos(Vector Pos, boolean IgnorePoop)` | 1 | **引擎方法数据行**（本批新开 `FieldReceipt::PathFinder` + 形状 `BoolVector2RefBool`（纯数据）） | `NPCAI_Pathfinder::HasPathToPos(Vector2 const&, bool) const @ 0x42F6CC` |

依据 = `docs/取证-L组-两条手写处理器的可执行规格-20261004d.md` §B（AnimateCollectible，
独立复核 = `docs/取证-N组-独立复核Explode与AnimateCollectible-20261004e.md`）与
`docs/取证-J组-两条缺前置的补齐方案-20261004c.md` §3.1（HasPathToPos）。

## 本批的核心判据

1. ★★★ **`AnimateCollectible` 的两个缺省字符串必须是字面串**（`"Pickup"` /
   `"PlayerPickupSparkle"`），**不能是 `nullptr`**：引擎把它们喂 `ANM2::Play(char const*, bool)`，
   那里对名字做 `strcmp`、对 null **无检查** ⇒ 传 null 会读 NULL 段、当场崩。
   ★ 宿主里验不到"真的传了什么"（引擎调用在宿主里必然降级）⇒ 这条用**静态判据**钉住
   （源码里必须是 `luaL_optstring(state, 3, "Pickup")` / `… 4, "PlayerPickupSparkle"`）。
2. ★★ **`EntityNPC.Pathfinder` 只答一个键**：`npc.Pathfinder` 是 userdata（不是 `nil`），
   它是 `Entity_NPC + 0x408` 那个**内嵌** `NPCAI_Pathfinder`；**其余字段仍回落到 `Entity`**
   （`npc.Position` 照旧是 `Vector`）—— 证明 `PushEntityNpcField` 只截 `"Pathfinder"`。
3. ★★ **接收者是 `FieldReceipt::PathFinder`（严格校验句柄类型）**：这一条是**调用**，
   `HasPathToPos` 一进去就顺着 `this` 读一堆成员 ⇒ 拿别的对象当 `this` 会**野读**。
   宿主里用"把 `Pathfinder` 换成别的 userdata"验它被挡下（不报错、返回 `false`）。
4. ★ **降级口径**：宿主里模块块是零 ⇒ 入口字对不上 ⇒ `HasPathToPos` 必须返回 **`false`**
   （PC 返回 boolean），**不报错、也不是 `nil`**。

## 没验到的（真机项）

* 真机上 `player:AnimateCollectible(...)` 真的播了拾取动画（1 参走缺省 / 3 参显式各一次）。
* 真机上 `npc.Pathfinder:HasPathToPos(pos, false)` 对"被石头/坑挡住的 NPC"返回 `true`、
  对空房间返回 `false`（即引擎真的被调到、且读的是真 `this`）。
* ★ 内嵌偏移 `+0x408` 没有具名访问器（只有构造点 + 3 处同族旁证）⇒ 真机若发现答出的对象不对，
  第一嫌疑就是这一格。
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
FIELD_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "field_api.hpp"
METHOD_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "engine_method_api.hpp"
HANDLES = ROOT / "runtime" / "source" / "lua_object_handles.hpp"
SURFACE = ROOT / "runtime" / "tests" / "contract" / "test_engine_row_api_surface.py"
CONTRACT_PAGE = ROOT / "tools" / "pc_contract_docs" / "PathFinder.md"

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "entity_layout.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 341 的用例）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes
//   g_OwnerSlotBytes                         = Game*
//   Game + 玩家数组 begin/end                 = 只有一个元素的玩家指针数组
//   玩家对象首字                              = base + kEntityPlayerVtableOffset / Type = PLAYER
//   玩家对象 + kEntityParentOffset            = g_NpcBytes（本批那条 NPC）
//   NPC 对象首字                              = base + kEntityNpcVtableOffset / Type = NPC
//   NPC + kEntityNpcPathfinderOffset          = **内嵌**的 NPCAI_Pathfinder（就是 `npc.Pathfinder`
//                                               交出去的那个地址；内容无所谓，本批不读它）
//
// ★ 两条 API 在宿主里**入口字必然对不上**（模块块是零）⇒ 处理器/共享处理器走**静默降级** ——
//   这正是我们要验的那条路。★ 模块块**故意开得足够大**，盖住本批用到的最大引擎偏移：
//   不这么做就是一次越界读（`EngineEntryWordMatches` 对地址是裸 `memcpy`，没有边界判定）。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_NpcBytes;
std::uintptr_t g_EngineBase = 0;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void PublishFakeGame() {
    const std::size_t largestEngineOffset =
        kPathFinderHasPathToPosOffset > kEntityPlayerAnimateCollectibleOffset
            ? kPathFinderHasPathToPosOffset
            : kEntityPlayerAnimateCollectibleOffset;
    g_ModuleBytes.assign(largestEngineOffset + 16, 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, kEntityTypePlayer);

    //: 本条要的 NPC：vptr 落在 `Entity` 家族的 vtable 区间里、且不是那 13 个非 NPC 直接子类
    //: ⇒ `IsNpcFamilyEntity()` 为真。★ 对象块要盖住 `kEntityNpcPathfinderOffset`（内嵌子对象）
    //: 与 `Entity` 通用字段偏移（`npc.Position` 那条回落判据要读它）。
    static_assert(kEntityNpcPathfinderOffset < kEntityPlayerSize,
                  "the fake NPC block must cover the embedded NPCAI_Pathfinder");
    static_assert(kEntityPositionOffset + 2 * sizeof(float) <= kEntityPlayerSize,
                  "the fake NPC block must cover the generic Position field");
    g_NpcBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_NpcBytes, 0, g_EngineBase + kEntityNpcVtableOffset);
    //: ★ NPC 的身份判据是**只按 vptr**（`IsNpcFamilyEntity` = 落在 `Entity` 家族的 vtable 区间里、
    //: 且不是那 13 个已知非 NPC 直接子类）—— `Type` **不参与**判定（批次 285 的夹具同理）
    //: ⇒ 这里不写 `Type`（留 0），免得凭印象编一个不存在的常量。
    //: 内嵌子对象里放一个**非零**标记（本批不读它，只是让"句柄里真的存了那个地址"可核对）。
    WriteAt<std::uint32_t>(g_NpcBytes, kEntityNpcPathfinderOffset, 0x5AA55AA5u);

    WriteAt<std::uint64_t>(g_PlayerBytes, kEntityParentOffset, AddressOf(g_NpcBytes));

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
    if (std::strcmp(scenario, "npc") != 0 && std::strcmp(scenario, "anim") != 0) {
        return 91;
    }

    PublishFakeGame();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);
    std::printf("B344 base=%d\n", g_EngineBase != 0 ? 1 : 0);

    char script[4096];
    if (std::strcmp(scenario, "npc") == 0) {
        const char* s =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local function count(...) return select('#', ...) end"
            " local function val(f) local a,b = pcall(f); return tostring(b) end"
            " local p = Isaac.GetPlayer(0)"
            " local raw = p.Parent"
            " local npc = raw:ToNPC()"
            " print('B344 npckind=' .. type(npc))"
            // ★★ 属性接线：只答 'Pathfinder' 一个键；其余回落 Entity（Position 仍是 Vector）。
            " print('B344 pfkind=' .. type(npc.Pathfinder))"
            " print('B344 pffn=' .. type(npc.Pathfinder and npc.Pathfinder.HasPathToPos))"
            " print('B344 fallback=' .. type(npc.Position))"
            // ★ 宿主里入口字对不上 ⇒ 返回 false（PC 是 boolean），**不报错、也不是 nil**。
            " print('B344 callok=' .. ok(function() return npc.Pathfinder:HasPathToPos(Vector(1, 2), false) end))"
            " print('B344 callval=' .. tostring(npc.Pathfinder:HasPathToPos(Vector(1, 2), false)))"
            " print('B344 calltype=' .. type(npc.Pathfinder:HasPathToPos(Vector(1, 2), false)))"
            " print('B344 calln=' .. tostring(count(npc.Pathfinder:HasPathToPos(Vector(1, 2), false))))"
            // --- 参数闸门（形状 argumentCount = 2、无缺省）---------------------------
            " print('B344 noarg=' .. ok(function() return npc.Pathfinder:HasPathToPos() end))"
            " print('B344 noargerr=' .. val(function() return npc.Pathfinder:HasPathToPos() end))"
            " print('B344 onearg=' .. ok(function() return npc.Pathfinder:HasPathToPos(Vector(1, 2)) end))"
            " print('B344 three=' .. ok(function() return npc.Pathfinder:HasPathToPos(Vector(1, 2), false, 1) end))"
            " print('B344 badvec=' .. ok(function() return npc.Pathfinder:HasPathToPos(1, false) end))"
            " print('B344 badvecerr=' .. val(function() return npc.Pathfinder:HasPathToPos(1, false) end))";
        std::snprintf(script, sizeof(script), "%s", s);
    } else {
        const char* s =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local function count(...) return select('#', ...) end"
            " local function val(f) local a,b = pcall(f); return tostring(b) end"
            " local p = Isaac.GetPlayer(0)"
            " print('B344 animfn=' .. type(p.AnimateCollectible))"
            // 1 参（走两个缺省）与 3 参（显式）都必须**不报错**且返回 0 个值
            // （宿主里入口字对不上 ⇒ 静默降级；契约返回 void）。
            " print('B344 anim1=' .. ok(function() return p:AnimateCollectible(1) end))"
            " print('B344 anim1n=' .. tostring(count(p:AnimateCollectible(1))))"
            " print('B344 anim3=' .. ok(function() return p:AnimateCollectible(1, 'UseItem', 'PlayerPickup') end))"
            " print('B344 anim3n=' .. tostring(count(p:AnimateCollectible(1, 'UseItem', 'PlayerPickup'))))"
            // --- 参数闸门 -----------------------------------------------------------
            " print('B344 anim0=' .. ok(function() return p:AnimateCollectible() end))"
            " print('B344 anim0err=' .. val(function() return p:AnimateCollectible() end))"
            " print('B344 anim4=' .. ok(function() return p:AnimateCollectible(1, 'a', 'b', 'c') end))"
            " print('B344 animstr=' .. ok(function() return p:AnimateCollectible('x') end))"
            " print('B344 animstrerr=' .. val(function() return p:AnimateCollectible('x') end))";
        std::snprintf(script, sizeof(script), "%s", s);
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b344.lua");
    static_cast<void>(result);
    return 0;
}
'''


class Batch344AnimateCollectibleAndPathFinderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b344-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario):
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # ★ 批次 285 的教训：只回 stdout 时「Lua 报错」与「什么都没做」长得一样。
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主）

    def test_pathfinder_property_is_wired_and_falls_back_to_entity_fields(self):
        """★★ `EntityNPC.Pathfinder` 交出 userdata、方法挂上了，**其余键仍回落到 `Entity`**。

        * `npc.Pathfinder` 是 `userdata`（不是 `nil`，证明属性入口 + 句柄 + 元表三处都接上了）；
        * `npc.Pathfinder.HasPathToPos` 是 `function`（引擎方法行真的挂到了 `PathFinder` 元表上）；
        * `npc.Position` 仍是 `Vector`（`PushEntityNpcField` 只截 `"Pathfinder"`、其余让给了
          `PushEntityField` —— 这正是 `IndexEntity` 新加的 `Npc` 分支要证明的事）。
        """
        out = self.run_scenario("npc")
        self.assertIn("B344 base=1", out)
        self.assertIn("B344 npckind=userdata", out)
        self.assertIn("B344 pfkind=userdata", out)
        self.assertIn("B344 pffn=function", out)
        self.assertIn("B344 fallback=userdata", out)

    def test_has_path_to_pos_degrades_to_false_and_gates_arguments(self):
        """★ 宿主里入口字对不上 ⇒ 返回 `false`（不是报错、不是 `nil`）+ 两格参数闸门。

        形状 `BoolVector2RefBool` 的 `argumentCount = 2` 且 `optionalArgumentCount = 0`
        ⇒ 0 个 / 1 个 / 3 个实参都报错，消息逐字 `PathFinder:HasPathToPos expects 2 argument(s)`；
        第 1 个实参必须能解成 `Vector`（`EngineArgKind::Vector2Ref` 走
        `luaL_testudata(…, kVectorMetatable)`）⇒ 传数字同样报上面那条消息。
        """
        out = self.run_scenario("npc")
        self.assertIn("B344 callok=true", out)
        self.assertIn("B344 callval=false", out)
        self.assertIn("B344 calltype=boolean", out)
        self.assertIn("B344 calln=1", out)
        self.assertIn("B344 noarg=false", out)
        self.assertIn("PathFinder:HasPathToPos expects 2 argument(s)", out)
        self.assertIn("B344 onearg=false", out)
        self.assertIn("B344 three=false", out)
        self.assertIn("B344 badvec=false", out)
        #: ★ 报错消息里带 `luaL_error` 的位置前缀（`<chunk>:<行>: `），所以这里只比子串。
        self.assertIn("B344 badvecerr=", out)

    def test_animate_collectible_is_wired_and_degrades_silently(self):
        """★ `EntityPlayer:AnimateCollectible` 挂上了、1 参/3 参都放行、宿主里静默降级。

        * `type(p.AnimateCollectible) == "function"`；
        * `p:AnimateCollectible(1)`（走两个字符串缺省）与
          `p:AnimateCollectible(1, "UseItem", "PlayerPickup")` 都**不报错**、返回 **0** 个值
          （契约返回 `void`；宿主里入口字对不上 ⇒ 不调引擎）；
        * 参数闸门：0 个实参、4 个实参、第 1 个不是整数 ⇒ 各报一条消息（逐字见下）。
        """
        out = self.run_scenario("anim")
        self.assertIn("B344 base=1", out)
        self.assertIn("B344 animfn=function", out)
        self.assertIn("B344 anim1=true", out)
        self.assertIn("B344 anim1n=0", out)
        self.assertIn("B344 anim3=true", out)
        self.assertIn("B344 anim3n=0", out)
        self.assertIn("B344 anim0=false", out)
        self.assertIn(
            "EntityPlayer:AnimateCollectible expects a collectible and optionally an animation "
            "name and a sprite animation name",
            out)
        self.assertIn("B344 anim4=false", out)
        self.assertIn("B344 animstr=false", out)
        self.assertIn("EntityPlayer:AnimateCollectible expects an integer collectible", out)

    # ---------------------------------------------------------------- 静态接线

    def test_the_default_strings_are_literal_not_null(self):
        """★★★ 本批最要紧的一条：缺省的两个字符串**必须是字面串**，不许是 `nullptr`。

        引擎把两个指针喂 `ANM2::Play(char const*, bool)`，那里对名字做 `strcmp`、**对 null
        无检查** ⇒ 传 `nullptr` 会读 NULL 段、当场崩。宿主里验不到"真的传了什么"（引擎调用
        必然降级）⇒ 这条用**静态判据**钉死。
        """
        api = ISAAC_API.read_text(encoding="utf-8")
        self.assertIn('luaL_optstring(state, 3, "Pickup")', api)
        self.assertIn('luaL_optstring(state, 4, "PlayerPickupSparkle")', api)
        #: ★ 反回归：不许出现"缺省传 nullptr / NULL"的写法。
        self.assertNotIn('luaL_optstring(state, 3, nullptr)', api)
        self.assertNotIn('luaL_optstring(state, 4, nullptr)', api)

    def test_wiring(self):
        """目录行 / 绑定行 / 引擎方法行 / 新 receipt / 新形状 / 视图五处 / 偏移常量。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        api = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        field_header = FIELD_HEADER.read_text(encoding="utf-8")
        method_header = METHOD_HEADER.read_text(encoding="utf-8")
        handles = HANDLES.read_text(encoding="utf-8")
        surface = SURFACE.read_text(encoding="utf-8")

        # --- 目录行（Isaac 域 0x00F6 / 0x00F7）----------------------------------
        for index, owner, name in ((0x00F6, "EntityPlayer", "AnimateCollectible"),
                                   (0x00F7, "PathFinder", "HasPathToPos")):
            with self.subTest(api=f"{owner}:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, '
                    f'"{owner}", "{name}"', catalog, f"目录里没有 {owner}:{name}")

        # --- 手写绑定行（AnimateCollectible）-------------------------------------
        self.assertIn("{0x0E0100F6, &EntityPlayerAnimateCollectible},", api)
        self.assertRegex(api, r"std::uintptr_t EntityPlayerAnimateCollectibleMethod\(\) noexcept")
        self.assertRegex(api, r"int EntityPlayerAnimateCollectible\(lua_State\* state\)")
        #: ★ 反回归：它是**手写**，不许被塞进引擎方法行表。
        self.assertNotRegex(api, r"0x0E0100F6[^\n]*EngineCallShape")

        # --- 引擎方法行（HasPathToPos）-------------------------------------------
        self.assertRegex(
            api,
            r"\{0x0E0100F7,\s*kPathFinderHasPathToPosOffset,\s*"
            r"kPathFinderHasPathToPosEntryWord,\s*FieldReceipt::PathFinder,\s*"
            r"EngineCallShape::BoolVector2RefBool,\s*2,\s*0xFF\}",
            "HasPathToPos 的引擎方法行缺失或形状/接收者不对")
        #: ★ 反回归：它是**调用**，不许被塞进字段行表。
        self.assertNotRegex(api, r"0x0E0100F7[^\n]*FieldKind::")

        # --- 新 receipt / 新形状 -------------------------------------------------
        self.assertIn("PathFinder = 12,", field_header)
        self.assertIn("case FieldReceipt::PathFinder:", api)
        self.assertIn("BoolVector2RefBool = 35,", method_header)
        self.assertRegex(
            api,
            r"\{2,\s*\{EngineArgKind::Vector2Ref,\s*EngineArgKind::Bool,[\s\S]{0,240}?"
            r"EngineReturnKind::Bool,\s*FieldReceipt::Entity,\s*IntArgumentGuard::None,\s*0,\s*"
            r"\{0, 0, 0\}\}",
            "形状 35 的描述符行缺失")

        # --- 视图五处接线 -------------------------------------------------------
        self.assertIn('inline constexpr char kPathFinderMetatable[] = "IsaacRuntime.PathFinder";',
                      handles)
        self.assertIn("struct PathFinderHandle {", handles)
        self.assertIn("void PushPathFinderHandle(lua_State* state, std::uintptr_t pathfinder,std::uintptr_t owner)", api)
        self.assertIn("PushPathFinderHandle(state, entity + kEntityNpcPathfinderOffset,entity)", api)
        self.assertIn("int PathFinderIndex(lua_State* state)", api)
        self.assertIn("luaL_newmetatable(state, kPathFinderMetatable)", api)
        self.assertIn("bool PushEntityNpcField(lua_State* state, std::uintptr_t entity,",
                      api)
        self.assertIn('std::strcmp(field, "Pathfinder") != 0', api)
        #: ★ `IndexEntity` 的 `Npc` 分支必须真的存在（否则属性没有入口）。
        self.assertRegex(api, r"view == EntityView::Npc\)\s*\{[\s\S]{0,400}PushEntityNpcField")

        # --- 偏移常量 -----------------------------------------------------------
        for needle in (
                "inline constexpr uintptr_t kEntityPlayerAnimateCollectibleOffset = 0x2DD150;",
                "inline constexpr std::uint32_t kEntityPlayerAnimateCollectibleEntryWord = 0xD10743FFu;",
                "inline constexpr uintptr_t kEntityNpcPathfinderOffset = 0x408;",
                "inline constexpr uintptr_t kPathFinderHasPathToPosOffset = 0x42F6CC;",
                "inline constexpr std::uint32_t kPathFinderHasPathToPosEntryWord = 0xA9BA7BFDu;"):
            self.assertIn(needle, constants, f"常量缺失：{needle}")

        # --- 表面表（`test_engine_row_api_surface` 按 Lua 名字钉形状）-------------
        self.assertIn('"PathFinder:HasPathToPos": "BoolVector2RefBool"', surface)

        # --- 契约页必须进了仓（台账引的是它）-------------------------------------
        self.assertTrue(CONTRACT_PAGE.is_file(), "PathFinder.md 没有 vendor 进 tools/pc_contract_docs/")

    def test_the_load_bearing_evidence_is_recorded(self):
        """★★ 两条最容易做错的地方必须在常量段里写清依据（后人照做时按它走）。

        * `AnimateCollectible` 是**改名**：引擎里没有同名符号，底座是
          `AnimatePickup(eCollectibleType, …)` 那条重载（同族 5 条，选错不报错只播错动画）；
        * 缺省字符串**必须**是字面串（`ANM2::Play` 的 `strcmp` 对 null 无检查）；
        * `+0x408` 的四条证据（构造点 + `ai_poky` / `ai_stonehead` / `Init` 三处旁证），
          且 `Entity_Familiar` 的 `+0x5F8` **不做**（PC 的 `EntityFamiliar` 页没有这个属性）。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        for needle in ("0x2DD150", "0xD10743FF", "AnimatePickup", "ANM2::Play", "strcmp",
                       "PlayerPickupSparkle", "0x42F6CC", "0xA9BA7BFD", "0x408",
                       "ai_poky", "ai_stonehead", "0x5F8", "改名", "EntityPlayer.md",
                       "PathFinder.md", "EntityNPC.md"):
            self.assertIn(needle, constants, f"证据 {needle} 没有写进常量段")


if __name__ == "__main__":
    unittest.main()
