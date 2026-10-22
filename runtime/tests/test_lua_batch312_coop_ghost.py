"""门禁：`EntityPlayer:IsCoopGhost()`（批次 312，2026-10-03）。

## 这一批是什么

| API | 契约 | 引擎侧依据 | 形状 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `EntityPlayer:IsCoopGhost()` | `EntityPlayer.md:1499` | 没有同名函数 ⇒ 直读 `Entity_Player + 0x284C` 那**一个字节** | `Bool` / `False` | 1（BOIStageAPI15） |

走**字段读取型数据行**（`isaac_api.cpp` 的 `kFieldApis`，**0 字节代码**）。
取值锚点 = 引擎自己的**三个具名写入方 + 一个具名消费者**（四项语义完全吻合）：

* `Entity_Player::morph_to_coop_ghost() @ 0x2E788C` —— 变成合作幽灵时 **置 1**
  （`x22 = 玩家 + 0x27E0`，`strb w21,[x22,#0x6C]` ⇒ `玩家 + 0x284C = 1`）；
* `Entity_Player::init_coop_ghost() @ 0x2F7FF8` —— 初始化合作幽灵时 **置 1**
  （`add x22, x0, #0x284C` + `strb w21,[x22]`）；
* `Entity_Player::revive_coop_ghost() @ 0x2F7CDC` —— 复活（不再是幽灵）时 **清 0**
  （`strb wzr, [x0, #0x284C]`）；
* `PlayerManager::GetNumCoopPlayersAlive() @ 0x4433B4` —— **具名消费者**：读这一格后
  `eor w12,w12,#0x1` 再加进计数 ⇒ 数的是"标志为 0 的玩家"（= 还活着的合作玩家）
  ⇒ **置 1 = 是合作幽灵**。

PC 侧对照：绑定函数 `0x6C4AF0` = `mov al, byte ptr [ecx+0x1f88]; ret` ⇒ PC 偏移 `+0x1F88`
（数值不许平移）。逐条证据写在 `runtime_constants.hpp` 的**批次 312 段**。

## 宿主验到了什么、没验到什么

* **验到**：写进去什么就读回什么、读的是**接收者自己那一格**、**"非 0 即真"**（写 `0x7F` 也答 true）、
  ★ **读的是"字节"而不是 `u32`**（这一格写 `0x00000100` ⇒ 低字节是 0 ⇒ 必须答 `false`，
  按 `u32` 读会答 `true` —— 这是"哪一种输入能把两者分开"的判别组）、
  返回**布尔**（不是数字）、参数闸门与接收者闸门。
* **没验**：**真机上的偏移归属**。宿主里"偏移对不对"是同一张表的两处都引用同一个常量
  ⇒ 只有真机能看这一格是不是真的合作幽灵标志 ⇒ 真机项 = 作业单 **V62**。
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

#: `(owner, 名字, 域内序号, 偏移常量, FieldKind, FieldMissing)`
FIELD_APIS = (
    ("EntityPlayer", "IsCoopGhost", 0x00D8, "kEntityPlayerCoopGhostFlagOffset", "Bool", "False"),
)

#: 夹具写进"玩家"与"父实体"的值。两个对象**故意不同**：读错对象（例如恒定读玩家）
#: 会被 `q*=` 那几条断言抓住。
PLAYER = {"flag": 1}      # 是合作幽灵
PARENT = {"flag": 0}      # 不是


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状与批次 284/286/287/288 的用例同源）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_Game 变量（槽里是**变量地址**）
//   g_Game 变量                     = Game*
//   Game + kGamePlayerArrayBegin/End = 只有一个元素的玩家指针数组
//   玩家对象首字                     = base + kEntityPlayerVtableOffset（`IsEntityPlayer` 要它）
//   玩家对象 + kEntityParentOffset   = 第二个"玩家对象"（`Entity.Parent`，用来验"读自己那格"）
//
// ★ 本批是字段行 ⇒ **没有入口指纹** ⇒ 宿主里能真的读到伪造块里的字节（不是降级值）。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_ParentBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::uintptr_t g_EngineBase = 0;

static_assert(kEntityParentOffset < kEntityPlayerSize,
              "parent pointer must live inside the Entity_Player object");
static_assert(kEntityPlayerCoopGhostFlagOffset + sizeof(std::uint8_t) <= kEntityPlayerSize,
              "coop ghost flag must live inside the Entity_Player object");
//: ★ 与邻格区分：合作幽灵标志**不是** `_cacheFlags`（`+0x1958`）、也不是玩家下标（`+0x19F0`）——
//:   写错格在宿主里会立刻被下面那些断言抓住（"值对不上"而不是"不报错"）。
static_assert(kEntityPlayerCoopGhostFlagOffset != kEntityPlayerCacheFlagsOffset,
              "coop ghost flag must not alias cache flags");
static_assert(kEntityPlayerCoopGhostFlagOffset != kEntityPlayerIndexOffset,
              "coop ghost flag must not alias the player index");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void MakeFakePlayer(std::vector<unsigned char>& block) {
    block.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(block, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(block, kEntityTypeOffset, kEntityTypePlayer);
    WriteAt<std::uint32_t>(block, kEntityPlayerTypeOffset, 0);
    WriteAt<std::uint32_t>(block, kEntityPlayerIndexOffset, 0);
}

void PublishFakeGame(std::uint8_t playerFlag, std::uint8_t parentFlag) {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    MakeFakePlayer(g_PlayerBytes);
    MakeFakePlayer(g_ParentBytes);
    WriteAt<std::uint8_t>(g_PlayerBytes, kEntityPlayerCoopGhostFlagOffset, playerFlag);
    WriteAt<std::uint8_t>(g_ParentBytes, kEntityPlayerCoopGhostFlagOffset, parentFlag);
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

    // 四个场景：
    //   ghost    —— 玩家 1 / 父 0（两个对象不同 ⇒ 专抓"恒定读玩家"）
    //   notghost —— 玩家 0 / 父 1（**反过来**摆，专抓"把两个偏移写反"或"写死 true"）
    //   nonzero  —— 玩家 0x7F（**非 0 但不是 1**）⇒ 必须答 true（"非 0 即真"，不是 "== 1"）
    //   highbyte —— 在这一格写 **`u32 = 0x100`**（低字节是 0、第二字节是 1）
    //               ⇒ 按**字节**读必须答 false；按 `u32` 读会答 true（判别组）
    std::uint8_t playerFlag = 1;
    std::uint8_t parentFlag = 0;
    bool highByteProbe = false;
    if (std::strcmp(scenario, "ghost") == 0) {
        // 默认值（与 Python 侧的 `PLAYER` / `PARENT` 一致）。
    } else if (std::strcmp(scenario, "notghost") == 0) {
        playerFlag = 0;
        parentFlag = 1;
    } else if (std::strcmp(scenario, "nonzero") == 0) {
        playerFlag = 0x7F;
        parentFlag = 0x00;
    } else if (std::strcmp(scenario, "highbyte") == 0) {
        playerFlag = 0x00;
        parentFlag = 0x00;
        highByteProbe = true;
    } else {
        return 91;
    }

    PublishFakeGame(playerFlag, parentFlag);
    if (highByteProbe) {
        // 覆盖成一个 `u32`：`0x00000100` ⇒ 低字节 0、第二字节 1。
        WriteAt<std::uint32_t>(g_PlayerBytes, kEntityPlayerCoopGhostFlagOffset, 0x00000100u);
    }
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local p = Isaac.GetPlayer(0)"
        " print('B312 pkind=' .. type(p))"
        " print('B312 fn=' .. type(p.IsCoopGhost))"
        " print('B312 ghost=' .. tostring(p:IsCoopGhost()))"
        " print('B312 ghosttype=' .. type(p:IsCoopGhost()))"
        // 读的是**接收者自己**那一格：`p.Parent` 是另一个"玩家对象"（标志摆成相反值）。
        " local q = p.Parent"
        " print('B312 qkind=' .. type(q))"
        " print('B312 qghost=' .. tostring(q:IsCoopGhost()))"
        // 参数闸门：字段行**恰好收一个**参数（只有接收者），多给一个就报错。
        " print('B312 arg=' .. ok(function() return p:IsCoopGhost(1) end))"
        " print('B312 argerr=' .. tostring(select(2, pcall(function()"
        "   return p:IsCoopGhost(1) end))))"
        // 点号显式 self（`p.IsCoopGhost(p)`）也是 1 个参数 ⇒ 放行（与字段行口径一致）。
        " print('B312 dot=' .. ok(function() return p.IsCoopGhost(p) end))"
        // 接收者闸门：非实体句柄 ⇒ **硬报错**（全族共用，本批没动它）。
        " local f = p.IsCoopGhost"
        " print('B312 badrecv=' .. ok(function() return f({}) end))"
        " print('B312 badrecverr=' .. tostring(select(2, pcall(f, {}))))"
        // 对照：同族老字段（`GetSoulHearts`）拿同一个坏接收者**也报同样的错**
        // ⇒ 接收者那一层不是本批引入的。
        " local g = p.GetSoulHearts"
        " print('B312 siblingbadrecv=' .. ok(function() return g({}) end))"
        " print('B312 sibling=' .. type(p.GetSoulHearts))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b312.lua");
    static_cast<void>(result);
    return 0;
}
'''


class EntityPlayerCoopGhostBatch312Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b312-")
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

    def test_flag_is_read_from_the_receivers_own_byte(self):
        """★ 写进去什么就读回什么，而且是**接收者自己那个对象**的格子、返回**布尔**。

        为什么这是硬判据：数据行没挂到 `EntityPlayer` 页 ⇒ `p.IsCoopGhost` 是 `nil`；
        偏移写错格（例如抄成 `_cacheFlags`）⇒ 值是别的数、下面的 true/false 会红；
        形状写成 `U32` ⇒ 返回值是数字不是 `boolean`。
        """
        out = self.run_scenario("ghost")
        self.assertIn("B312 pkind=userdata", out)
        self.assertIn("B312 fn=function", out)
        self.assertIn("B312 ghost=true", out)
        self.assertIn("B312 ghosttype=boolean", out)
        #: `Parent` 是另一个对象（标志摆成相反值）⇒ 证明读的是**接收者自己**那一格。
        self.assertIn("B312 qkind=userdata", out)
        self.assertIn("B312 qghost=false", out)

    def test_flag_inverts_with_the_receiver(self):
        """把两个对象的标志**反过来摆** ⇒ 两条断言同时对调。

        这一场专抓两类错法：① 实现把接收者写死成"当前玩家"（那 `qghost` 会跟 `ghost` 一样）；
        ② 实现把结果写死成 `true`/`false`（那两场不可能同时对上）。
        """
        out = self.run_scenario("notghost")
        self.assertIn("B312 ghost=false", out)
        self.assertIn("B312 qghost=true", out)

    def test_non_zero_means_true(self):
        """`0x7F`（非 0 但**不是 1**）⇒ 必须答 `true`。

        PC 的绑定本体是 `mov al, byte ptr [ecx+0x1f88]` + 胶水层的布尔转换 ⇒ **非 0 即真**。
        写成"等于 1 才真"会在"这一格被当成位掩码用"时静默答错（本项目反复记的
        "看起来像真值的错值"那一类）。
        """
        out = self.run_scenario("nonzero")
        self.assertIn("B312 ghost=true", out)
        self.assertIn("B312 qghost=false", out)

    def test_reads_a_byte_not_a_u32(self):
        """★ 判别组：这一格写 `u32 = 0x100`（低字节 0、第二字节 1）⇒ 按**字节**读必须答 `false`。

        按 `u32` 读（`BoolNonZero`）会读到 `256` ⇒ 答 `true`。两种输入把"读一个字节"与
        "读四个字节"**分开** —— 这正是 `FieldKind::Bool`（`ReadField<uint8_t>`）与
        `FieldKind::BoolNonZero`（`ReadField<uint32_t>`）唯一能被区分的地方。
        """
        out = self.run_scenario("highbyte")
        self.assertIn("B312 ghost=false", out)
        self.assertNotIn("B312 ghost=true", out)

    def test_argument_gate_and_receiver_gate(self):
        """参数闸门 = **恰好一个**（只有接收者）；接收者不是实体句柄 = **硬报错**。"""
        out = self.run_scenario("ghost")
        #: 多给一个参数 ⇒ 报错（消息按 catalog 里的 owner:name 现拼）。
        self.assertIn("B312 arg=false", out)
        self.assertIn("EntityPlayer:IsCoopGhost accepts no arguments", out)
        #: 点号显式 self（1 个参数）⇒ 放行（字段行的既有口径，不是引擎方法行那套"尾部可省"）。
        self.assertIn("B312 dot=true", out)
        #: 坏接收者 ⇒ 硬报错；同族老字段报同样的错（接收者那一层不是本批引入的）。
        self.assertIn("B312 badrecv=false", out)
        self.assertIn("expected an Entity", out)
        self.assertIn("B312 siblingbadrecv=false", out)
        self.assertIn("B312 sibling=function", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 形状与降级档 / 偏移常量 —— 完成定义台账引用的就是这个方法。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

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
                    rf"FieldReceipt::EntityPlayer,\s*0xFF\}}",
                    f"数据行缺失或形状/降级档不对：{owner}:{name}")
                self.assertRegex(constants, rf"inline constexpr uintptr_t {prefix}\s*=\s*0x[0-9A-Fa-f]+;")

        #: ★ 反回归：这一条**不许**被塞进引擎方法行表（引擎里没有同名函数，
        #:   `tools/mangled_impl_count.py IsCoopGhost` = 0 个实现）。
        self.assertNotRegex(isaac, r"0x0E0100D8[^\n]*EngineCallShape")

    def test_the_evidence_is_recorded(self):
        """★ 常量段必须写明 PC 绑定 VA、四条 Switch 具名证据、以及"误认格"的排除。

        这条不是形式主义：本批最容易犯的错是把 `Entity + 0x384`（同样是 morph/init 置 1、
        revive 清 0 的字节）当成这一格 —— 判别靠的正是 `GetNumCoopPlayersAlive` 那条消费者。
        丢掉它，后人只会看到"某处有个字节"。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        self.assertIn(
            "inline constexpr uintptr_t kEntityPlayerCoopGhostFlagOffset = 0x284C;", constants)
        for token in ("0x6C4AF0", "0x1F88", "0x2E788C", "0x2F7FF8", "0x2F7CDC", "0x4433B4",
                      "0x27e0", "GetNumCoopPlayersAlive", "0x384"):
            self.assertIn(token, constants, f"证据 {token} 没有写进常量段")


if __name__ == "__main__":
    unittest.main()
