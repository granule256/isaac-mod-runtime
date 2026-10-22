"""门禁：`EntityPlayer:CheckFamiliar(...)`（批次 334，2026-10-03）。

## 这一条是什么

| API | 契约 | 引擎侧 | 语料 |
| --- | --- | --- | --- |
| `EntityPlayer:CheckFamiliar(FamiliarVariant, TargetCount, RNG, Item=nil, SubType=-1)` | `EntityPlayer.md:591` | `Entity_Player::check_familiar(u32,int,RNG&,Item const*,int)` @ `0x29AD94` → `void` | 3 处 |

★ 引擎符号逐字存在、而且是 **snake_case**（与 328 那批同一现象）。
★ 3 处语料调用**全是 3 参写法**（`IsaacOnTwitchReloaded/scripts/callbacks.lua:255`、
`RepentancePlus/RepentancePlus/main.lua:1742` 与 `:1743`）⇒ 后两个形参走的就是它们的缺省值。

## ★★★ 本批的关键点：**两个形参的缺省值都不是 0**

`void CheckFamiliar(..., ItemConfigItem SourceItemConfigItem = nil, int FamiliarSubType = -1)`

* 第 4 个缺省 `nil`（= 空指针）；
* 第 5 个缺省 **`-1`** —— 而引擎拿它的**符号位**分支
  （`0x29AE1C tbnz w24, #0x1f, ...`）⇒ **填 0 与填 -1 行为不同**（文档：`-1 matches any subtype`）。

⇒ 这正是"数据行那条路表达不了"的两点之一（另一点是"把 Lua 的 RNG 句柄当 `RNG&` 传"）：
`EngineCallShapeRow::optionalArgumentCount` 的语义写死了"省略的寄存器保持 0"
⇒ **手写处理器**（账目见 `runtime_constants.hpp` 批次 334 段）。⇒ **形状表零增长**。

## 宿主验到了什么、没验到什么

* **验到**：方法挂得上；3 / 4 / 5 参都**不报错、且返回 0 个值**；参数闸门（太少 / 太多 / 第 3 参不是 RNG）
  各自报错且消息里带 API 名字；点号 + 显式 `self` 放行。
* **没验**：**引擎那一步真的做了什么**（有没有把随从增/减到 `TargetCount`）—— 宿主里没有引擎函数
  ⇒ 必然走"入口取不到"那条降级 ⇒ **真值只能真机**。
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

INDEX = 0x00E6
HANDLER = "EntityPlayerCheckFamiliar"
OFFSET_NAME = "kEntityPlayerCheckFamiliarOffset"
ENTRY_NAME = "kEntityPlayerCheckFamiliarEntryWord"

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "entity_layout.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（与 328/332 的夹具同形）：只要一个"当前玩家"。
//   ★ 本批**故意不提供引擎函数** ⇒ 处理器必然走"入口取不到"那条降级 ⇒ 宿主看到"没做事、也没报错"。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
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

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, kEntityTypePlayer);

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
    static_cast<void>(argv);
    if (argc != 2) return 90;

    PublishFakeGame();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function err(f) return tostring(select(2, pcall(f))) end"
        " local p = Isaac.GetPlayer(0)"
        " print('B334 pkind=' .. type(p))"
        " print('B334 fn=' .. type(p.CheckFamiliar))"
        " local r = RNG()"
        " print('B334 rng=' .. type(r))"
        // 语料那三处的写法：3 个实参（后两个形参走缺省）。
        " print('B334 three=' .. ok(function() return p:CheckFamiliar(1, 0, r) end))"
        " print('B334 threecount=' .. tostring(select('#', p:CheckFamiliar(1, 0, r))))"
        // 写全 5 个。
        " print('B334 five=' .. ok(function() return p:CheckFamiliar(1, 0, r, nil, -1) end))"
        // 4 个（只省 subType）。
        " print('B334 four=' .. ok(function() return p:CheckFamiliar(1, 0, r, nil) end))"
        // 参数太少（缺 RNG）。
        " print('B334 two=' .. ok(function() return p:CheckFamiliar(1, 0) end))"
        " print('B334 twoerr=' .. err(function() return p:CheckFamiliar(1, 0) end))"
        // 参数太多。
        " print('B334 six=' .. ok(function() return p:CheckFamiliar(1, 0, r, nil, -1, 7) end))"
        // 第 3 个不是 RNG。
        " print('B334 badrng=' .. ok(function() return p:CheckFamiliar(1, 0, 5) end))"
        " print('B334 badrngerr=' .. err(function() return p:CheckFamiliar(1, 0, 5) end))"
        // 点号 + 显式 self。
        " print('B334 dot=' .. ok(function() return p.CheckFamiliar(p, 1, 0, r) end))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b334.lua");
    static_cast<void>(result);
    return 0;
}
'''


class CheckFamiliarBatch334Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b334-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self):
        result = subprocess.run([str(self.binary), "run"], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主）

    def test_three_arguments_are_accepted_and_return_nothing(self):
        """★ 语料那三处的写法（3 个实参）必须放行，且返回 **0 个值**（PC 返回 `void`）。"""
        out = self.run_scenario()
        self.assertIn("B334 pkind=userdata", out)
        self.assertIn("B334 fn=function", out)
        self.assertIn("B334 rng=userdata", out)
        self.assertIn("B334 three=true", out)
        self.assertIn("B334 threecount=0", out)

    def test_optional_tail_arguments_are_accepted(self):
        """★ 后两个形参带缺省值 ⇒ **4 个和 5 个实参也都放行**（PC 同样如此）。"""
        out = self.run_scenario()
        self.assertIn("B334 four=true", out)
        self.assertIn("B334 five=true", out)

    def test_argument_gate_rejects_too_few_and_too_many(self):
        """参数闸门：2 个（缺 RNG）与 6 个都报错，且消息里有 API 名字。"""
        out = self.run_scenario()
        self.assertIn("B334 two=false", out)
        self.assertIn("B334 six=false", out)
        self.assertIn("EntityPlayer:CheckFamiliar expects", out)

    def test_the_third_argument_must_be_an_rng(self):
        """★ 第 3 个参数必须是 **RNG 句柄**（契约里它没有缺省值）⇒ 不是就报错。"""
        out = self.run_scenario()
        self.assertIn("B334 badrng=false", out)
        self.assertIn("EntityPlayer:CheckFamiliar expects an RNG", out)

    def test_dot_call_with_explicit_self_is_accepted(self):
        """点号 + 显式 `self`（`p.CheckFamiliar(p, ...)`）与冒号调用等价 ⇒ 放行。"""
        out = self.run_scenario()
        self.assertIn("B334 dot=true", out)

    def test_without_an_engine_nothing_happens_and_nothing_raises(self):
        """★ 宿主里没有引擎函数 ⇒ 走"入口取不到" ⇒ **不报错、也不压值**（验的是**降级档选对了**）。"""
        out = self.run_scenario()
        self.assertNotIn("attempt to", out)
        #: 三个"正常路径"的调用全部返回 true（没有 Lua 错误冒出来）。
        for needle in ("B334 three=true", "B334 four=true", "B334 five=true"):
            self.assertIn(needle, out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 绑定行 / 常量 / 入口首字核对 —— 完成定义台账引用的就是这个方法。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        api = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        self.assertIn(
            f'MakeId(ApiDomain::Isaac, 1, 0x{INDEX:04X}), ApiDomain::Isaac, '
            f'"EntityPlayer", "CheckFamiliar"', catalog, "目录行缺失")
        self.assertIn(f"{{0x0E01{INDEX:04X}, &{HANDLER}}}", api, "绑定行缺失")
        self.assertIn(f"inline constexpr uintptr_t {OFFSET_NAME} = 0x29AD94;", constants)
        self.assertIn(f"inline constexpr std::uint32_t {ENTRY_NAME} = 0xD10243FFu;", constants)
        self.assertRegex(api, rf"EngineEntryWordMatches\(method, {ENTRY_NAME}\)")
        #: ★★ 反回归：这一条**不许**被塞进数据行/引擎方法行表（它是手写处理器）。
        self.assertNotRegex(api, rf"0x0E01{INDEX:04X}[^\n]*EngineCallShape")
        self.assertNotRegex(api, rf"0x0E01{INDEX:04X}[^\n]*FieldKind::")
        #: ★ 第 3 参的 RNG 用**现成**那套接法（与 `Level:QueryRoomTypeIndex` 逐字同形）。
        self.assertRegex(api, r"rng->storage\.data\(\)")
        #: ★ 返回 `void` ⇒ 不许出现任何 `PushLuaVector` / `lua_pushinteger` 的返回值压栈。
        self.assertRegex(api, r"EntityPlayerCheckFamiliar\(lua_State\* state\)")

    def test_the_non_zero_defaults_are_recorded(self):
        """★★ 常量段必须写明「后两个形参的缺省值不是 0」这件事本身，以及它的**引擎侧证据**。

        这条不是形式主义：`optionalArgumentCount` 那套机制把"省略 = 寄存器保持 0"写死了，
        将来有人照着那条路把这一条改成数据行，`FamiliarSubType` 就会变成 0
        （= 只匹配 subtype 0，与 PC 的"任意 subtype"不同）—— 这是**静默**的语义偏离。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        folded = constants.lower()
        for needle in ("0x72eb50", "0x29ad94", "check_familiar", "rng::next", "0xf50",
                       "tbnz", "0x1f", "sourceitemconfigitem", "familiarsubtype"):
            self.assertIn(needle, folded, f"证据 {needle} 没有写进常量段")
        #: 「-1 不是 0」这件事本身要留痕。
        self.assertIn("-1", constants)
        self.assertIn("nil", constants)
        #: 契约页与行号。
        self.assertIn("EntityPlayer.md", constants)
        self.assertIn("591", constants)


if __name__ == "__main__":
    unittest.main()
