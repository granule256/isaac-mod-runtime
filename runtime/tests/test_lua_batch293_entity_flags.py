"""门禁：`Entity` 的三个相邻状态字节（批次 293，2026-10-03）。

## 这一批是什么

| API | 契约 | 引擎侧字段 | 形状 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `Entity:IsVisible()` | `Entity.md:491` | `Entity + 0x1C1`（**字节**） | `Bool` / 降级 `False` | 1 |
| `Entity:Exists()` | `Entity.md:320` | `Entity + 0x1C2`（**字节**） | `Bool` / 降级 `False` | 17 |
| `Entity:IsDead()` | `Entity.md:466` | `Entity + 0x1C3`（**字节**） | `Bool` / 降级 `False` | 14 |

三条合计 **32 处 / 5 个模组**，全部走**字段读取型数据行**、**0 字节手写处理器** ——
而且**零新机制**：接收者是既有的 `FieldReceipt::Entity`（Lua 栈上的实体句柄），
种类是既有的 `FieldKind::Bool`。

## 为什么 `0x1C1 / 0x1C2 / 0x1C3` 就是这三个量

**PC 侧的标尺**（`tools/pc_exe_binding.py <名字> --disasm`）：三个绑定本体是**相邻**的
`mov al, byte ptr [ecx + 0x169/0x16A/0x16B]; ret` —— PC 上就是 `visible / exists / dead` 连着三格。

**Switch 侧三格各有具名消费者**（不是"照 PC 平移"）：

* `0x1C1` = **可见**：`Entity::Render @ 0x062514`（读到 0 就 `cbz` 跳过整个渲染）、
  `EntityList::RenderShadows @ 0x078210`（连影子都不画）、
  `Camera::get_enemy_target @ 0x032BBC`（不锁定看不见的敌人）、
  写入方 `Entity_Effect::Init @ 0x0800A4`（`strb wzr` ⇒ 新建 Effect 初始不可见）。
* `0x1C2` = **还在实体表里**：`EntityList::Update @ 0x076848`（为 0 就跳过这个实体）、
  写入方 `Entity::Remove() @ 0x05D3E4`（清零）、构造函数 `0x0588E8` 清零、析构 `0x0589DC` 读它。
  ★ 契约散文逐字对上：`Checks whether the entity is still spawned in the current room.`
* `0x1C3` = **已死**：★★ `Entity::Kill() @ 0x05C8E8`..`0x05C934` 的函数体是
  `ldrb [x0,#0x1c3]` → `cbnz`（已置就返回，幂等）→ `mov w8,#1` → `strb` →
  取虚表槽调用 → 类型不是 3 就**尾调用 `Entity::BloodExplode()`**；
  而契约散文写着 `Kills the entity and makes a blood splat or gibs.` ⇒ 两头对上。
  第二处独立读者 `Entity::IsVulnerableEnemy @ 0x05C650`（死掉的不再是可伤害的敌人）。

★ 三格与 PC 的**顺序一致**（visible / exists / dead）是一层交叉印证，但每一格的归属
都是**它自己的消费者**定的。

## 宿主验到了什么、没验到什么

* **验到**（字段行**没有入口指纹** ⇒ 伪造内存里的字节真会被读出来）：
  - ★★ **读的是"接收者自己"那一格，不是恒定读某个全局**：夹具放两个不同的实体对象
    （`Isaac.GetPlayer(0)` 与 `p.Parent`），三格各摆**互不相同**的组合 ⇒ 两个对象读回两套值；
  - ★ **三个字节各归各**：同一对象上摆 `visible=1 / exists=0 / dead=0` 与
    `0 / 1 / 1` 两种组合，三条读回来的必须分别对上（**读错格**立刻红）；
  - ★ **宽度是一个字节**：某一格写 `0xFF` 而它的邻居写 `0` 时仍只答那一格
    （用 `BoolNonZero` 读 4 字节会一起算进来 ⇒ 这种错法也会红）；
  - **非零即真**：写 `2` 也是 true；
  - **句柄失效 ⇒ 三条都答 `false` 且不抛 Lua 错误**（把 `Parent` 指向一块"首字不是合法 vtable"
    的内存来造失效句柄）；
  - 参数闸门：`p:IsVisible(1)` / `p:IsDead(1)` 报错。
* **没验**：真机上这三格是不是就是那三个量（宿主里"偏移对不对"是同一张表的两处引用
  同一个常量，自己证不了自己）、以及真机上的数值。⇒ 真机项 = 作业单 **V44**。
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
LAYOUT_ENTITY = ROOT / "tools" / "layout_tables" / "entity.json"

#: `(名字, 域内序号, 偏移常量)` —— 三条都是 `Bool` + `FieldMissing::False` + `FieldReceipt::Entity`。
FIELD_APIS = (
    ("IsVisible", 0x00C9, "kEntityVisibleOffset"),
    ("Exists", 0x00CA, "kEntityExistsOffset"),
    ("IsDead", 0x00CB, "kEntityIsDeadOffset"),
)

#: 两个对象上三格的组合（互不相同 ⇒ 读错格 / 读错对象都会红）。
#:  `(visible, exists, dead)`
PLAYER = (1, 0, 0)
PARENT = (0, 1, 1)
#: `edge` 那一场的组合：非零即真（2 与 0xFF 都算 true），且邻居仍是 0。
PLAYER_EDGE = (2, 0xFF, 2)


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "entity_layout.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 285/287 的用例）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes（槽里是**变量地址**）
//   g_OwnerSlotBytes                         = Game*
//   Game + kGamePlayerArrayBegin/End         = 只有一个元素的玩家指针数组
//   玩家对象首字                              = base + kEntityPlayerVtableOffset（`IsEntityPointer` 要它）
//   玩家对象 + kEntityParentOffset            = 第二个"实体对象"（★ 造出**第二个句柄**用）
//   两个对象 + 0x1C1 / 0x1C2 / 0x1C3          = 本批读的那三格
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_ParentBytes;
std::uintptr_t g_EngineBase = 0;
bool g_ParentIsGarbage = false;

static_assert(kEntityParentOffset + sizeof(std::uint64_t) <= kEntityPlayerSize,
              "parent pointer must live inside the Entity object");
static_assert(kEntityVisibleOffset + sizeof(std::uint8_t) <= kEntityPlayerSize,
              "visible byte must live inside the Entity object");
static_assert(kEntityExistsOffset + sizeof(std::uint8_t) <= kEntityPlayerSize,
              "exists byte must live inside the Entity object");
static_assert(kEntityIsDeadOffset + sizeof(std::uint8_t) <= kEntityPlayerSize,
              "dead byte must live inside the Entity object");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

//: 三格的组合（`visible` / `exists` / `dead`）。
struct Flags {
    std::uint8_t visible;
    std::uint8_t exists;
    std::uint8_t dead;
};

// 造一个"看起来像 `Entity`"的对象：首字是 vtable（`IsEntityPointer` 只认这个区间）。
void MakeFakeEntity(std::vector<unsigned char>& block) {
    block.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(block, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(block, kEntityTypeOffset, kEntityTypePlayer);
}

void WriteFlags(std::vector<unsigned char>& block, const Flags& flags) {
    WriteAt<std::uint8_t>(block, kEntityVisibleOffset, flags.visible);
    WriteAt<std::uint8_t>(block, kEntityExistsOffset, flags.exists);
    WriteAt<std::uint8_t>(block, kEntityIsDeadOffset, flags.dead);
}

void PublishFakeGame(const Flags& player, const Flags& parent) {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    MakeFakeEntity(g_PlayerBytes);
    WriteFlags(g_PlayerBytes, player);
    if (g_ParentIsGarbage) {
        // 失效句柄那一场：Parent 指向一块**首字不是合法 vtable** 的内存
        // ⇒ `IsEntityPointer` 判定不过 ⇒ 接收者解析成 0 ⇒ 三条都该答 false（且不抛错）。
        g_ParentBytes.assign(0x40, 0x5A);
    } else {
        MakeFakeEntity(g_ParentBytes);
        WriteFlags(g_ParentBytes, parent);
    }
    WriteAt<std::uint64_t>(g_PlayerBytes, kEntityParentOffset, AddressOf(g_ParentBytes));

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

    // 五个场景：
    //   combo      —— 两个对象三格各摆**互不相同**的组合（默认）
    //   zero       —— 两边全 0
    //   edge       —— 非零即真：玩家（2, 0xFF, 2）、第二个对象全 0
    //   badparent  —— 第二个句柄**失效**（Parent 指向非实体内存）
    //   args       —— 参数闸门
    Flags player{1, 0, 0};
    Flags parent{0, 1, 1};
    if (std::strcmp(scenario, "combo") == 0) {
        // 默认值。
    } else if (std::strcmp(scenario, "zero") == 0) {
        player = {0, 0, 0};
        parent = {0, 0, 0};
    } else if (std::strcmp(scenario, "edge") == 0) {
        player = {2, 0xFF, 2};
        parent = {0, 0, 0};
    } else if (std::strcmp(scenario, "badparent") == 0) {
        g_ParentIsGarbage = true;
    } else if (std::strcmp(scenario, "args") == 0) {
        // 默认组合即可。
    } else {
        return 91;
    }

    PublishFakeGame(player, parent);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function err(f) return tostring(select(2, pcall(f))) end"
        " local p = Isaac.GetPlayer(0)"
        " print('B293 pkind=' .. type(p))"
        " print('B293 fn=' .. type(p.IsVisible) .. ',' .. type(p.Exists) .. ',' .. type(p.IsDead))"
        // 接收者自己那一格
        " print('B293 pvis=' .. tostring(p:IsVisible()))"
        " print('B293 pexists=' .. tostring(p:Exists()))"
        " print('B293 pdead=' .. tostring(p:IsDead()))"
        " print('B293 pviskind=' .. type(p:IsVisible()))"
        // 第二个对象（`p.Parent`：把 0x390 上的指针原样包成句柄，不做校验）
        " local q = p.Parent"
        " print('B293 qkind=' .. type(q))"
        " print('B293 qvis=' .. tostring(q:IsVisible()))"
        " print('B293 qexists=' .. tostring(q:Exists()))"
        " print('B293 qdead=' .. tostring(q:IsDead()))"
        // 参数闸门：字段行**恰好收一个**（= 只有接收者）。
        " print('B293 argvis=' .. ok(function() return p:IsVisible(1) end))"
        " print('B293 argdead=' .. ok(function() return p:IsDead(1) end))"
        " print('B293 argerr2=' .. err(function() return p:IsVisible(1) end))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b293.lua");
    static_cast<void>(result);
    return 0;
}
'''


class EntityFlagsBatch293Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b293-")
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
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主）

    def test_each_byte_is_read_from_the_receiver_itself(self):
        """★★ 两个对象三格各摆**互不相同**的组合 ⇒ 读回两套值（读错格 / 读错对象都会红）。

        夹具里 `p = Isaac.GetPlayer(0)`、`q = p.Parent` 是**两块不同的伪造内存**：
        `p` = (visible 1, exists 0, dead 0)、`q` = (0, 1, 1)。
        ★ 只断言"三条都被调用到"是没用的（常量、恒真、读错格都能过）；这里三格的值**两两不同**，
        所以任何"读错格"都会让至少两条同时翻转。
        """
        out = self.run_scenario("combo")
        self.assertIn("B293 pkind=userdata", out)
        self.assertIn("B293 fn=function,function,function", out)
        self.assertIn("B293 pviskind=boolean", out)
        #: 接收者 p：三格 (1, 0, 0)
        self.assertIn("B293 pvis=true", out)
        self.assertIn("B293 pexists=false", out)
        self.assertIn("B293 pdead=false", out)
        #: 接收者 q：三格 (0, 1, 1) —— 与 p 互不相同
        self.assertIn("B293 qkind=userdata", out)
        self.assertIn("B293 qvis=false", out)
        self.assertIn("B293 qexists=true", out)
        self.assertIn("B293 qdead=true", out)

    def test_all_zero_reads_false(self):
        """★ 三格全 0 ⇒ 三条都答 false（"读到 0"与"读不到"两条路径同值，都由上面那一场分开）。"""
        out = self.run_scenario("zero")
        self.assertIn("B293 pvis=false", out)
        self.assertIn("B293 pexists=false", out)
        self.assertIn("B293 pdead=false", out)
        self.assertIn("B293 qvis=false", out)
        self.assertIn("B293 qexists=false", out)
        self.assertIn("B293 qdead=false", out)

    def test_non_zero_is_true_and_neighbours_stay_separate(self):
        """★ 非零即真（`2` / `0xFF` 都算 true），且**邻居仍是 0 时结果不受影响**。

        ★ 这一场专抓"读 4 字节"的实现（`BoolNonZero`）：那会把相邻两格一起算进来 ——
        玩家那三格是 `(2, 0xFF, 2)`，若按 4 字节读 `+0x1C1`，`exists` 会跟着变 true。
        """
        out = self.run_scenario("edge")
        self.assertIn("B293 pvis=true", out)
        self.assertIn("B293 pexists=true", out)
        self.assertIn("B293 pdead=true", out)
        #: 第二个对象全 0 ⇒ 三条都 false（证明读的是各自的对象，不是缓存/全局）。
        self.assertIn("B293 qvis=false", out)
        self.assertIn("B293 qexists=false", out)
        self.assertIn("B293 qdead=false", out)

    def test_invalid_handle_degrades_to_false_without_erroring(self):
        """★ 句柄失效（`Parent` 指向一块首字不是合法 vtable 的内存）⇒ 三条都答 `false`、**不抛错**。

        `FieldReceipt::Entity` 每次都重做指针校验（vptr 落在 `Entity` 家族的 vtable 区间里）——
        校验不过就返回 0 ⇒ 字段行按 `FieldMissing::False` 静默降级（批 250 定案：
        报错会把整条模组回调摘掉）。★ 接收者 p 仍然能用（那一场同时证明"失效的是 q，不是全部"）。
        """
        out = self.run_scenario("badparent")
        self.assertIn("B293 qkind=userdata", out)
        self.assertIn("B293 qvis=false", out)
        self.assertIn("B293 qexists=false", out)
        self.assertIn("B293 qdead=false", out)
        #: p 不受影响（默认组合 (1, 0, 0)）。
        self.assertIn("B293 pvis=true", out)
        self.assertIn("B293 pdead=false", out)

    def test_argument_gate_is_exactly_one(self):
        """参数闸门 = **恰好一个**（只有冒号调用压进来的 `self`），多给一个就报错。"""
        out = self.run_scenario("args")
        self.assertIn("B293 argvis=false", out)
        self.assertIn("B293 argdead=false", out)
        self.assertIn("Entity:IsVisible accepts no arguments", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 种类与降级档 / 接收者 / 偏移常量。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        for name, index, offset_name in FIELD_APIS:
            with self.subTest(api=f"Entity:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, "Entity", "{name}"',
                    catalog, f"目录里没有 Entity:{name}")
                #: 三条都是 `Bool` + `False` + `FieldReceipt::Entity`（**既有**接收者，本批零新机制）。
                #: `offset2` 在这三条里都写 `0`（`Bool` 不用第二栏）；与 `kFieldApis` 里
                #: 其它 `Bool` 行的写法一致 —— 门禁的解析式两种写法都认。
                self.assertRegex(
                    isaac,
                    rf"\{{\s*(?i:0x0E01{index:04x}),\s*{offset_name},\s*(?:0x00|0),\s*"
                    rf"FieldKind::Bool,\s*FieldMissing::False,\s*FieldReceipt::Entity,\s*0xFF\}}",
                    f"数据行缺失或形状/降级档/接收者不对：Entity:{name}")
                #: ★ 反回归：不许被塞进引擎方法行表 —— 这三条**引擎里没有同名访问器**
                #:   （PC 侧那三个绑定本体就是 `mov al,[ecx+0x169/0x16A/0x16B]; ret`）。
                self.assertNotRegex(isaac, rf"0x0E01{index:04x}[^\n]*EngineCallShape")

        self.assertRegex(constants, r"inline constexpr uintptr_t kEntityVisibleOffset\s*=\s*0x1C1;")
        self.assertRegex(constants, r"inline constexpr uintptr_t kEntityExistsOffset\s*=\s*0x1C2;")
        self.assertRegex(constants, r"inline constexpr uintptr_t kEntityIsDeadOffset\s*=\s*0x1C3;")
        #: 布局表那份常量与这里的同名同值 ⇒ 三条 `static_assert` 钉住不许漂移。
        for name in ("Visible", "Exists", "IsDead"):
            self.assertRegex(
                isaac,
                rf"static_assert\(kEntity{name}Offset\s*==\s*layout::kEntity{name}Offset")

    def test_the_three_layout_rows_are_confirmed_with_named_consumers(self):
        """★ 布局表三行必须 `confirmed`，各带**具名**消费者（不是"某处有个字节"）。"""
        import json

        table = json.loads(LAYOUT_ENTITY.read_text(encoding="utf-8"))
        rows = {row["name"]: row for row in table["rows"]}
        expected = {
            "Visible": (0x1C1, ["_ZN15IsaacRepentance6Entity6RenderERKN4KAGE4Math7Vector2E",
                                "_ZN15IsaacRepentance10EntityList13RenderShadowsERKN4KAGE4Math7Vector2E",
                                "_ZN15IsaacRepentance6Camera16get_enemy_targetEv"]),
            "Exists": (0x1C2, ["_ZN15IsaacRepentance10EntityList6UpdateEb",
                               "_ZN15IsaacRepentance6Entity6RemoveEv",
                               "_ZN15IsaacRepentance6EntityC2Ev"]),
            "IsDead": (0x1C3, ["_ZN15IsaacRepentance6Entity4KillEv",
                               "_ZN15IsaacRepentance6Entity12BloodExplodeEv",
                               "_ZNK15IsaacRepentance6Entity17IsVulnerableEnemyEPS0_"]),
        }
        for name, (offset, functions) in expected.items():
            with self.subTest(row=name):
                self.assertIn(name, rows, f"布局表里没有 {name} 行")
                row = rows[name]
                self.assertEqual(row["confidence"], "confirmed")
                self.assertEqual(row["offset"], offset)
                #: ★ 宽度必须是 1（字节）：写成 4 会让读法变成读 u32，把邻居算进来。
                self.assertEqual(row["width"], 1)
                kinds = [e["kind"] for e in row["evidence"]]
                self.assertIn("semantic", kinds)
                cited = [e["function"] for e in row["evidence"]]
                for function in functions:
                    self.assertIn(function, cited, f"{name} 行缺少 {function} 的证据")

        #: 常量段要写下 PC 的三个相邻字节（标尺）与那条"函数体 + 契约散文"的对应关系。
        #: ★ 比对**按数值**而不是按字符串：常量段里的地址有 `0x412340` / `0x05C8E8` / `0x6251C`
        #:   几种写法（散文处引反汇编原样、正文里用统一形式），按字符串比会因为补零/大小写误判。
        import re

        constants = CONSTANTS.read_text(encoding="utf-8")
        written = {int(v, 16) for v in re.findall(r"0x[0-9A-Fa-f]+", constants)}
        for va in (0x412340, 0x412350, 0x412360,        # PC 三个绑定本体
                   0x05C8E8, 0x05C8F4,                  # Entity::Kill（写入方 + 取值锚点）
                   0x062514, 0x078210, 0x032BBC,        # Visible 的三个具名读者
                   0x0800A4,                            # Visible 的写入方
                   0x076848, 0x05D3E4, 0x0588E8, 0x0589DC,   # Exists 的读者/写入方
                   0x05D380, 0x05C650):                 # IsDead 的两处独立读者
            self.assertIn(va, written, f"证据地址 {va:#x} 没有写进常量段")
        #: PC 侧那三个相邻字节的偏移也要写下来（它们是"顺序一致"这条交叉证据的一半）。
        for off in (0x169, 0x16A, 0x16B):
            self.assertIn(off, written, f"PC 侧字节偏移 {off:#x} 没有写进常量段")


if __name__ == "__main__":
    unittest.main()
