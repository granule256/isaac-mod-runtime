"""门禁：`Entity:IsVulnerableEnemy()`（批次 286，2026-10-02 —— 一次 PC 侧取证专项）。

## 这一批是什么

| API | 引擎入口 | 形状 | 语料调用点 |
| --- | --- | --- | --- |
| `Entity:IsVulnerableEnemy()` | `Entity::IsVulnerableEnemy(Entity*) const` @ `0x5C62C` | `Bool0`（0 参 → 布尔） | **22 处**（4 个模组）—— 全项目单条最多的未做项 |

它是"引擎签名比 PC 契约**多一个参数**"的那一类：PC 契约 `tools/pc_contract_docs/Entity.md:496`
逐字是 `#### boolean IsVulnerableEnemy ( )`（**0 参**），而引擎那条 mangled 名
`_ZNK15IsaacRepentance6Entity17IsVulnerableEnemyEPS0_` **多一个 `Entity*`**（"来源实体"）。
按纪律这种**不许猜** —— 本批把"PC 那个无参重载到底往那格传了什么"查清了：**传空指针**。

## ★ 为什么能照 PC 做（完整证据链在 `runtime_constants.hpp` 的批次 286 段）

* **PC 侧**：名字表项 `0x805450` 成对的指针是 `0x7FAE70`，而 `0x7FAE70` 全镜像**只出现两次**
  （表项一次、注册现场 `0x80E9D6` 一次）⇒ 它是**专为这一条方法手写的** Lua 包装，不是通用模板。
  反汇编显示它 `lua_pushvalue(L, 2)` → `lua_type` → **是 nil 就 `eax = 0`** → `call 0x684630`
  （= `IsVulnerableEnemy(this, eax)`）。文档口径 0 参 ⇒ 第 2 格不存在 ⇒ 压的是 nil ⇒ **传 0**。
* **引擎侧**：`0x5C67C cbz x1, 0x5C6B8` ⇒ 来源为空时**纯读 + 立即返回**，不解引用、无副作用；
  而 `0x5C678` 算出的 `w0` 与 PC 那条路径的结果是**同一个式子**
  （返回 `(Type&~0x40 == 0x322) || ((flags & 0x10) == 0)`）⇒ **`x1 = 0` 时两版返回值等价**。
* **实现上 0 字节代码**：用既有形状 `Bool0`（`bool(this)`、0 个参数）即可 —— 共享处理器把参数数组
  **整块零初始化**、只搬"实际给出"的那几个，而跳板无条件读满 8 个 `x` ⇒ 省略的 `x1` **保持 0**。
  ★ ABI 体检会因此报 `under`（我们声明 1 个含 `this` < 引擎 1 + 1），**这是预期**，
  理由登记在 `tools/engine_abi_triage.json`（"引擎那个参数可以传 0，我们的跳板会把寄存器清零"）。

## 宿主验到了什么、没验到什么

* **验到（运行期事实，不只是读源码）**：拿一个真实体句柄（伪造 `Game` → `players` 数组 → 玩家对象，
  配方抄批次 281/284/285）后，`IsVulnerableEnemy` 的**参数个数闸门**、**静默降级口径**与
  **返回值种类**都真跑了一遍。这些是"数据行挂对页、形状对、共享处理器认得它"的硬判据 ——
  任何一处断了，下面就会变成 `nil` 或直接抛错（批次 207 就是这么栽的）。
* **没验**：真的调进引擎、拿到真实布尔。宿主没有引擎 —— 伪造的模块块里那段偏移处是一片零，
  入口字核对必然失效，于是**按设计静默降级**（`Bool` 压 `false`，**不报错**）。
  这一层只能真机看（作业单 **V37**）。
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
    ("Entity", "IsVulnerableEnemy", 0x00C2, "kEntityIsVulnerableEnemy", "Bool0", 0),
)


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 281/284/285 的用例，只留本批要的那几块）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_Game 变量（槽里是**变量地址**，不是对象）
//   g_Game 变量            = Game*
//   Game + kGamePlayerArrayBegin/End = 只有一个元素的玩家指针数组
//   玩家对象首字            = base + kEntityPlayerVtableOffset（`GetPlayer` 要它）
//
// ★ 模块块按 `kGameOwnerGlobalSlotOffset + 8`（≈ 10.7 MiB，正是模块映像的量级）分配，
//   **已经覆盖**本批要读的那个方法偏移（`kEntityIsVulnerableEnemyOffset` 0x5C62C）
//   ⇒ 那次"模块基址 + 偏移"的读落在我们自己的零块里：宿主没有 `svcQueryMemory`，
//   越界读不返回 false 而是**真去读**，所以块必须自己够大（下面有 static_assert 钉住）。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::uintptr_t g_EngineBase = 0;

static_assert(kEntityIsVulnerableEnemyOffset < kGameOwnerGlobalSlotOffset,
              "module block must cover the Entity::IsVulnerableEnemy entry read");

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
    if (std::strcmp(argv[1], "entity") != 0) return 91;
    PublishFakeGame();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    // `ok(f)` = "这次调用**没抛错**"（`pcall` 的第一个返回值）。本批的降级是**静默**的
    // （拿不到接收者 / 入口指纹对不上 ⇒ 压 `false`、**不报错**），所以"没抛错"本身就是判据。
    // ★ `stdout + stderr` 一起回（批 285 被"只回 stdout"骗过一次）：脚本里报了 Lua 错时
    //   `print` 之前就中断、stdout 是空的，只回 stdout 等于"什么都没说"。
    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local p = Isaac.GetPlayer(0)"
        " print('B286 pkind=' .. type(p))"
        " print('B286 fn=' .. type(p.IsVulnerableEnemy))"
        " print('B286 ret=' .. ok(function() return p:IsVulnerableEnemy() end))"
        " print('B286 retkind=' .. type(p:IsVulnerableEnemy()))"
        " print('B286 val=' .. tostring(p:IsVulnerableEnemy()))"
        " print('B286 dotself=' .. ok(function() return p.IsVulnerableEnemy(p) end))"
        " print('B286 arg1=' .. ok(function() return p:IsVulnerableEnemy(true) end))"
        " print('B286 arg2=' .. ok(function() return p:IsVulnerableEnemy(nil) end))"
        //  ★ 接收者闸门：`CheckEntityHandle` 对**非实体**是**硬报错**（不是静默降级）——
        //    这是**全族共用**的判据（同一段代码，`IsFlying` 等老方法一样报），本批没有改动它。
        //    写成 `f({})` 只压**一个**值（那张表）当接收者；写成 `p.IsVulnerableEnemy({})` 会把
        //    `p` 也压进去 ⇒ 那一刻报的是**参数个数**错，验不到接收者这一层。
        " local f = p.IsVulnerableEnemy"
        " print('B286 badrecv=' .. ok(function() return f({}) end))"
        " print('B286 badrecverr=' .. tostring(select(2, pcall(f, {}))))"
        " local g = p.IsFlying"
        " print('B286 siblingbadrecv=' .. ok(function() return g({}) end))"
        " print('B286 sibling=' .. type(p.IsFlying))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b286.lua");
    static_cast<void>(result);
    return 0;
}
'''


class EntityIsVulnerableEnemyBatch286Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b286-")
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
        #: 连 `stderr` 一起交出去（见 harness 里那段说明）。
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主）

    def test_zero_argument_gate_and_silent_degradation(self):
        """★ `IsVulnerableEnemy` 是 **0 参**：`()` 放行、给参数就报错；无引擎时**静默返回 `false`**。

        为什么这是硬判据：数据行没挂到 `Entity` 页 ⇒ `p.IsVulnerableEnemy` 是 `nil`；
        形状不是 `Bool0` ⇒ 0 参那条会因为"参数个数不符"直接报错；共享处理器不认它 ⇒
        调用不记账、返回值也不对。三条里任何一条断了，下面都会红。
        """
        out = self.run_scenario("entity")
        #: 句柄与方法的可达性（`Entity` 页通过视图回落对实体句柄可见）。
        self.assertIn("B286 pkind=userdata", out)
        self.assertIn("B286 fn=function", out)
        #: 0 参放行（点号写法显式传 self 也必须能走 —— 与冒号写法等价）。
        self.assertIn("B286 ret=true", out)
        self.assertIn("B286 dotself=true", out)
        #: 返回**布尔**、不是 nil：模组常拿它做条件判断，nil 会抛 "attempt to index a nil value"。
        self.assertIn("B286 retkind=boolean", out)
        #: 宿主没有引擎 ⇒ 入口字核对失败 ⇒ 按设计**静默降级**成 `false`（**不报错**）。
        self.assertIn("B286 val=false", out)
        #: 参数个数闸门：恰好 0（多了挡，`nil` 也算一个）。
        self.assertIn("B286 arg1=false", out)
        self.assertIn("B286 arg2=false", out)
        #: 接收者不是实体句柄 ⇒ **硬报错**（这是 `CheckEntityHandle` 的全族共用判据，本批没动它）。
        self.assertIn("B286 badrecv=false", out)
        self.assertIn("expected an Entity", out)
        #: ★ 对照：同族老方法（`IsFlying`）拿同一个坏接收者**也报同样的错** ⇒
        #:   接收者这一层不是本批引入的、也不是本批改坏的。
        self.assertIn("B286 siblingbadrecv=false", out)
        #: 反回归：`Entity` 页原有的方法不能被本批的表改动挤掉。
        self.assertIn("B286 sibling=function", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 形状与参数个数 / 行数断言 —— 完成定义台账引用的就是这个方法。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

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
                self.assertIn(f"inline constexpr uintptr_t {prefix}Offset = 0x5C62C", constants)
                self.assertIn(f"inline constexpr std::uint32_t {prefix}EntryWord = 0xB9403808U",
                              constants)

        #: ★ 行数断言必须跟着改（漏改会让"新行根本没进表"这件事**看不见**）。
        #: ★ 2026-10-07（门禁修复：批次 347 之后的存量红）：期望值从 8 改成 9。
        #:   本批（286）落地 `Entity:IsVulnerableEnemy` 时它是第 **8** 行；随后批次 303
        #:   （commit `6fee3203`，2026-10-03，`docs/改动日志-20261003.md` 第 284 行起，
        #:   `docs/会话交接-20261003-三-语料API恢复-批次301到311.md` 第 22 行）新增了
        #:   `Entity:CanShutDoors()`（按 vtable 槽号调用）作为第 **9** 行 —— 这是**有意**的产品改动，
        #:   产品侧的 `static_assert` 已同步改为 `== 9`（`isaac_api.cpp:11149`），门禁当时没跟上。
        #:   这里仍钉**精确**条数（不换成任意数字），"新增行必须同步改两处"的保护价值不变。
        self.assertRegex(isaac, r"static_assert\(RowCount\(kEntityEngineRows\) == 9,")
        #: ★ 数据行 id 不许再挂手写处理器 —— 顺带确认没有为它写 `&…` 绑定行。
        self.assertNotRegex(catalog, r"\{0x0E0100C2,\s*&\w+\}")
        #: `Entity` owner 早就登记在「文件 → 允许的 owner」表里（新视图才需要加）。
        self.assertIn('"Entity"', CATALOG_TEST.read_text(encoding="utf-8"))

    def test_shape_and_owner_are_as_intended(self):
        """★ 反回归：形状是既有的 `Bool0`（0 参 → 布尔），**没有为新参数造形状**。

        `Bool0` 的 `argumentCount` 必须是 0 —— 因为"省略的 `x1` 保持 0 = PC 的缺省值"正是
        本批敢照 PC 做的机制；若哪天有人把它改成 `Bool1`（声明 1 个可省参数），那个 `x1`
        就会由 Lua 参数决定，语义立刻偏离（ABI 也会从"预期 under"变成另一种不符）。
        """
        isaac = ISAAC_API.read_text(encoding="utf-8")
        shapes = SHAPES.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        handles = HANDLES.read_text(encoding="utf-8")

        self.assertRegex(shapes, r"\bBool0\s*=\s*6")
        #: `Bool0` 那一行的 `argumentCount`（行首第一个数字）必须是 0。
        self.assertRegex(isaac, r"// 6 Bool0：[^\n]*\n\s*\{0,")
        #: 常量段必须写明本批的关键结论（取证链条里那几处）。
        self.assertIn("@ `0x5C62C`", constants)
        self.assertIn("IsObstacle", constants)
        self.assertIn("0x7FAE70", constants)
        self.assertIn("PC 传下去的就是空指针", constants)
        #: 入口字与 `Entity::IsEnemy` 相同的说明（免得后人以为挂错了）。
        self.assertIn("逐字节相同", constants)
        #: 这批没有新视图 ⇒ 不该动句柄元表清单（反回归：别顺手加了没用的元表）。
        self.assertNotIn("kEntityVulnerable", handles)


if __name__ == "__main__":
    unittest.main()
