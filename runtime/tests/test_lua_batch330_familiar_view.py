"""门禁：`EntityFamiliar` 视图 + `FollowParent()` / `AddToFollowers()`（批次 330，2026-10-03）。

## 这一批是什么

| API | 契约 | 引擎侧 | 形状 | 语料 |
| --- | --- | --- | --- | --- |
| `EntityFamiliar:FollowParent()` | `EntityFamiliar.md:65` | `Entity_Familiar::follow_parent()` @ `0xAEC14` | `EngineCallShape::Void0`（复用现成） | 2 处 |
| `EntityFamiliar:AddToFollowers()` | `EntityFamiliar.md:47` | `Entity_Familiar::add_to_followers()` @ `0xAC958` | 同上 | 3 处 |

**本批真正的产出是「视图」**：`Entity:ToFamiliar()` 此前压的是**基类 `Entity` 元表**
（批次 9 起就是），于是 `EntityFamiliar` 页上的方法**没有地方挂** ——
`familiar:FollowParent()` 报 "attempt to call a nil value"、**整条模组回调被摘**。
本批照批次 285 给 `EntityNPC` 立的那一套接线建 `kEntityFamiliarMetatable`（六处，见下）。

## 六处接线（少一处就是"方法挂不上/句柄不认"，而且只在真机上才发现）

1. `runtime/source/lua_object_handles.hpp` 的 `kEntityFamiliarMetatable`；
2. `EntityView::Familiar`；
3. `EntityViewMetatable()` 的分支；
4. `EntityFamiliarIndex()`（= `IndexEntity(state, EntityView::Familiar)`）；
5. `CheckEntityHandle()` 的多张元表；
6. `Entity:ToFamiliar()` 改压新元表。
   ★ 另外还有第 7 处（本批特有）：`FieldReceipt::EntityFamiliar`（精确 vptr + 类型）。

## 宿主验到了什么、没验到什么

* **验到**：
  - `ToFamiliar()` 现在交出的是**新元表**的句柄（与 `Entity.Parent` 那张基类元表**不同一张**）；
  - 两条方法真的挂在新元表上（`type(fam.FollowParent) == "function"`）；
  - **基类那一侧没有退化**：字段/方法仍然回落（`fam.Player` 要得住、`:GetSprite()` / `:ToPlayer()`
    仍是函数、`fam:ToFamiliar()` 幂等）；
  - 参数闸门：多给一个实参 ⇒ 报错，且消息里有 API 名字；
  - ★★ **接收者闸门**：点号调用时显式传一个**别的实体**（`fam.FollowParent(p.Parent)`）
    ⇒ **不报错、什么都不做** —— 这正是"精确判接收者"要挡的那条路（引擎那条路一进去就解引用
    `[this+0xf50]`，拿错对象会野读）；
  - 不是 familiar 的对象上 `ToFamiliar()` 仍然给 `nil`（老行为没变）。
* **没验**：
  1. **引擎那一步真的做了什么** —— 宿主里没有引擎函数 ⇒ "入口取不到"那条降级**必然命中**，
     所以宿主只能证明"接线对、形状对、不该调的时候没调" ⇒ **真值只能真机**。
  2. "引擎入口首字对不上"那条分支（宿主里入口本来就是 0，走的是同一个降级出口）。
"""

import re
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
HANDLES = ROOT / "runtime" / "source" / "lua_object_handles.hpp"

#: `(API 名, 域内序号, 偏移常量, 入口字常量)`。
FAMILIAR_APIS = (
    ("FollowParent", 0x00E2, "kEntityFamiliarFollowParentOffset",
     "kEntityFamiliarFollowParentEntryWord"),
    ("AddToFollowers", 0x00E3, "kEntityFamiliarAddToFollowersOffset",
     "kEntityFamiliarAddToFollowersEntryWord"),
)

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "entity_layout.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 316/285 的用例）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes
//   g_OwnerSlotBytes                         = Game*
//   Game + kGamePlayerArrayBegin/End         = 只有一个元素的玩家指针数组
//   玩家对象首字                              = base + kEntityPlayerVtableOffset / Type = PLAYER
//   玩家对象 + kEntityParentOffset            = g_TargetBytes（**本批要造的那个实体**）
//
// ★★ 造"任意实体句柄"用的是批次 285 立的那招：`Entity.Parent` 只是把指针原样包成句柄
//    （身份校验全在后续使用处）⇒ 把假玩家的 Parent 指向目标块，`p.Parent` 就交出一个
//    **可控类型**的实体句柄。目标块的 vptr 决定它是 familiar 还是别的。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_FamiliarBytes;
std::vector<unsigned char> g_OtherBytes;
std::uintptr_t g_EngineBase = 0;
bool g_TargetIsFamiliar = true;

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

    // 假玩家：**精确**的 Entity_Player vptr ⇒ `Isaac.GetPlayer(0)` 认它。
    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, kEntityTypePlayer);

    // 目标块一：**精确**的 Entity_Familiar vptr + Type ⇒ `ToFamiliar()` 认它。
    g_FamiliarBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_FamiliarBytes, 0, g_EngineBase + kEntityFamiliarVtableOffset);
    WriteAt<std::uint32_t>(g_FamiliarBytes, kEntityTypeOffset, kEntityTypeFamiliar);

    // 目标块二：**不是** familiar（Type 对、vptr 是玩家的）⇒ `ToFamiliar()` 必须给 nil。
    g_OtherBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_OtherBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_OtherBytes, kEntityTypeOffset, kEntityTypeFamiliar);

    g_PlayerArrayBytes.assign(2 * sizeof(std::uint64_t), 0);
    WriteAt<std::uint64_t>(g_PlayerArrayBytes, 0, AddressOf(g_PlayerBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayBeginOffset, AddressOf(g_PlayerArrayBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayEndOffset,
                           AddressOf(g_PlayerArrayBytes) + sizeof(std::uint64_t));

    // ★ 关键一步：假玩家的 `Parent` 指向目标块 ⇒ `p.Parent` 交出"任意实体"的句柄。
    WriteAt<std::uint64_t>(g_PlayerBytes, kEntityParentOffset,
                           AddressOf(g_TargetIsFamiliar ? g_FamiliarBytes : g_OtherBytes));

    LuaRuntime::SetEngineModuleBase(g_EngineBase);
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = nullptr;
    return GameRoomObservation::GameNull;
}

int main(int argc, char** argv) {
    static_cast<void>(argv);
    if (argc != 2) return 90;
    if (std::strcmp(argv[1], "other") == 0) {
        g_TargetIsFamiliar = false;
    } else if (std::strcmp(argv[1], "run") != 0) {
        return 91;
    }

    PublishFakeGame();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function err(f) return tostring(select(2, pcall(f))) end"
        " local function argc(f) return tostring(select('#', pcall(f))) end"
        " local p = Isaac.GetPlayer(0)"
        " local raw = p.Parent"
        " print('B330 rawkind=' .. type(raw))"
        " local fam = raw:ToFamiliar()"
        " print('B330 famkind=' .. type(fam))"
        // ★ 新元表：ToFamiliar() 交回的句柄与基类句柄**不是同一张元表**（本批的核心接线）。
        " print('B330 newmt=' .. tostring(getmetatable(fam) ~= getmetatable(raw)))"
        // 两条方法必须挂在新元表上。
        " print('B330 f1=' .. type(fam.FollowParent))"
        " print('B330 f2=' .. type(fam.AddToFollowers))"
        // 调一次：宿主里没有引擎函数 ⇒ 走"入口取不到"降级 ⇒ 不报错、返回 0 个值。
        " print('B330 call1=' .. ok(function() return fam:FollowParent() end))"
        " print('B330 ret1=' .. argc(function() return fam:FollowParent() end))"
        " print('B330 call2=' .. ok(function() return fam:AddToFollowers() end))"
        " print('B330 ret2=' .. argc(function() return fam:AddToFollowers() end))"
        // ★ 基类那一侧没退化：字段回落 + 方法回落 + ToFamiliar 幂等。
        " print('B330 field=' .. tostring(pcall(function() return fam.Player end)))"
        " print('B330 inherit1=' .. type(fam.GetSprite))"
        " print('B330 inherit2=' .. type(fam.ToPlayer))"
        " print('B330 idem=' .. tostring(fam:ToFamiliar() == fam or type(fam:ToFamiliar()) == 'userdata'))"
        // ★★ 接收者闸门：点号 + 显式传**别的实体** ⇒ 不报错、什么都不做（那条野读被挡在这里）。
        " print('B330 foreign=' .. ok(function() return fam.FollowParent(raw) end))"
        " print('B330 foreignargv=' .. argc(function() return fam.FollowParent(raw) end))"
        // 参数闸门。
        " print('B330 extra=' .. ok(function() return fam:FollowParent(1) end))"
        " print('B330 extraerr=' .. err(function() return fam:FollowParent(1) end))"
        " print('B330 extra2=' .. ok(function() return fam:AddToFollowers(1) end))"
        " print('B330 extra2err=' .. err(function() return fam:AddToFollowers(1) end))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b330.lua");
    static_cast<void>(result);
    return 0;
}
'''


class FamiliarViewBatch330Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b330-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario="run"):
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主）

    def test_the_view_now_has_its_own_metatable(self):
        """★★ 本批的核心接线：`ToFamiliar()` 交回的句柄用的是**新的**元表，两条方法挂得上。

        数据行没接上 ⇒ `fam.FollowParent` 是 `nil`（模组报 "attempt to call a nil value"）；
        元表没换 ⇒ 方法没有地方挂，同样 `nil`。这两条断言把"视图"这件事钉住。
        """
        out = self.run_scenario()
        self.assertIn("B330 rawkind=userdata", out)
        self.assertIn("B330 famkind=userdata", out)
        self.assertIn("B330 newmt=true", out)
        self.assertIn("B330 f1=function", out)
        self.assertIn("B330 f2=function", out)

    def test_both_calls_are_silent_no_ops_without_an_engine(self):
        """★ 宿主里没有引擎函数 ⇒ 走"入口取不到"那条降级 ⇒ **不报错、返回 0 个值**。

        PC 那两条都返回 `void` ⇒ 这里也必须是 0 个返回值；报错会把整条模组回调摘掉。
        """
        out = self.run_scenario()
        self.assertIn("B330 call1=true", out)
        self.assertIn("B330 ret1=", out)
        self.assertIn("B330 call2=true", out)
        self.assertIn("B330 ret2=", out)
        self.assertNotIn("B330 call1=false", out)
        self.assertNotIn("B330 call2=false", out)

    def test_the_base_class_side_does_not_regress(self):
        """★ 换了元表**不许**把继承那一侧弄坏：字段回落 + 方法回落 + `ToFamiliar()` 幂等。

        ★ 这条是"改既有行为"那类改动必须带的回归：EID 从批次 9 起就在用
        `wisp:ToFamiliar().Player`。
        """
        out = self.run_scenario()
        self.assertIn("B330 field=true", out)
        self.assertIn("B330 inherit1=function", out)
        self.assertIn("B330 inherit2=function", out)
        self.assertIn("B330 idem=true", out)

    def test_a_foreign_receiver_is_refused_silently(self):
        """★★ 接收者闸门：点号 + 显式传**别的实体** ⇒ 不报错、什么都不做。

        这条挡的是**野读**：`follow_parent()` 一进去就 `ldr x8,[x0,#0xf50]` 然后解引用它
        ⇒ 拿别的实体当 `this` 会顺着垃圾指针跑出去（`FieldReceipt::EntityFamiliar` 的
        精确判据就是在这一关把它挡下来的）。★ 不报错是刻意的：那与"这次没生效"同义
        （批 250 定案：报错会摘掉整条回调）。
        """
        out = self.run_scenario()
        self.assertIn("B330 foreign=true", out)
        self.assertNotIn("B330 foreign=false", out)

    def test_argument_gate_is_exactly_one_and_names_the_api(self):
        """参数闸门：**恰好一个**（`self`）；多给一个报错，且消息里有**这一条**的名字。

        ★ 消息文案与引擎方法行族一致（`expects 0 argument(s)`）—— 与字段行那族的
        `accepts no arguments` 不同，别把两者混起来断言。"""
        out = self.run_scenario()
        self.assertIn("B330 extra=false", out)
        self.assertIn("EntityFamiliar:FollowParent expects 0 argument(s)", out)
        self.assertIn("B330 extra2=false", out)
        self.assertIn("EntityFamiliar:AddToFollowers expects 0 argument(s)", out)

    def test_a_non_familiar_still_yields_nil(self):
        """★ 老行为没变：不是 familiar 的对象上 `ToFamiliar()` 仍然给 `nil`（批次 9 起的口径）。"""
        out = self.run_scenario("other")
        self.assertIn("B330 famkind=nil", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """六处接线 + 第 7 处（精确接收者）+ 数据行 + 常量 —— 完成定义台账引用的就是这个方法。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        api = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        handles = HANDLES.read_text(encoding="utf-8")
        field_api = FIELD_HEADER.read_text(encoding="utf-8")

        for name, index, offset_name, entry_name in FAMILIAR_APIS:
            with self.subTest(api=f"EntityFamiliar:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, '
                    f'"EntityFamiliar", "{name}"', catalog, f"目录里没有 EntityFamiliar:{name}")
                self.assertIn(f"inline constexpr uintptr_t {offset_name} =", constants)
                self.assertIn(f"inline constexpr std::uint32_t {entry_name} =", constants)
                self.assertRegex(
                    api,
                    rf"\{{0x0E01{index:04X},\s*{offset_name},\s*{entry_name},\s*"
                    rf"FieldReceipt::EntityFamiliar,\s*EngineCallShape::Void0,\s*0,\s*0xFF\}}",
                    f"数据行缺失或形状/接收者不对：EntityFamiliar:{name}")
                #: ★ 反回归：这两条是**调用**，不许被塞进字段行表。
                self.assertNotRegex(api, rf"0x0E01{index:04X}[^\n]*FieldKind::")

        # --- 六处接线 ---------------------------------------------------------
        #: ① 元表常量。
        self.assertIn('kEntityFamiliarMetatable[] = "IsaacRuntime.EntityFamiliar"', handles)
        #: ② view 枚举 + ③ 元表映射。
        self.assertRegex(api, r"enum class EntityView[^;]*Npc,\s*Familiar\s*\}")
        self.assertRegex(api, r"EntityView::Familiar \? kEntityFamiliarMetatable : kEntityMetatable")
        #: ④ `__index`。
        self.assertRegex(api, r"int EntityFamiliarIndex\(lua_State\* state\)\s*\{\s*"
                              r"return IndexEntity\(state, EntityView::Familiar\);")
        #: ⑤ 句柄校验认它。
        self.assertRegex(api, r"luaL_testudata\(state, index, kEntityFamiliarMetatable\)")
        #: ⑥ `ToFamiliar()` 改压新元表。
        self.assertRegex(api, r"PushEntityHandle\(state, entity, kEntityFamiliarMetatable\)")
        #: 注册处那一段。
        self.assertRegex(api, r"luaL_newmetatable\(state, kEntityFamiliarMetatable\)")
        self.assertRegex(api, r"AttachEntityFamiliarMethods\(state\)")

        # --- 第 7 处：精确接收者 ------------------------------------------------
        self.assertRegex(field_api, r"EntityFamiliar\s*=\s*10,")
        self.assertRegex(api, r"case FieldReceipt::EntityFamiliar:")
        self.assertRegex(api, r"return ValidatedEntityFamiliar\(handle\)")
        #: ★★ 判据只有一份：`ToFamiliar()` 也走同一个函数（原来那里是就地写死的四行）。
        self.assertRegex(api, r"const std::uintptr_t entity = ValidatedEntityFamiliar\(handle\);")

        #: 表面表里要有这两条（`test_engine_row_api_surface` 按 Lua 名字钉形状）。
        surface = (ROOT / "runtime" / "tests" / "contract" /
                   "test_engine_row_api_surface.py").read_text(encoding="utf-8")
        for name, _index, _o, _e in FAMILIAR_APIS:
            self.assertIn(f'"EntityFamiliar:{name}": "Void0"', surface)

    def test_the_evidence_and_the_name_mapping_check_are_recorded(self):
        """★ 常量段必须写明：PC 两个绑定 VA、两个 Switch 符号、**为什么判法②**、
        以及**"两个名字有没有接反"的核对过程**（本批最容易接错的地方）。
        """
        folded = CONSTANTS.read_text(encoding="utf-8").lower()
        for needle in ("0x60d000", "0x447de0", "0xaec14", "0xac958",
                       "0xd10243ff", "0xd10143ff",
                       "entity_familiar::follow_parent", "add_to_followers",
                       "0x295", "0xeb", "野读"):
            self.assertIn(needle, folded, f"证据 {needle} 没有写进常量段")
        constants = CONSTANTS.read_text(encoding="utf-8")
        #: 契约页与行号。
        self.assertIn("EntityFamiliar.md", constants)
        self.assertIn(":65", constants)
        self.assertIn(":47", constants)


if __name__ == "__main__":
    unittest.main()
