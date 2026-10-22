"""门禁：`Entity:Die()`（批次 315，2026-10-03）。

## 这一批是什么

| API | 契约 | 引擎侧 | 形状 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `Entity:Die()` | `Entity.md:314` | 往 `Entity + 0x1C3`（**已死字节**）写**常量 1** | `BoolWriteConst` / 降级 `False` | **27（4 个模组）** |

★★★ **剩余清单里最大的一条**，而且**0 字节手写处理器、零新机制**：
接收者是既有的 `FieldReceipt::Entity`，种类是既有的 `FieldKind::BoolWriteConst`
（批次 305 立的：往 1 字节字段写**行内常量**、**不收实参**、返回 0 个值）。

## ★★★ 本批推翻了交接 §4 的一条"别碰"

交接写：「`Entity:Die` / `AddVelocity` 已查明 **dynsym 里 0 个实现** ⇒ **别在这两条上花时间**」。

**"0 实现"只说明 Switch 侧没有同名函数（内联进去了），字段本身一定在。** 本批核 PC 侧两条绑定：

```
Entity:IsDead() @ 0x412350 = movb 0x16b(%ecx), %al ; ret      （读 PC +0x16B）
Entity:Die()    @ 0x436B60 = movb $0x1, 0x16b(%ecx) ; ret     （写**同一格**）
```

⇒ PC 上这两条 API 是"同一格的两侧"、各自只有两条指令 ⇒ `Die` 就是**纯字段写**。
★ 又一条交叉印证：PC 的 `IsVisible @ 0x412360` 读 `+0x169`，与 `+0x16B` **相隔 2**；
Switch 的 `+0x1C1`（可见）与 `+0x1C3`（已死）**同样相隔 2**（中间 `+0x1C2` = `Exists`）。

★ 而 Switch 那一格早在**批次 293** 就有决定性证据：`Entity::Kill() @ 0x05C8E8` 的函数体是
`ldrb [x0,#0x1c3]` → `cbnz`（**已置着就返回 ⇒ 幂等**）→ `mov w8,#1` → `strb`；
契约散文（`Entity.md:502`）写 `Kills the entity and makes a blood splat or gibs.` ⇒ 两头对上。

★ **口径**：我们**只写这一格**（PC 的 `Die` 逐字照做）。Switch 的 `Entity::Kill()` 额外立刻
调虚表槽、并可能 `ForeachParent`/`BloodExplode`，**我们不复刻那一步**（PC 也没做）；
血/爆炸由引擎看到这一格之后自行处理 ⇒ 与 PC 一致。

## 宿主验到了什么、没验到什么

* **验到** —— 判据分**两层**（写侧的判据必须落到"内存真的变了"）：
  - **① 引擎内存那一格真的被写**（C++ 侧跑完 Lua 后直接打印 `Entity` 块里的**原始字节**，
    不经过我们自己的读侧 API）⇒ `[0x1C3]` 从 0 变 1；
  - **② 与读侧互相印证**：同一次调用之后 `e:IsDead()` 必须变 `true`
    （读侧是批次 293 已交付的、读的是同一格）；
  - ★★ **相邻两格不许被动**（`IsVisible` / `Exists` 摆 1、Die 之后仍是 1）——
    这三格相邻、真机上写错一格极难发现，只有宿主能把它们分开；
  - ★ **幂等**（已经是 1 ⇒ 再 Die 仍是 1，与 `Entity::Kill()` 的守卫一致）；
  - **返回 0 个值**（`select('#', p:Die())` == 0）；参数闸门（多给一个实参报错）。
  - ★ **句柄失效时不写**：`Parent` 指向非实体内存 ⇒ 接收者解析成 0 ⇒ **什么都不写**、
    也**不抛错**（`RowReturnsNoValues` 那一档的既有口径）。
* **没验**：真机上这两个偏移是不是"已死那一格"（宿主里"偏移对不对"是同一张表的两处引用
  同一个常量）⇒ 真机项 = 作业单 **V65**（判据 = `Die()` 之后 `IsDead()` 变 true、
  且实体在下一帧真的消失）。
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

#: `(owner, 名字, 域内序号, 偏移常量, 行内常量, FieldKind, FieldMissing)`
FIELD_APIS = (
    ("Entity", "Die", 0x00DA, "kEntityIsDeadOffset", 1, "BoolWriteConst", "False"),
)


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "entity_layout.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 293 的用例）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes（槽里是**变量地址**）
//   g_OwnerSlotBytes                         = Game*
//   Game + kGamePlayerArrayBegin/End         = 只有一个元素的玩家指针数组
//   玩家对象首字                              = base + kEntityPlayerVtableOffset
//   玩家对象 + kEntityParentOffset            = 第二个"实体对象"（★ 造出**第二个句柄**用）
//   两个对象 + 0x1C1 / 0x1C2 / 0x1C3          = 三格状态字节（本批只该写最后一格）
// ★ 本批是**写侧**：跑完 Lua 之后由 C++ 直接打印原始字节（不经过我们自己的读侧 API）。
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
static_assert(kEntityIsDeadOffset + sizeof(std::uint8_t) <= kEntityPlayerSize,
              "dead byte must live inside the Entity object");
//: ★★ 这三格**相邻**（`+0x1C1`/`+0x1C2`/`+0x1C3`）：真机上写错一格极难发现 ⇒
//:   夹具必须把三格摆成不同值，让"写错格"当场现形。
static_assert(kEntityVisibleOffset + 1 == kEntityExistsOffset &&
              kEntityExistsOffset + 1 == kEntityIsDeadOffset,
              "the three state bytes must be adjacent");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

struct Flags {
    std::uint8_t visible;
    std::uint8_t exists;
    std::uint8_t dead;
};

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
        // ⇒ 接收者解析成 0 ⇒ **什么都不写**、也不抛错。
        // ★ 块要**够大**（`kEntityPlayerSize`）—— 否则下面 `ReportRaw` 读 `+0x1C1` 会越界，
        //   读数不确定（本批第一版就是这么红的：读到的是堆上的残留字节）。
        g_ParentBytes.assign(kEntityPlayerSize, 0x5A);
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

//: ★ 判据①：**直接读引擎内存的原始字节**（不经过我们自己的读侧 API）。
unsigned Raw(const std::vector<unsigned char>& block, std::uintptr_t offset) {
    return static_cast<unsigned>(block[offset]);
}

void ReportRaw(const char* label, const std::vector<unsigned char>& block) {
    std::printf("B315 %s vis=%u exists=%u dead=%u\n", label,
                Raw(block, kEntityVisibleOffset), Raw(block, kEntityExistsOffset),
                Raw(block, kEntityIsDeadOffset));
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

    // 四个场景（初值 / 是否让第二个句柄失效）：
    //   write      —— 三格全 0（`Die` 之后只该有 dead 变 1）
    //   idempotent —— 三格全 1（已经是"死"⇒ 再 `Die` 仍是 1）
    //   neighbors  —— visible=1 / exists=1 / dead=0（★ 专抓"写错相邻那一格"）
    //   badparent  —— 第二个句柄失效（`q:Die()` **什么都不该写**、也不该抛错）
    Flags player{0, 0, 0};
    Flags parent{0, 0, 0};
    bool callOnParent = false;
    if (std::strcmp(scenario, "write") == 0) {
        // 默认值。
    } else if (std::strcmp(scenario, "idempotent") == 0) {
        player = Flags{1, 1, 1};
        parent = Flags{1, 1, 1};
    } else if (std::strcmp(scenario, "neighbors") == 0) {
        player = Flags{1, 1, 0};
        parent = Flags{1, 1, 1};
    } else if (std::strcmp(scenario, "badparent") == 0) {
        g_ParentIsGarbage = true;
        callOnParent = true;
    } else {
        return 91;
    }

    PublishFakeGame(player, parent);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function err(f) return tostring(select(2, pcall(f))) end"
        " local p = Isaac.GetPlayer(0)"
        " print('B315 pkind=' .. type(p))"
        " print('B315 fn=' .. type(p.Die))"
        " print('B315 deadbefore=' .. tostring(p:IsDead()))"
        // 返回 0 个值（PC 是 `void`）。
        " print('B315 rc=' .. tostring(select('#', p:Die())))"
        // ★ 判据②：与**读侧**（批次 293 已交付、读同一格）互相印证。
        " print('B315 deadafter=' .. tostring(p:IsDead()))"
        " print('B315 visafter=' .. tostring(p:IsVisible()))"
        " print('B315 existsafter=' .. tostring(p:Exists()))"
        // 第二个实体：`Die` 只该动**接收者自己**那一格。
        " local q = p.Parent"
        " print('B315 qdeadbefore=' .. tostring(q:IsDead()))"
        " print('B315 qrc=' .. tostring(select('#', q:Die())))"
        " print('B315 qdeadafter=' .. tostring(q:IsDead()))"
        // 参数闸门：写侧也**不收实参**（只有接收者）。
        " print('B315 arg=' .. ok(function() return p:Die(1) end))"
        " print('B315 argerr=' .. err(function() return p:Die(1) end))"
        // 点号显式 self（1 个参数）⇒ 放行。
        " print('B315 dot=' .. ok(function() return p.Die(p) end))"
        // 接收者闸门：不是实体句柄 ⇒ **硬报错**（全族共用）。
        " print('B315 badrecv=' .. ok(function() return p.Die({}) end))"
        " print('B315 badrecverr=' .. err(function() return p.Die({}) end))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b315.lua");
    static_cast<void>(result);

    // ★ 判据①：Lua 跑完之后，直接看引擎内存里的**原始字节**。
    ReportRaw("player", g_PlayerBytes);
    if (callOnParent) {
        ReportRaw("parent", g_ParentBytes);
    }
    return 0;
}
'''


class EntityDieBatch315Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b315-")
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
        # ★ 把 stderr 一起交回：只回 stdout 时，"脚本中途报错"与"什么都没做"长得一模一样。
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主）

    def test_die_writes_one_into_the_dead_byte(self):
        """★ 判据分两层：**引擎内存里那一格真的从 0 变 1**（C++ 直接读原始字节）+
        同一次调用之后 `IsDead()` 变 `true`（读侧与写侧读的是同一格，互相印证）。"""
        out = self.run_scenario("write")
        self.assertIn("B315 pkind=userdata", out)
        self.assertIn("B315 fn=function", out)
        self.assertIn("B315 deadbefore=false", out)
        #: ① 原始字节：只有 dead 那一格从 0 变 1。
        self.assertIn("B315 player vis=0 exists=0 dead=1", out)
        #: ② 读侧互相印证。
        self.assertIn("B315 deadafter=true", out)
        self.assertIn("B315 visafter=false", out)
        self.assertIn("B315 existsafter=false", out)

    def test_die_is_idempotent(self):
        """已经是"死"（那一格为 1）⇒ 再 `Die()` 仍是 1（与 `Entity::Kill()` 的守卫一致）。"""
        out = self.run_scenario("idempotent")
        self.assertIn("B315 deadbefore=true", out)
        self.assertIn("B315 player vis=1 exists=1 dead=1", out)
        self.assertIn("B315 deadafter=true", out)

    def test_die_does_not_touch_the_neighbouring_bytes(self):
        """★★★ 本批的**核心判据**：三格相邻，`Die` 只该动 `dead` 那一格。

        夹具把 `visible=1 / exists=1 / dead=0` 摆好 ⇒ `Die()` 之后原始字节必须是
        `vis=1 exists=1 dead=1`。★ 这三格在真机上相邻、语义也相近（"还能不能看见/还算不算
        实体表的一员/死没死"），写错一格在**真机上完全看不出来**（都变成非 0、
        `IsVisible()`/`Exists()` 也会跟着答 true）⇒ 只有宿主能把它们分开。
        """
        out = self.run_scenario("neighbors")
        self.assertIn("B315 player vis=1 exists=1 dead=1", out)
        self.assertIn("B315 visafter=true", out)
        self.assertIn("B315 existsafter=true", out)
        self.assertIn("B315 deadafter=true", out)
        #: 反向：不许把 visible / exists 写掉。
        self.assertNotIn("B315 player vis=0", out)
        self.assertNotIn("B315 player vis=1 exists=0", out)

    def test_die_writes_only_the_receivers_own_cell(self):
        """写的是**接收者自己**那个对象的那一格（第二个实体摆成"活着"⇒ 不受影响）。"""
        out = self.run_scenario("write")
        self.assertIn("B315 qdeadbefore=false", out)
        self.assertIn("B315 qdeadafter=true", out)

    def test_returns_nothing_and_gates_arguments(self):
        """`Die()` 是 `void`（**返回 0 个值**）+ 参数闸门（写侧也不收实参）。"""
        out = self.run_scenario("write")
        self.assertIn("B315 rc=0", out)
        self.assertIn("B315 arg=false", out)
        self.assertIn("Entity:Die accepts no arguments", out)
        #: 点号显式 self（1 个参数）⇒ 放行。
        self.assertIn("B315 dot=true", out)
        #: 接收者不是实体句柄 ⇒ 硬报错（全族共用）。
        self.assertIn("B315 badrecv=false", out)
        self.assertIn("expected an Entity", out)

    def test_invalid_receiver_writes_nothing_without_erroring(self):
        """★ 句柄失效（指向非实体内存）⇒ 接收者解析成 0 ⇒ **什么都不写**、**不抛错**。

        这是写侧最要紧的一条安全口径：绝不能在解析不出实体时照着一个 0 地址或越界地址写内存
        （`RowReturnsNoValues` 那一档配合 `engine_memory::WriteField` 的护栏）。
        """
        out = self.run_scenario("badparent")
        #: 第二个对象是一块垃圾内存 ⇒ 三格"原始字节"里不该出现我们的写入痕迹（全是 0x5A = 90）。
        self.assertIn("B315 parent vis=90 exists=90 dead=90", out)
        self.assertNotIn("B315 parent vis=90 exists=90 dead=1", out)
        #: 而且整场**没有抛错**（脚本跑到底了）。
        self.assertIn("B315 badrecverr=", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行（写侧形状 + 行内常量）/ 偏移常量 —— 完成定义台账引用的就是这个方法。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        for owner, name, index, prefix, inline_const, kind, missing in FIELD_APIS:
            with self.subTest(api=f"{owner}:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, "{owner}", '
                    f'"{name}"',
                    catalog, f"目录里没有 {owner}:{name}")
                #: 写侧的形状：`offset2` = **行内常量 1**、kind = `BoolWriteConst`。
                self.assertRegex(
                    isaac,
                    rf"\{{\s*(?i:0x0e01{index:04x}),\s*{prefix},\s*{inline_const},\s*"
                    rf"FieldKind::{kind},\s*FieldMissing::{missing},\s*"
                    rf"FieldReceipt::Entity,\s*0xFF\}}",
                    f"数据行缺失或形状/降级档不对：{owner}:{name}")
                self.assertRegex(constants,
                                 rf"inline constexpr uintptr_t {prefix}\s*=\s*0x[0-9A-Fa-f]+;")

        #: ★ 反回归：这一条**不许**被塞进引擎方法行表（它是纯字段写，不需要引擎函数）。
        self.assertNotRegex(isaac, r"0x0E0100DA[^\n]*EngineCallShape")
        #: ★ 写侧 kind 必须在 `RowReturnsNoValues` 里（否则会多压一个值）。
        self.assertRegex(isaac, r"RowReturnsNoValues[\s\S]{0,600}FieldKind::BoolWriteConst")

    def test_the_evidence_is_recorded(self):
        """★ 常量段必须写明"PC 的 `Die` 与 `IsDead` 读写同一格"与那条交叉印证。

        这条不是形式主义：交接 §4 把这一条列入"别碰"（理由是"0 个实现"），
        丢掉这段证据，后人会**再排除一次**。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        for token in ("0x412350", "0x436B60", "0x16b", "0x169", "0x1C3", "0x1C1",
                      "0x05C8E8", "Kill", "0x16A", "0x1C2"):
            self.assertIn(token, constants, f"证据 {token} 没有写进常量段")


if __name__ == "__main__":
    unittest.main()
