"""门禁：`EntityNPC` 视图 + `Morph` 家族两条（批次 285，2026-10-02）。

## 这一批是什么

| API | 引擎入口 | 形态 | 语料调用点 |
| --- | --- | --- | --- |
| `EntityNPC:Morph(EntityType, int, int, int)` | `Entity_NPC::Morph(eEntityType, u32, u32, int)` @ `0x10FAF4` | 4 整数 → 布尔 | 2（报告按名字聚合） |
| `EntityPickup:Morph(EntityType, int, int, b, b, b)` | `Entity_Pickup::Morph(eEntityType, u32, u32, bool, bool, bool)` @ `0x26BD14` | 3 整数 + 3 布尔（**尾部 3 个可省**）→ `void` | 至少 8（5 个模组） |

## ★ 为什么要先建 `EntityNPC` 视图

`Entity:ToNPC()` 以前压的是**基类 `Entity` 元表** ⇒ `EntityNPC` 页上的方法（`Morph` 等）
**没有地方挂**。本批照批次 281/282 的"视图六处接线"给 `EntityNPC` 建了独立视图：

① `lua_object_handles.hpp` 加元表名 `kEntityNPCMetatable`；② `EntityView` 加枚举值 `Npc`；
③ `IndexEntity` 的 `else` 分支天然覆盖（字段回落 `Entity`，`Scale` 那条由 `IsNpcFamilyEntity` 把关）；
④ `EntityViewMetatable` 让 `Npc` 返回新元表名；⑤ **`CheckEntityHandle` 与 `EntityReceiverOrError`
认这张元表**（漏了 = 死代码）；⑥ `RegisterViewMetatables` 建表 + `EntityNpcIndex` 作 `__index`。
★ 连带：目录行 owner = `EntityNPC`；`test_api_catalog.py` 的「文件 → 允许的 owner」表加一项。

## ★ `Morph` 两个 owner 是**兄弟类**，不是重写

`Morph` 在整份 `Repentance.nro` 里只有 `Entity_NPC::Morph` 与 `Entity_Pickup::Morph` 两条
mangled 命中（判据 = 扫全镜像，不是数 `dynsym`，也不是靠名字眼熟 —— 批次 284 立的尺子）。
两者都是 `Entity` 的**直接子类**，彼此没有继承关系 ⇒ 直调基类地址不会跳过虚分派。

## ★ `EntityPickup:Morph` 的"尾部 3 个可省"是硬要求

PC 契约 `tools/pc_contract_docs/EntityPickup.md:40` 里后 3 个布尔带缺省值 `false`，而语料里
两种写法都有：`ChallengeAPI/scripts/challengeapi/goals/hooks/polaroid_negative.lua:33` 只传 3 个、
`CyclingItemsAPI/main.lua:392` 传 6 个 ⇒ 形状必须声明"尾部 3 个可省"，否则 3 参那条调用会
因为"参数个数严格相等"直接报错、摘掉整条模组回调（批次 207 `BoolOpt1` 那条教训）。

## 宿主验到了什么、没验到什么

* **验到（运行期事实，不只是读源码）**。难点是"宿主怎么拿到一个非玩家句柄" —— 批次 281 就是
  卡在这里、行为用例只能 `skipTest`：`Isaac.GetPlayer(0)` 会把 vptr **精确等于** `Entity_Player`
  的对象交出来（`ResolveEntityPlayer` 第 8 档），所以"把伪造对象做成 NPC"这条路是堵死的。
  **本批用 `Entity.Parent` 绕开**：那个字段的实现是把 `entity + 0x390` 里的指针**原样**包成句柄
  （`PushEntityHandle` 自身不做任何校验），而玩家对象那块内存由我们伪造 ⇒ 把假玩家的 `Parent`
  指向一个"NPC 对象"，`p.Parent` 就交出了指向它的句柄，再 `:ToNPC()` / `:ToPickup()` 便走
  真实路径拿到目标视图。于是下面这些**全部是真跑出来的**：

  | 调用 | 期望 | 它证明了什么 |
  | --- | --- | --- |
  | `player:ToNPC()` / `ToPickup()` | `nil` | 玩家 vtable 在那 13 个非 NPC 子类里 ⇒ 转换失败口径正确 |
  | `player.Parent` | `userdata` | 我们造出了非玩家句柄（这条路本身也是本批方法的入口假设） |
  | `npc:ToNPC()` | `userdata` | `EntityNPC` 元表**真的建成并挂上了**（没建就是 `nil`） |
  | `npc:Morph(1,2,3,4)` | 不报错 | 数据行挂到了 `EntityNPC` 页上、闸门认识这张表 |
  | `npc:Morph(1,2,3)` / `(1,2,3,4,5)` / `()` | 报错 | 参数个数闸门是**恰好 4** |
  | `npc.Scale` / `npc:GetSprite()` | 有值 / 不报错 | 字段与方法都**回落到 `Entity`**，老用法不退化 |
  | `pickup:Morph(1,2,3)` / `(1,2,3,true,false,true)` | 不报错 | "尾部 3 个可省"真的放行 3 参与 6 参 |
  | `pickup:Morph(1,2)` / `(1,2,3,true,false,true,1)` | 报错 | 下限 3、上限 6 —— 少了/多了都挡 |
  | `type(pickup.CanReroll)` / `pickup:ToPickup()` | `function` / `userdata` | 反回归：`EntityPickup` 页原有的方法没被本批挤掉，且闸门仍认这张表 |

  ★ 这些是"视图六处接线真的生效"的硬判据 —— 元表没建 / `__index` 没装 / 方法没挂到
  `EntityNPC` 页 / 闸门没认这张表，上面任何一条都会变成 `nil` 或直接抛错（批次 207/281 都
  栽在"少了某一处 ⇒ 死代码"，而宿主用例正是当时抓出它的东西）。
* **没验**：`Morph` 到底有没有真的改到引擎状态、返回值对不对。宿主没有引擎 —— 伪造的模块块
  里那两个偏移处是一片零，方法解析（`EngineOffsetAddress` + 入口 word 核对）必然失效，
  于是按 PC 语义**静默降级**（Bool 压 `false`、Void 什么都不做）。这一层只能真机看（作业单 V36）。
* ★ 本批第一版曾打算从 Lua 注册表读元表来证明"表真的建了"（`debug.getregistry`）——**那条路
  不通**：我们这边的 `debug` 是手搓的精简库、**只有 `getinfo`**（登记在
  `api_catalog.cpp:1167`，由 `lua_runtime.cpp` 的 `RegisterDebugLibrary` 建表）。
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
HANDLES = ROOT / "runtime" / "source" / "lua_object_handles.hpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
SHAPES = ROOT / "runtime" / "src" / "interfaces" / "lua" / "engine_method_api.hpp"
CATALOG_TEST = ROOT / "runtime" / "tests" / "contract" / "test_api_catalog.py"

#: `(owner, 名字, 域内序号, 常量前缀, 形状, 参数个数)`
APIS = (
    ("EntityNPC", "Morph", 0x00C0, "kEntityNpcMorph", "BoolIntIntIntInt", 4),
    ("EntityPickup", "Morph", 0x00C1, "kEntityPickupMorph", "VoidIntIntIntBoolBoolBoolOpt3", 6),
)


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 281/284 的用例，外加"目标对象"一块）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_Game 变量（槽里是**变量地址**，不是对象）
//   g_Game 变量            = Game*
//   Game + kGamePlayerArrayBegin/End = 只有一个元素的玩家指针数组
//   玩家对象首字            = base + kEntityPlayerVtableOffset（`GetPlayer` 要它）
//   玩家对象 + kEntityParentOffset = &目标对象（★ 本批的关键，见下）
//   目标对象首字            = base + <本场景选的 vtable 偏移>，`Type` 按需
//
// ★★ 怎么拿到一个"非玩家实体"的句柄（批次 281 卡在这里、行为用例只能 skip）：
//   `Isaac.GetPlayer(0)` 会把 vptr **精确等于** `Entity_Player` 的对象交出来（`ResolveEntityPlayer`
//   第 8 档校验），所以"把对象做成 NPC"这条路被堵死。但 `Entity.Parent`（PC 的通用字段，
//   EID 的 `main.lua:1089` 就读它）的实现是"把 `entity + 0x390` 里那个指针**原样**包成句柄"
//   （`PushEntityHandle` 自身**不做任何校验**，身份判据全在后续使用处），而玩家对象这块内存
//   由我们伪造 ⇒ 于是 `p.Parent` 就能交出一个指向任意"实体"的句柄，再 `:ToNPC()` / `:ToPickup()`
//   便走真实路径拿到 `EntityNPC` / `EntityPickup` 视图。
//
// ★ 模块块按 `kGameOwnerGlobalSlotOffset + 8`（≈ 11.2 MiB，正好是模块映像的量级）分配，
//   **已经覆盖**本批要读的三个方法偏移（`kEntityNpcMorphOffset` 0x10FAF4、
//   `kEntityPickupMorphOffset` 0x26BD14、`kEntityPickupCanRerollOffset` 0x26AFA8）
//   ⇒ 那些"模块基址 + 偏移"的读落在我们自己的零块里：宿主没有 `svcQueryMemory`，
//   越界读不会返回 false 而是**真去读**，所以块必须自己够大（下面有 static_assert 钉住）。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_TargetBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::uintptr_t g_EngineBase = 0;

//: 本场景要把"目标对象"做成哪一种实体 —— 只改这两个字段就能让 `ToNPC`/`ToPickup` 认它。
std::uintptr_t g_TargetVtableOffset = kEntityPlayerVtableOffset;
std::uint32_t g_TargetType = kEntityTypePlayer;

static_assert(kEntityParentOffset + sizeof(std::uint64_t) <= kEntityPlayerSize,
              "the fake player must be big enough to hold the Parent pointer");
static_assert(kEntityNpcMorphOffset < kGameOwnerGlobalSlotOffset,
              "module block must cover the EntityNPC::Morph entry read");
static_assert(kEntityPickupMorphOffset < kGameOwnerGlobalSlotOffset,
              "module block must cover the Entity_Pickup::Morph entry read");
static_assert(kEntityPickupCanRerollOffset < kGameOwnerGlobalSlotOffset,
              "module block must cover the Entity_Pickup::CanReroll read");

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

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, kEntityTypePlayer);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityPlayerTypeOffset, 0);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityPlayerIndexOffset, 0);

    //: 「目标对象」：本场景要交出去的那个非玩家实体（NPC 或掉落物）。
    g_TargetBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_TargetBytes, 0, g_EngineBase + g_TargetVtableOffset);
    WriteAt<std::uint32_t>(g_TargetBytes, kEntityTypeOffset, g_TargetType);
    //: ★ 把它挂到玩家的 `Parent` 上 —— `p.Parent` 于是交出一张指向它的实体句柄。
    WriteAt<std::uint64_t>(g_PlayerBytes, kEntityParentOffset, AddressOf(g_TargetBytes));

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
    if (std::strcmp(scenario, "npc") == 0) {
        // `ToNPC()` 的判据只有"类身份"（`IsNpcFamilyEntity`），不看 `Type`；这里随便给一个。
        g_TargetVtableOffset = kEntityNpcVtableOffset;
        g_TargetType = kEntityTypeTear;
    } else if (std::strcmp(scenario, "pickup") == 0) {
        // `ToPickup()` 除了精确 `vptr` 还要 `Type == ENTITY_PICKUP`。
        g_TargetVtableOffset = kEntityPickupVtableOffset;
        g_TargetType = kEntityTypePickup;
    } else if (std::strcmp(scenario, "player") == 0) {
        // 目标对象用不上（本场景只验"玩家自己转不成 NPC"），给个玩家 vtable 即可。
        g_TargetVtableOffset = kEntityPlayerVtableOffset;
        g_TargetType = kEntityTypePlayer;
    } else {
        return 91;
    }
    PublishFakeGame();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script = nullptr;
    if (std::strcmp(scenario, "player") == 0) {
        script =
            "local p = Isaac.GetPlayer(0)"
            " print('B285 pkind=' .. type(p))"
            " print('B285 tonpc=' .. tostring(p:ToNPC()))"
            " print('B285 topickup=' .. tostring(p:ToPickup()))";
    } else if (std::strcmp(scenario, "npc") == 0) {
        script =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local p = Isaac.GetPlayer(0)"
            " local raw = p.Parent"
            " print('B285 rawkind=' .. type(raw))"
            " local n = raw:ToNPC()"
            " print('B285 npckind=' .. type(n))"
            " print('B285 morph4=' .. ok(function() return n:Morph(1, 2, 3, 4) end))"
            " print('B285 morph3=' .. ok(function() return n:Morph(1, 2, 3) end))"
            " print('B285 morph5=' .. ok(function() return n:Morph(1, 2, 3, 4, 5) end))"
            " print('B285 morph0=' .. ok(function() return n:Morph() end))"
            " print('B285 npcscale=' .. tostring(n.Scale ~= nil))"
            " print('B285 basefallback=' .. ok(function() return n:GetSprite() end))";
    } else {
        script =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local u = Isaac.GetPlayer(0).Parent:ToPickup()"
            " print('B285 upkind=' .. type(u))"
            " print('B285 pmorph6=' .. ok(function() return u:Morph(1, 2, 3, true, false, true) end))"
            " print('B285 pmorph3=' .. ok(function() return u:Morph(1, 2, 3) end))"
            " print('B285 pmorph2=' .. ok(function() return u:Morph(1, 2) end))"
            " print('B285 pmorph7=' .. ok("
            "   function() return u:Morph(1, 2, 3, true, false, true, 1) end))"
            " print('B285 pickfn=' .. type(u.CanReroll))"
            " print('B285 retopickup=' .. type(u:ToPickup()))";
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b285.lua");
    static_cast<void>(result);
    return 0;
}
'''


class EntityNpcMorphBatch285Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b285-")
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
        #: 连 `stderr` 一起交出去：脚本里报了 Lua 错时，`print` 之前就中断、stdout 会是空的，
        #: 只回 stdout 的话失败信息等于"什么都没说"（本批第一版就吃了这个亏）。
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主）

    def test_npc_view_really_exposes_morph(self):
        """★ 把伪造对象做成 NPC ⇒ 拿到**真的 `EntityNPC` 句柄**，`Morph` 的闸门逐条验。

        为什么这是硬判据：`EntityNPC` 元表没建 ⇒ `ToNPC()` 给 `nil`；`__index` 没装 ⇒
        句柄取不到任何东西；方法没挂到 `EntityNPC` 页 ⇒ `n:Morph` 是 `nil`（报错）；
        `CheckEntityHandle`/`EntityReceiverOrError` 没认这张表 ⇒ 走不到接收者校验。
        四条里任何一条断了，下面都会红。
        """
        out = self.run_scenario("npc")
        self.assertIn("B285 rawkind=userdata", out)
        self.assertIn("B285 npckind=userdata", out)
        #: 恰好 4 个整数参数（少了、多了都挡）。
        self.assertIn("B285 morph4=true", out)
        for too_few_or_many in ("B285 morph3=false", "B285 morph5=false", "B285 morph0=false"):
            self.assertIn(too_few_or_many, out)
        #: 字段回落 `Entity`（`Scale` 只挂在 NPC 页上 —— 它能读到值，说明视图认得出这是 NPC 家族）。
        self.assertIn("B285 npcscale=true", out)
        #: 方法回落 `Entity`（`GetSprite` 在基类页上）⇒ 老用法不退化。
        self.assertIn("B285 basefallback=true", out)

    def test_pickup_view_really_exposes_morph_with_optional_tail(self):
        """★ `EntityPickup:Morph` 的"尾部 3 个可省"要真的放行 3 参、6 参，且挡掉 2 参、7 参。"""
        out = self.run_scenario("pickup")
        self.assertIn("B285 upkind=userdata", out)
        self.assertIn("B285 pmorph6=true", out)
        self.assertIn("B285 pmorph3=true", out)
        self.assertIn("B285 pmorph2=false", out)
        self.assertIn("B285 pmorph7=false", out)
        #: 反回归：`EntityPickup` 页原有的方法不能被本批的表改动挤掉。
        #: ★ 这里只查"方法在不在"与"已经是该视图再转换能不能走通"，**不真调引擎方法** ——
        #: `CanReroll` 是手写处理器，它遇到"入口指纹对不上"会**按设计报错**
        #: （宿主没有引擎 ⇒ 必然报错），拿它当反回归判据会把"缺引擎"误读成"回归"。
        self.assertIn("B285 pickfn=function", out)
        self.assertIn("B285 retopickup=userdata", out)

    def test_player_is_not_an_npc(self):
        """★ PC 的"转换失败返回 `nil`"口径：玩家（vtable 在那 13 个非 NPC 子类里）转不出 NPC。"""
        out = self.run_scenario("player")
        self.assertIn("B285 pkind=userdata", out)
        self.assertIn("B285 tonpc=nil", out)
        self.assertIn("B285 topickup=nil", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 形状与参数个数 / owner —— 完成定义台账引用的就是这个方法。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        shapes = SHAPES.read_text(encoding="utf-8")
        owner_table = CATALOG_TEST.read_text(encoding="utf-8")

        for owner, name, index, prefix, shape, arity in APIS:
            with self.subTest(api=f"{owner}:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, "{owner}", '
                    f'"{name}"',
                    catalog, f"目录里没有 {owner}:{name}")
                #: 数据行：`{0x0E01____, k…Offset, k…EntryWord, FieldReceipt::Entity, Shape, N,`
                self.assertRegex(
                    isaac,
                    rf"\{{\s*(?i:0x0e01{index:04x}),\s*{prefix}Offset,\s*{prefix}EntryWord,\s*"
                    rf"FieldReceipt::Entity,\s*EngineCallShape::{shape},\s*{arity},",
                    f"数据行缺失或形状/参数个数不对：{owner}:{name}")
                self.assertIn(f"inline constexpr uintptr_t {prefix}Offset = 0x", constants)
                self.assertIn(f"inline constexpr std::uint32_t {prefix}EntryWord = 0x", constants)

        #: `EntityNPC` 是新 owner ⇒ 必须登记进「文件 → 允许的 owner」表，否则 `api_catalog` 判红。
        self.assertIn('"EntityNPC"', owner_table)
        #: ★ 数据行 id 不许再挂手写处理器 —— 这里顺带确认没有为它写 `&…` 绑定行。
        self.assertNotRegex(catalog, r"\{0x0E0100C0,\s*&\w+\}")
        self.assertNotRegex(catalog, r"\{0x0E0100C1,\s*&\w+\}")
        #: 两种新形状都得在枚举里（形状是数据，`kEngineCallShapes` 的行数要与枚举一一对应）。
        self.assertRegex(shapes, r"\bBoolIntIntIntInt\s*=\s*28")
        self.assertRegex(shapes, r"\bVoidIntIntIntBoolBoolBoolOpt3\s*=\s*29")

    def test_the_new_view_is_recognised_by_the_handle_gates(self):
        """★ 反回归（批次 207 踩过的形态）：新视图**必须**在 `CheckEntityHandle` 与
        `EntityReceiverOrError` 里各认一次；漏了会让"已经是该视图再转换"的分支变成**死代码**。"""
        isaac = ISAAC_API.read_text(encoding="utf-8")
        handles = HANDLES.read_text(encoding="utf-8")

        self.assertIn('kEntityNPCMetatable[] = "IsaacRuntime.EntityNPC"', handles)
        self.assertIn("luaL_testudata(state, index, kEntityNPCMetatable)", isaac)  # CheckEntityHandle
        self.assertIn("luaL_testudata(state, 1, kEntityNPCMetatable)", isaac)     # EntityReceiverOrError
        self.assertIn("lua_setfield(state, -2, \"__index\")", isaac)
        #: `Entity:ToNPC()` 必须压**新视图**，不再压基类元表（否则本批等于没做）。
        self.assertIn("EntityViewMetatable(EntityView::Npc)", isaac)
        self.assertIn("int EntityNpcIndex(lua_State* state)", isaac)
        self.assertIn("static_cast<void>(AttachEntityNPCMethods(state))", isaac)

    def test_morph_belongs_to_two_sibling_classes(self):
        """★ 反回归：常量段里必须写明两条 `Morph` 是**兄弟类**（不是重写）—— 本批的进批依据。"""
        constants = CONSTANTS.read_text(encoding="utf-8")
        self.assertIn("Entity_NPC::Morph(eEntityType, u32 Variant, u32 SubType, int ChampionColorIdx)",
                      constants)
        self.assertIn("Entity_Pickup::Morph", constants)
        self.assertIn("兄弟类", constants)


if __name__ == "__main__":
    unittest.main()
