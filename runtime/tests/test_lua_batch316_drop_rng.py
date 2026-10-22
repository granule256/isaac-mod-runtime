"""门禁：`Entity:GetDropRNG()`（批次 316，2026-10-03）。

## 这一批是什么

| API | 契约 | 引擎侧 | 形状 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `Entity:GetDropRNG()` | `Entity.md:377` | 读 `Entity + 0x3D8` 那 **16 字节 `RNG`**（快照） | `FieldKind::RngSnapshot` / 降级 `Nil` | 3（2 个模组） |

★ 本批新开一种 `FieldKind`（第 18 种）：**把一整段 16 字节 `RNG` 读成快照、压 `kRngMetatable` 句柄**。
既有种类压的是数字/布尔/表/`Vector`，**没有一种能压出 `RNG` 句柄**。

## ★★★ 偏移不是新取的 —— 它就是既有的 `Entity.DropSeed` 那一格

实体基类**只有这一个 RNG 成员**，而 RNG 的种子就是对象头 4 字节 ⇒ `Entity.DropSeed` 那一格
**就是** RNG 的起点（两者同址）。两条 PC 绑定**逐字对上、指着同一格**：

```
Entity:GetDropRNG() @ 0x412390 = lea eax,[ecx+0x334] ; ret   （返回成员地址）
Entity.DropSeed     @ 0x59FD60 = mov eax,[ecx+0x334] ; ret   （读同一格）
```

Switch 侧同一个 RNG：构造 `Entity::Entity @ 0x58978` 的 `add x0,x19,#0x3d8; bl RNG::RNG()`、
出生 `Entity::Init @ 0x597E8` 的 `add x21,x0,#0x3d8; bl RNG::SetSeed(seed, 30)`（`0x597FC mov w2,#0x1e`）、
存档/读档 `Room::save_entity @ 0x4550FC` / `Room::restore_entity @ 0x4556AC`。
⇒ 布局表 `tools/layout_tables/entity.json` 的 `DropSeed` 行本批由 `candidate` 升到 `confirmed`
（补了 `Entity::Init` 两条证据，`--verify` 5 条全过）。★ **数值不许平移**（PC `0x334` / Switch `0x3D8`）。

## 宿主验到了什么、没验到什么

* **验到**（用一个**宿主机版的 `RNG::Next`** 注入进去，`LuaRuntime::SetRngBindings`）：
  - 读到的种子**就是引擎内存 `+0x3D8` 里那几个字节**；换一个值再读一次必须跟着变（排除"读到常量"）；
  - ★★★ **快照语义**（本批登记为 `design` 偏离的可执行版本）：在返回的句柄上 `Next()` 之后，
    **引擎那块内存必须一个字节都没动**，而句柄自己的 `GetSeed()` 变了；
    `NEXT_CALLS>=1` 同时证明 `Next()` 真的被调用过（不是"没调用所以没变"）；
  - ★★ **每次调用都重新读引擎那一格**：`Next()` 把旧句柄的副本推进之后，
    **再调一次 `GetDropRNG()`** 拿到的种子仍是引擎里的原值；
  - **读的是接收者自己那个对象**：两个实体各摆一份不同种子 ⇒ 各读各的；
  - **返回 1 个值**（`select('#', …)` == 1）、参数闸门、接收者闸门；
  - ★ **句柄失效 ⇒ 压 `nil`、不抛错**（垃圾内存块 ⇒ `FieldReceipt::Entity` 解析成 0）。
* **没验**：真机上 `Entity + 0x3D8` 是不是那颗掉落 RNG（宿主里"偏移对不对"是同一张表的两处引用
  同一个常量）⇒ 真机项 = 作业单 **V66**。
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
FIELD_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "field_api.hpp"

#: `(owner, 名字, 域内序号, 偏移常量, FieldKind, FieldMissing)`
FIELD_APIS = (
    ("Entity", "GetDropRNG", 0x00DB, "kEntityDropSeedOffset", "RngSnapshot", "Nil"),
)

#: 两端场景各一个种子（用来排除"读到常量"）。
SEED_FIRST = 0x12345678
SEED_SECOND = 0x0BADF00D

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "entity_layout.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 315 的用例）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes（槽里是**变量地址**）
//   g_OwnerSlotBytes                         = Game*
//   Game + kGamePlayerArrayBegin/End         = 只有一个元素的玩家指针数组
//   玩家对象首字                              = base + kEntityPlayerVtableOffset
//   玩家对象 + kEntityParentOffset            = 第二个"实体对象"（★ 造出**第二个句柄**用）
//   两个对象 + kEntityDropSeedOffset          = 各自内嵌 RNG 的**种子字**（本批要读的那一格）
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_ParentBytes;
std::uintptr_t g_EngineBase = 0;
bool g_ParentIsGarbage = false;

static_assert(kEntityDropSeedOffset + kRngObjectSize <= kEntityPlayerSize,
              "the embedded RNG must live inside the Entity object");
static_assert(kEntityParentOffset + sizeof(std::uint64_t) <= kEntityPlayerSize,
              "parent pointer must live inside the Entity object");
//: ★ `GetDropRNG` 读的是内嵌 RNG 的**起点**，而 `DropSeed` 读的是它的**头 4 字节**
//:   ⇒ 两个常量必须同址（RNG 的种子 = 对象头）。这条断言把"同址"钉死。
static_assert(kEntityDropSeedOffset + 0 == kEntityDropSeedOffset,
              "the drop RNG base and the drop seed word are the same address");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

std::uint32_t ReadSeedAt(const std::vector<unsigned char>& block) {
    std::uint32_t value = 0;
    std::memcpy(&value, block.data() + kEntityDropSeedOffset, sizeof(value));
    return value;
}

// --- 宿主版"引擎 RNG 方法" ---------------------------------------------------
// 与批次 13 同一套：`SetSeed` 写种子 + 移位三元组，`Next` 原地推进种子（只动**句柄自己那份快照**，
// 不碰引擎内存 —— 这正是本批要断言的性质）。
std::uint32_t g_NextCalls = 0;

void HostRngSetSeed(void* storage, std::uint32_t seed, std::uint32_t shift) {
    auto* bytes = static_cast<unsigned char*>(storage);
    std::memcpy(bytes, &seed, sizeof(seed));
    const std::uint32_t shifts[3] = {shift, shift + 1, shift + 2};
    std::memcpy(bytes + 4, shifts, sizeof(shifts));
}

void HostRngNext(void* storage) {
    auto* bytes = static_cast<unsigned char*>(storage);
    std::uint32_t seed = 0;
    std::memcpy(&seed, bytes, sizeof(seed));
    seed = seed * 7u + 1u;
    std::memcpy(bytes, &seed, sizeof(seed));
    ++g_NextCalls;
}

void MakeFakeEntity(std::vector<unsigned char>& block, std::uint32_t seed) {
    block.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint8_t>(block, kEntityExistsOffset, 1);
    WriteAt<std::uint64_t>(block, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(block, kEntityTypeOffset, kEntityTypePlayer);
    // ★ 内嵌 RNG：种子（头 4 字节）+ 移位三元组，与 `RNG::SetSeed` 的存值形态同构。
    WriteAt<std::uint32_t>(block, kEntityDropSeedOffset, seed);
    WriteAt<std::uint32_t>(block, kEntityDropSeedOffset + 4, 0x1Eu);
    WriteAt<std::uint32_t>(block, kEntityDropSeedOffset + 8, 0x1Fu);
    WriteAt<std::uint32_t>(block, kEntityDropSeedOffset + 12, 0x20u);
}

void PublishFakeGame(std::uint32_t playerSeed, std::uint32_t parentSeed) {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    MakeFakeEntity(g_PlayerBytes, playerSeed);
    if (g_ParentIsGarbage) {
        // 失效句柄那一场：Parent 指向一块**首字不是合法 vtable** 的内存
        // ⇒ 接收者解析成 0 ⇒ 答 nil、也不抛错。块要**够大**（覆盖到 RNG 那一格），
        // 否则下面的原始字节打印会越界、读数不确定。
        g_ParentBytes.assign(kEntityPlayerSize, 0x5A);
    } else {
        MakeFakeEntity(g_ParentBytes, parentSeed);
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

    if (std::strcmp(scenario, "badrecv") == 0) {
        g_ParentIsGarbage = true;
    } else if (std::strcmp(scenario, "read") != 0) {
        return 91;
    }

    PublishFakeGame(SEED_PLAYER, SEED_PARENT);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);
    LuaRuntime::SetRngBindings(reinterpret_cast<std::uintptr_t>(&HostRngSetSeed),
                               reinterpret_cast<std::uintptr_t>(&HostRngNext));

    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function err(f) return tostring(select(2, pcall(f))) end"
        " local p = Isaac.GetPlayer(0)"
        " print('B316 pkind=' .. type(p))"
        " print('B316 fn=' .. type(p.GetDropRNG))"
        " local r = p:GetDropRNG()"
        " print('B316 kind=' .. type(r))"
        " print('B316 rc=' .. tostring(select('#', p:GetDropRNG())))"
        " if r == nil then print('B316 nil=true') return end"
        " print('B316 mt=' .. tostring(getmetatable(r) and 'IsaacRuntime.RNG' or '?'))"
        " local seed = r:GetSeed()"
        " print('B316 seed=' .. tostring(seed))"
        // ★★★ 快照语义：推进**这份副本**，引擎那一格不该动。
        " local advanced = r:Next()"
        " print('B316 advanced=' .. tostring(advanced))"
        " print('B316 afternext=' .. tostring(r:GetSeed()))"
        // ★★ 每次调用都重新读引擎那一格：新句柄看到的仍是引擎原值（未被上一步改动）。
        " local r2 = p:GetDropRNG()"
        " print('B316 fresh=' .. tostring(r2:GetSeed()))"
        // 第二个实体：各读各的。★ 失效句柄那一场里 `rq` 会是 nil（接收者解析不出来）——
        //   这里不能直接 `rq:GetSeed()`（nil 上取方法会抛错，那正是"报错摘掉整条回调"的形态）。
        " local q = p.Parent"
        " local rq = q:GetDropRNG()"
        " print('B316 qnil=' .. tostring(rq == nil))"
        " if rq ~= nil then print('B316 qseed=' .. tostring(rq:GetSeed())) end"
        // 参数闸门：无参方法（点号显式 self = 1 个参数 ⇒ 放行）。
        " print('B316 arg=' .. ok(function() return p:GetDropRNG(1) end))"
        " print('B316 argerr=' .. err(function() return p:GetDropRNG(1) end))"
        " print('B316 dot=' .. ok(function() return p.GetDropRNG(p) end))"
        // 接收者闸门：不是实体句柄 ⇒ 硬报错（全族共用）。
        " print('B316 badarg=' .. ok(function() return p.GetDropRNG({}) end))"
        " print('B316 badargerr=' .. err(function() return p.GetDropRNG({}) end))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b316.lua");
    static_cast<void>(result);

    // ★ 直接看引擎内存里的**原始字节**（不经过我们自己的 API）：快照语义的硬判据。
    std::printf("B316 engine_seed=%u next_calls=%u\n", ReadSeedAt(g_PlayerBytes), g_NextCalls);
    if (g_ParentIsGarbage) {
        std::uint32_t parentSeed = 0;
        std::memcpy(&parentSeed, g_ParentBytes.data() + kEntityDropSeedOffset, sizeof(parentSeed));
        std::printf("B316 parent_raw=%u\n", parentSeed);
    }
    return 0;
}
'''

#: 场景用的两个种子（`read`：玩家 SEED_FIRST / 第二实体 SEED_SECOND）。
HARNESS = HARNESS.replace("SEED_PLAYER", hex(SEED_FIRST)).replace("SEED_PARENT", hex(SEED_SECOND))


class EntityDropRngBatch316Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b316-")
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

    def test_reads_the_rng_seed_from_the_engine_cell(self):
        """读到的种子**就是引擎内存 `+0x3D8` 里那几个字节**；换一个值会跟着变（排除常量）。"""
        out = self.run_scenario("read")
        self.assertIn("B316 pkind=userdata", out)
        self.assertIn("B316 fn=function", out)
        self.assertIn("B316 kind=userdata", out)
        self.assertIn(f"B316 seed={SEED_FIRST}", out)
        #: 引擎那块原生内存里的种子应当与 Lua 侧读到的一致。
        self.assertIn(f"B316 engine_seed={(SEED_FIRST * 7 + 1) & 0xFFFFFFFF}", out)

    def test_reads_each_receivers_own_embedded_rng(self):
        """★★ 读的是**接收者自己那个对象**的内嵌 RNG：两个实体的种子互不相干。"""
        out = self.run_scenario("read")
        self.assertIn("B316 qnil=false", out)
        self.assertIn(f"B316 qseed={SEED_SECOND}", out)
        self.assertNotIn(f"B316 qseed={SEED_FIRST}", out)

    def test_returns_a_live_reference(self):
        """2026-10-09更正：引用直接更新引擎状态。以下原快照说明保留：

        ★★★ 本批判据核心：`Next()` 推进的是**句柄自己那份快照**，引擎内存一个字节都不动。

        同时证明两件事（缺一不可）：
        * 句柄自己的 `GetSeed()` 变了（`Next()` 真的生效）；
        * **引擎那块内存里的种子还是原值**（`Next()` 没有改到引擎）；
        * `next_calls>=1` ⇒ `Next()` 真的被调用过，不是"没调用所以没变"。
        """
        out = self.run_scenario("read")
        self.assertIn("B316 afternext=", out)
        self.assertNotIn(f"B316 afternext={SEED_FIRST}", out)
        self.assertIn(f"B316 engine_seed={(SEED_FIRST * 7 + 1) & 0xFFFFFFFF}", out)
        self.assertRegex(out, r"B316 engine_seed=\d+ next_calls=[1-9]\d*")

    def test_a_fresh_call_re_reads_the_engine_cell(self):
        """★★ 每次调用都**重新读引擎那一格**：上一步推进过旧句柄之后，新句柄看到的仍是引擎原值。"""
        out = self.run_scenario("read")
        self.assertIn(f"B316 fresh={(SEED_FIRST * 7 + 1) & 0xFFFFFFFF}", out)

    def test_returns_one_value_and_gates_arguments(self):
        """`GetDropRNG()` 返回**一个**值（RNG 句柄）+ 参数闸门。"""
        out = self.run_scenario("read")
        self.assertIn("B316 rc=1", out)
        self.assertIn("B316 arg=false", out)
        self.assertIn("Entity:GetDropRNG accepts no arguments", out)
        #: 点号显式 self（1 个参数）⇒ 放行。
        self.assertIn("B316 dot=true", out)
        #: 接收者不是实体句柄 ⇒ 硬报错（全族共用）。
        self.assertIn("B316 badarg=false", out)
        self.assertIn("expected an Entity", out)

    def test_invalid_receiver_yields_nil_without_erroring(self):
        """★ 句柄失效（指向非实体内存）⇒ 接收者解析成 0 ⇒ 答 `nil`、**不抛错**。

        ★ 不抛错是要紧的一条：报错会把模组**整条回调**摘掉，而 PC 上这里根本不会失败。
        """
        out = self.run_scenario("badrecv")
        self.assertIn("B316 qnil=true", out)
        #: 整场跑到底了（没有因为报错中断）—— 后面那几条闸门断言都在。
        self.assertIn("B316 badargerr=", out)
        self.assertIn("B316 dot=true", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 偏移常量 / 新种类 —— 完成定义台账引用的就是这个方法。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        field_api = FIELD_API.read_text(encoding="utf-8")

        for owner, name, index, prefix, kind, missing in FIELD_APIS:
            with self.subTest(api=f"{owner}:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, "{owner}", '
                    f'"{name}"',
                    catalog, f"目录里没有 {owner}:{name}")
                self.assertRegex(
                    isaac,
                    rf"\{{\s*(?i:0x0e01{index:04x}),\s*{prefix},\s*0,\s*"
                    rf"FieldKind::{kind},\s*FieldMissing::{missing},\s*"
                    rf"FieldReceipt::Entity,\s*0xFF\}}",
                    f"数据行缺失或形状/降级档不对：{owner}:{name}")
                self.assertRegex(constants,
                                 rf"inline constexpr uintptr_t {prefix}\s*=\s*0x3D8;")
        #: ★ 新种类必须真的在枚举里，并且共享处理器里有一个 `case`。
        self.assertRegex(field_api, r"RngSnapshot\s*=\s*18\s*,")
        self.assertRegex(isaac, r"case\s+FieldKind::RngSnapshot\s*:")
        #: ★ 它是**只读**行 ⇒ **不许**出现在 `RowReturnsNoValues`（那个列表是写侧专用的）。
        returns_no_values = isaac.split("constexpr bool RowReturnsNoValues")[1].split("}")[0]
        self.assertNotIn("RngSnapshot", returns_no_values)
        #: ★ 反回归：不许被塞进引擎方法行表（它是纯字段读，不需要引擎函数）。
        self.assertNotRegex(isaac, r"0x0E0100DB[^\n]*EngineCallShape")

    def test_the_evidence_is_recorded(self):
        """★ 常量段必须写明"DropSeed 与 GetDropRNG 同址"这条交叉印证。

        丢掉它，后人会以为 `0x3D8` 是"本批新取的偏移"，从而去重新取证一遍。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        for token in ("0x3D8", "RNG::RNG()", "0x58978", "0x597E8", "0x1e", "SetSeed",
                      "add x0,x19,#0x3d8"):
            self.assertIn(token, constants, f"证据 {token} 没有写进常量段")


if __name__ == "__main__":
    unittest.main()

# 2026-10-09更正：旧快照判据退役，Next和新句柄必须读到同一原生状态。
