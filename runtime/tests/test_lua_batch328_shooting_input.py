"""门禁：`EntityPlayer:GetShootingInput()` / `EntityPlayer:GetShootingJoystick()`（批次 328，2026-10-03）。

## 这一批是什么

| API | 契约 | 引擎侧 | 语料调用点 |
| --- | --- | --- | --- |
| `EntityPlayer:GetShootingInput()` | `EntityPlayer.md:1235` | `Entity_Player::get_shooting_input()` @ `0x2B0FFC` → 返回 `Vector` | **14** |
| `EntityPlayer:GetShootingJoystick()` | `EntityPlayer.md:1245` | ★ **同一个函数**（PC 的两个名字表项指向同一个 VA `0x741B00`） | 2 |

合 **2 条 / 16 处** —— 是全清单里最大的一块。

**为什么两条是同一份实现**：PC 的 `GetShootingInput` 与 `GetShootingJoystick` 名字表项指向**同一个
`0x741B00`**（`python3 tools/pc_exe_binding.py` 各跑一次即可复现）⇒ 我们也是同一段代码的两张门面。

**为什么手写而不是数据行**：引擎返回 `KAGE::Math::Vector2`（两个 `float` 的 **HFA** ⇒ 走 `s0`/`s1`），
而通用跳板 `engine_call_trampoline.s` 只回填 `x0`/`d0` ⇒ 机制内表达不了。照 `Room:GetCenterPos()`
的先例，用一个"返回两个 float 的结构体"的函数指针类型让编译器生成 HFA 约定。

## ★★ 本批顺手发现的某类盲点（写在这里，免得下一个人再踩）

工作清单按 **Lua 名**（`GetShootingInput`）去符号表查，而引擎里是 **snake_case**
（`get_shooting_input`）⇒ 清单报了 `no_symbol`、把它塞进 `needs_forensics`。
同一次排查还捞出 `Entity_Familiar::follow_parent` / `add_to_followers` / `follow_position`
—— **按 snake_case 复查能翻出一批**。

## 宿主验到了什么、没验到什么

* **验到**（三条边界 + 挂载面）：
  - 两条方法真的挂在 `EntityPlayer` 的 `__methods` 上（`type(p.GetShootingInput) == "function"`）；
  - 调用**不报错**，且**返回一个 Lua `Vector`**（不是 `nil` —— 模组紧接着就 `.X`/`.Y`）；
  - 参数闸门：多给一个实参 ⇒ 报错，且消息里有**这一条 API 的名字**（两条各验一次）；
  - 点号 + 显式 `self` 也是 1 个实参 ⇒ 放行。
* **没验**：
  1. **值的真伪** —— 宿主里没有引擎函数 ⇒ 三条边界里那条"入口取不到"**必然命中**，所以宿主
     只能看到降级值 `Vector(0, 0)`。**真值只能真机**（作业单第九节的真机项）。
  2. "接收者不是精确 `Entity_Player`"那条分支：从 Lua 侧**走不到** —— `p.Parent` 交出的句柄
     按 `IsEntityPlayer` 选元表，非玩家对象拿到的是基类 `Entity` 元表（那上面没有这个方法）⇒
     只会是"调用 nil"。这条分支由下面的静态接线用例兜住。
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

#: `(API 名, 域名序号, 处理器名)`。
FIELD_APIS = (
    ("GetShootingInput", 0x00E0, "EntityPlayerGetShootingInput"),
    ("GetShootingJoystick", 0x00E1, "EntityPlayerGetShootingJoystick"),
)

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "entity_layout.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 316 的用例）：只要一个"当前玩家"，**不需要**房间/描述符。
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes（槽里是**变量地址**）
//   g_OwnerSlotBytes                         = Game*
//   Game + kGamePlayerArrayBegin/End         = 只有一个元素的玩家指针数组
//   玩家对象首字                              = base + kEntityPlayerVtableOffset（**精确**的玩家 vptr）
//
// ★ 本批**故意不提供任何引擎函数**：`get_shooting_input` 的地址在模块块里是 0
//   ⇒ 处理器必然走"入口取不到"那条降级路径 ⇒ 宿主看到的就是 `Vector(0, 0)`（这正是要钉的那条）。
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
        " print('B328 pkind=' .. type(p))"
        " print('B328 f1=' .. type(p.GetShootingInput))"
        " print('B328 f2=' .. type(p.GetShootingJoystick))"
        // ★ 返回值必须是**一个** Lua `Vector`（不是 nil、不是报错）—— 模组紧接着就取 `.X`/`.Y`。
        " local v = p:GetShootingInput()"
        " print('B328 kind=' .. type(v))"
        " print('B328 count=' .. tostring(select('#', p:GetShootingInput())))"
        " print('B328 xkind=' .. type(v.X) .. ' ykind=' .. type(v.Y))"
        " print('B328 x=' .. tostring(v.X) .. ' y=' .. tostring(v.Y))"
        " local j = p:GetShootingJoystick()"
        " print('B328 jkind=' .. type(j))"
        " print('B328 jx=' .. tostring(j.X) .. ' jy=' .. tostring(j.Y))"
        // 模组的真实用法（`IsaacOnTwitchReloaded/scripts/mechanics.lua:97`）：直接取分量做算术。
        " print('B328 use=' .. tostring(v.X * 10 + v.Y * 10))"
        // 参数闸门：多给一个 ⇒ 报错，且消息里带**这一条**的名字。
        " print('B328 extra=' .. ok(function() return p:GetShootingInput(1) end))"
        " print('B328 err1=' .. err(function() return p:GetShootingInput(1) end))"
        " print('B328 extra2=' .. ok(function() return p:GetShootingJoystick(1) end))"
        " print('B328 err2=' .. err(function() return p:GetShootingJoystick(1) end))"
        // 点号 + 显式 self 也是 1 个实参 ⇒ 放行。
        " print('B328 dot=' .. ok(function() return p.GetShootingInput(p) end))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b328.lua");
    static_cast<void>(result);
    return 0;
}
'''


class ShootingInputBatch328Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b328-")
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

    def test_both_methods_are_attached_and_return_a_vector(self):
        """★★ 两条方法都挂在 `EntityPlayer` 的 `__methods` 上，且返回**一个 Lua `Vector`**。

        这条钉的是"**不能返 `nil`**"：语料里 `p:GetShootingInput().X` 是连写的
        （`IsaacOnTwitchReloaded/scripts/mechanics.lua:97` 等 14 处），`nil` 会让整条回调
        以 "attempt to index a nil value" 被摘掉 —— 比"这次方向算成零"严重得多。
        """
        out = self.run_scenario()
        self.assertIn("B328 pkind=userdata", out)
        self.assertIn("B328 f1=function", out)
        self.assertIn("B328 f2=function", out)
        self.assertIn("B328 kind=userdata", out)
        #: ★ 恰好压 **1** 个返回值（PC 返回一个 `Vector`）。
        self.assertIn("B328 count=1", out)
        self.assertIn("B328 xkind=number ykind=number", out)
        self.assertIn("B328 jkind=userdata", out)
        #: 模组的连写用法必须走得通。
        self.assertIn("B328 use=", out)
        self.assertNotIn("attempt to", out)

    def test_the_engine_is_absent_so_the_fallback_is_vector_zero(self):
        """★ 宿主里没有引擎函数 ⇒ "入口取不到"那条降级必然命中 ⇒ 答 `Vector(0, 0)`、不报错。

        ★ 这条**不是**在验"值对不对"（那只能真机）：它验的是"**降级档选对了**" ——
        若把降级写成 `nil` / 不压值 / 报错，这里三条断言都会红。
        """
        out = self.run_scenario()
        self.assertIn("B328 x=0.0 y=0.0", out)
        self.assertIn("B328 jx=0.0 jy=0.0", out)

    def test_argument_gate_is_exactly_one_and_names_the_api(self):
        """参数闸门：**恰好一个**（`self`）；多给一个就报错，且消息里有**这一条**的名字。

        ★ 两条的消息必须**各说各的名字** —— 它们是同一段代码的两张门面，名字错了会让真机读数误导。
        """
        out = self.run_scenario()
        self.assertIn("B328 extra=false", out)
        self.assertIn("EntityPlayer:GetShootingInput accepts no arguments", out)
        self.assertIn("B328 extra2=false", out)
        self.assertIn("EntityPlayer:GetShootingJoystick accepts no arguments", out)
        #: 点号 + 显式 self 也是 1 个实参 ⇒ 放行。
        self.assertIn("B328 dot=true", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 绑定行 / 常量 / 入口首字 / 两条共用同一段实现 —— 完成定义台账引用的就是这个方法。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        api = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        for name, index, handler in FIELD_APIS:
            with self.subTest(api=f"EntityPlayer:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, '
                    f'"EntityPlayer", "{name}"', catalog, f"目录里没有 EntityPlayer:{name}")
                self.assertIn(f"{{0x0E01{index:04X}, &{handler}}}", api,
                              f"绑定表里没有 {handler}")
                #: ★★ 反回归：这两条**不能**被塞进引擎方法行/字段行表 ——
                #:   它们返回 16 字节的 `Vector`（HFA），机制里表达不了 ⇒ 只能是手写处理器。
                self.assertNotRegex(api, rf"0x0E01{index:04X}[^\n]*EngineCallShape")
                self.assertNotRegex(api, rf"0x0E01{index:04X},\s*k\w+Offset")

        #: 偏移与入口首字：常量段 + 处理器里真的核对了首字。
        self.assertIn("inline constexpr uintptr_t kEntityPlayerGetShootingInputOffset = 0x2B0FFC;",
                      constants)
        self.assertIn("inline constexpr std::uint32_t kEntityPlayerGetShootingInputEntryWord = "
                      "0xD10143FFu;", constants)
        self.assertRegex(api, r"EngineEntryWordMatches\(method, "
                              r"kEntityPlayerGetShootingInputEntryWord\)")
        #: ★★ 两条共用**同一段**实现（PC 的两个名字表项指向同一个 VA）—— 不是"两份长得像的代码"。
        self.assertRegex(api, r"int EntityPlayerShootingInputCommon\(lua_State\* state,")
        self.assertIn('EntityPlayerShootingInputCommon(state, "EntityPlayer:GetShootingInput")', api)
        self.assertIn('EntityPlayerShootingInputCommon(state, "EntityPlayer:GetShootingJoystick")',
                      api)
        #: ★ HFA 返回：用一个"两个 float 的结构体"的函数指针类型（与 `Room:GetCenterPos` 同先例）。
        self.assertRegex(api, r"struct EngineVector2Abi\s*\{[^}]*float x;[^}]*float y;")

    def test_the_evidence_and_the_pc_yardstick_are_recorded(self):
        """★ 常量段必须写明"PC 两个名字同一个 VA"、"符号是 snake_case 的盲点"、函数体做了什么、
        以及"为什么手写而不是数据行"。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        folded = constants.lower()
        for needle in ("0x741b00", "0x2b0ffc", "0xd10143ff", "get_shooting_input",
                       "entityplayer.md", "hfa", "s0"):
            self.assertIn(needle, folded, f"证据 {needle} 没有写进常量段")
        #: 盲点本身也要留痕（下一个接手的人按 snake_case 复查）。
        self.assertIn("snake_case", constants)
        #: 契约那两句（pressing / holding）。
        self.assertIn("pressing", constants)
        self.assertIn("holding", constants)
        #: `no_symbol` 与函数体的关键锚点（-4.0f 与 action 4/5/6）。
        self.assertIn("no_symbol", constants)
        self.assertIn("0x4a", folded)
        self.assertIn("-4.0f", constants)


if __name__ == "__main__":
    unittest.main()
