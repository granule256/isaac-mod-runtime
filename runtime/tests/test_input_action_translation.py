"""模组（PC）**动作号** → Switch 引擎**内部**动作号：批次 230（2026-09-30）。

## 这个测试解决什么问题

中文版 MCM 里"摇杆向下推不能正常向下选择"。根因不是手感、不是设备表，而是**两张编号表不是同一张**：

* 模组写的是 PC 的 `ButtonAction`：`ACTION_MENULEFT = 20`、`ACTION_MENUDOWN = 23`；
* Switch 引擎的内部表把 **17..20 当"菜单左/右/上/下"**（`ACTION_MENULEFT` 在引擎里是 **17**）；
* 我们原来把模组给的号**原样**递给引擎 ⇒ 推"下"时引擎把 `ACTION_MENULEFT(20)` 也答成"按住"
  ⇒ MCM 的导航链（`modconfig.lua:1651-1663`：下 → 上 → 右 → **左**，后判覆盖前判）把"下"改写成"左"。
  ⇒ 用户看到的就是"向下推没用（像是往左）"。

本文件钉住三件事：

1. **表的内容**（`runtime/src/interfaces/lua/input_action_map.hpp`）：逐行取值 + 0..15 同号 +
   所有目标都在 Switch 引擎的 24 个内部号之内（或明确标"Switch 上没有"）；
2. **消费者视角**（真跑一份宿主夹具）：按真机读数"推某个方向时引擎把哪几个内部号答成按住"，
   算出**照 MCM 那样**读这套 API 会得到哪个方向 —— 必须**只**得到用户推的那个方向。
   这一条才是"用户会不会再看到那个缺陷"的判据；顺手把"不翻译（= 修之前）会得到 LEFT"
   也算一遍，证明这条用例真的能抓到那个缺陷（否则就是把门禁写成了假的）。
3. ★ **反表（引擎内部号 → 模组/PC 号）+ 互逆性**（批次 393，2026-10-07）：`MC_INPUT_ACTION`
   回调的 `buttonAction` 实参必须给 PC 口径的号 —— 引擎内部 `16..23` 对应 PC `19..26`
   （PC 的 16/17/18 在 Switch 上没有对应动作 ⇒ 那一段整体错开 3）。判据 = 反表逐行 +
   "引擎 0..23 每一条都能被翻译回原值"。

## 真值来源（都能重跑）

* 设备层/管理器层不翻译：`tools/nro_disasm.py 0x4F76A8` / `0x4F9920`；
* 引擎自己的菜单用 17..20：`tools/nro_disasm.py 0x40D770`（19 ⇒ 选中行 -1、20 ⇒ +1）；
* 默认按键表：`IsaacRepentance::s_ButtonMap @0xa38300`（17..20 ← 十字键四向 + 左摇杆；
  21 ← L、22 ← R、23 ← X、16 ← "+"）；
* 16 = `JOINMULTIPLAYER`：`tools/nro_disasm.py 0x43E700`（`SpawnCoPlayer`）；
* 真机读数：`dist/gdb-read-20260930-1633*-snapshot.txt`（推左 ⇒ 0 与 17、推右 ⇒ 1 与 18、
  推下 ⇒ 3 与 20）。
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LUA_DIR = ROOT / "runtime" / "src" / "interfaces" / "lua"
INPUT_API = LUA_DIR / "input_api.cpp"
ACTION_MAP = LUA_DIR / "input_action_map.hpp"
DEVIATION = LUA_DIR / "api_deviation.cpp"

#: 逐行钉住的翻译表（模组号 → 引擎内部号；`None` = Switch 上没有这个动作）。
EXPECTED = {
    0: 0, 1: 1, 2: 2, 3: 3,                    # LEFT / RIGHT / UP / DOWN
    4: 4, 5: 5, 6: 6, 7: 7,                    # SHOOT*
    8: 8, 9: 9, 10: 10, 11: 11,                # BOMB / ITEM / PILLCARD / DROP
    12: 12, 13: 13, 14: 14, 15: 15,            # PAUSE / MAP / MENUCONFIRM / MENUBACK
    16: None, 17: None, 18: None,              # FULLSCREEN / MUTE / RESTART：Switch 上没有
    19: 16,                                    # JOINMULTIPLAYER（引擎 16，见 SpawnCoPlayer）
    20: 17, 21: 18, 22: 19, 23: 20,            # MENU LEFT / RIGHT / UP / DOWN（用户可见缺陷在这里）
    24: 21, 25: 22,                            # MENULB / MENURB（Switch = L / R）
    26: 23, 28: 23, 29: 23,                    # MENUTAB 的三种候选写法（Switch = X）
    27: None, 30: None, 31: None, 32: None,    # MENURT / EMOTES / 未定义 / CONSOLE
}

#: ★ 批次 393：**反表**（引擎内部号 → 模组/PC 号）—— `MC_INPUT_ACTION` 的 `buttonAction` 用这个方向。
#: 0..15 同号；16..23 = PC 19..26（PC 的 16/17/18 在 Switch 上没有 ⇒ 整段 `+3`）。
#: 引擎 23 在正向表里有三个 PC 写法（26/28/29，都是 MENUTAB 的候选号）⇒ 反表取**正写 26**
#: （与 `kButtonActionConstants` 里的 26 = MENUTAB 一致，模组写 `ButtonAction.ACTION_MENUTAB` 才能比中）。
EXPECTED_REVERSE = {
    0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7,
    8: 8, 9: 9, 10: 10, 11: 11, 12: 12, 13: 13, 14: 14, 15: 15,
    16: 19,                                    # JOINMULTIPLAYER（"+"）
    17: 20, 18: 21, 19: 22, 20: 23,            # MENU 四向（引擎 17..20 ↔ PC 20..23）
    21: 24, 22: 25, 23: 26,                    # Switch 上的 L / R / X
}

#: 真机读数：推某个方向时引擎把哪些**内部**号答成"按住"（十字键四向 + 左摇杆/菜单四向）。
ENGINE_PRESSED_WHEN_PUSHED = {
    "LEFT": (0, 17),
    "RIGHT": (1, 18),
    "UP": (2, 19),
    "DOWN": (3, 20),
}

#: MCM 的方向组（`analysis/mod-corpus/isaac-mod-config-menu/scripts/modconfig.lua:1294-1297`）。
MCM_GROUPS = {
    "DOWN": (3, 7, 23),
    "UP": (2, 6, 22),
    "RIGHT": (1, 5, 21),
    "LEFT": (0, 4, 20),
}
#: MCM 的判定顺序（后判覆盖前判：`modconfig.lua:1651-1663`）。
MCM_ORDER = ("DOWN", "UP", "RIGHT", "LEFT")


HARNESS = r'''
#include "input_action_map.hpp"

#include <cstdint>
#include <cstdio>
#include <string>

using isaac::runtime::TranslateLuaActionToEngineAction;
using isaac::runtime::kNoEngineAction;
using isaac::runtime::kSwitchEngineActionCount;

namespace {

int failures = 0;

void Check(bool condition, const char* label) {
    if (!condition) {
        std::printf("FAIL %s\n", label);
        ++failures;
    }
}

// 真机读数（`dist/gdb-read-20260930-1633*-snapshot.txt`）：推某个方向时引擎答"按住"的内部号。
std::uint32_t PushedMask(const char* direction) {
    const unsigned char a = static_cast<unsigned char>(direction[0]);
    if (a == 'L') { return (1u << 0) | (1u << 17); }   // 左：十字键左 + 左摇杆 + 菜单左
    if (a == 'R') { return (1u << 1) | (1u << 18); }
    if (a == 'U') { return (1u << 2) | (1u << 19); }
    return (1u << 3) | (1u << 20);                     // 下
}

// "模组这一问会不会得到 true"：先翻译，再问"引擎此刻对那个内部号答不答按住"。
bool LuaActionPressed(std::uint32_t lua_action, std::uint32_t engine_pushed) {
    const std::uint32_t engine_action = TranslateLuaActionToEngineAction(lua_action);
    if (engine_action == kNoEngineAction) {
        return false;                                  // Switch 上没有这个动作 ⇒ 直接 false
    }
    return (engine_pushed & (1u << engine_action)) != 0u;
}

// MCM 的导航结果（`modconfig.lua:1651-1663`：下 → 上 → 右 → 左，后判覆盖前判）。
const char* McmNavigation(std::uint32_t engine_pushed) {
    static const std::uint32_t kDown[3] = {3, 7, 23};
    static const std::uint32_t kUp[3] = {2, 6, 22};
    static const std::uint32_t kRight[3] = {1, 5, 21};
    static const std::uint32_t kLeft[3] = {0, 4, 20};
    const char* pressing = "NONE";
    for (const std::uint32_t action : kDown) {
        if (LuaActionPressed(action, engine_pushed)) { pressing = "DOWN"; }
    }
    for (const std::uint32_t action : kUp) {
        if (LuaActionPressed(action, engine_pushed)) { pressing = "UP"; }
    }
    for (const std::uint32_t action : kRight) {
        if (LuaActionPressed(action, engine_pushed)) { pressing = "RIGHT"; }
    }
    for (const std::uint32_t action : kLeft) {
        if (LuaActionPressed(action, engine_pushed)) { pressing = "LEFT"; }
    }
    return pressing;
}

// 修之前的行为（原样把模组号递给引擎）—— 只用来证明"这条用例真的抓得住那个缺陷"。
const char* McmNavigationWithoutTranslation(std::uint32_t engine_pushed) {
    static const std::uint32_t kDown[3] = {3, 7, 23};
    static const std::uint32_t kUp[3] = {2, 6, 22};
    static const std::uint32_t kRight[3] = {1, 5, 21};
    static const std::uint32_t kLeft[3] = {0, 4, 20};
    const char* pressing = "NONE";
    for (const std::uint32_t action : kDown) {
        if ((engine_pushed & (1u << action)) != 0u) { pressing = "DOWN"; }
    }
    for (const std::uint32_t action : kUp) {
        if ((engine_pushed & (1u << action)) != 0u) { pressing = "UP"; }
    }
    for (const std::uint32_t action : kRight) {
        if ((engine_pushed & (1u << action)) != 0u) { pressing = "RIGHT"; }
    }
    for (const std::uint32_t action : kLeft) {
        if ((engine_pushed & (1u << action)) != 0u) { pressing = "LEFT"; }
    }
    return pressing;
}

}  // namespace

int main() {
    // ① 表本身：逐行取值（值写错一位就会"按了这个键触发别的功能"，且不报错）。
    const std::uint32_t down = PushedMask("D");
    const std::uint32_t left = PushedMask("L");
    const std::uint32_t right = PushedMask("R");
    const std::uint32_t up = PushedMask("U");

    // ② 0..15 **同号**（引擎自己的代码在 8/10/14/15/12 上都按这个语义用）。
    for (std::uint32_t action = 0; action <= 15u; ++action) {
        Check(TranslateLuaActionToEngineAction(action) == action, "0..15 必须同号");
    }

    // ③ 用户可见缺陷那四行（硬证据：引擎菜单代码 + 默认按键表 + 真机读数）。
    Check(TranslateLuaActionToEngineAction(20) == 17, "MENULEFT(20) → 引擎 17");
    Check(TranslateLuaActionToEngineAction(21) == 18, "MENURIGHT(21) → 引擎 18");
    Check(TranslateLuaActionToEngineAction(22) == 19, "MENUUP(22) → 引擎 19");
    Check(TranslateLuaActionToEngineAction(23) == 20, "MENUDOWN(23) → 引擎 20");
    Check(TranslateLuaActionToEngineAction(19) == 16, "JOINMULTIPLAYER(19) → 引擎 16");

    // ④ Switch 上没有的动作必须**明确**标出来（不许"碰巧"被设备层越界判假）。
    for (const std::uint32_t absent : {16u, 17u, 18u, 27u, 30u, 31u, 32u}) {
        Check(TranslateLuaActionToEngineAction(absent) == kNoEngineAction,
              "这些号在 Switch 上没有对应动作");
    }
    // 越界（33 及以上）同样是"没有"。
    Check(TranslateLuaActionToEngineAction(33) == kNoEngineAction, "越界号必须是 kNoEngineAction");
    Check(TranslateLuaActionToEngineAction(0xFFFFFFFFu) == kNoEngineAction,
          "0xFFFFFFFF 必须是 kNoEngineAction（别与设备层哨兵混用）");

    // ⑤ 所有目标号都必须落在引擎真的有的 24 个内部号之内。
    for (std::uint32_t action = 0; action < 33u; ++action) {
        const std::uint32_t engine_action = TranslateLuaActionToEngineAction(action);
        if (engine_action != kNoEngineAction) {
            Check(engine_action < kSwitchEngineActionCount, "目标号必须 < 24（设备层越界判据）");
        }
    }

    // ⑥ ★ 消费者视角：照 MCM 那样读，必须只得到"用户推的那个方向"。
    Check(std::string(McmNavigation(down)) == "DOWN", "推下 ⇒ MCM 得到 DOWN");
    Check(std::string(McmNavigation(up)) == "UP", "推上 ⇒ MCM 得到 UP");
    Check(std::string(McmNavigation(left)) == "LEFT", "推左 ⇒ MCM 得到 LEFT");
    Check(std::string(McmNavigation(right)) == "RIGHT", "推右 ⇒ MCM 得到 RIGHT");

    // ⑦ 具体到那一格：推"下"时 `ACTION_MENULEFT(20)` 必须**为假**、`ACTION_MENUDOWN(23)` 必须为真。
    Check(!LuaActionPressed(20, down), "推下时 MENULEFT 必须为假（缺陷就是它误真）");
    Check(LuaActionPressed(23, down), "推下时 MENUDOWN 必须为真");
    Check(LuaActionPressed(20, left), "推左时 MENULEFT 必须为真");

    // ⑧ 反向自证：**不翻译**（= 修之前）时推"下"会被读成 LEFT —— 这条用例确实抓得住那个缺陷。
    Check(std::string(McmNavigationWithoutTranslation(down)) == "LEFT",
          "不翻译时推下会被读成 LEFT（证明本用例能抓到缺陷，不是假门禁）");

    if (failures != 0) {
        std::printf("INPUT_ACTION_MAP_CHECKS_FAILED %d\n", failures);
        return 1;
    }
    std::printf("INPUT_ACTION_MAP_CHECKS_PASSED\n");
    return 0;
}
'''

#: 逐行取值那一段用 C++ 侧的字面量再钉一遍（Python 侧的 EXPECTED 是"人读的清单"，
#: 这里生成一份等价的断言，任何一行被改都会红）。
HARNESS_TABLE = r'''
#include "input_action_map.hpp"

#include <cstdint>
#include <cstdio>

using isaac::runtime::TranslateLuaActionToEngineAction;
using isaac::runtime::kNoEngineAction;

namespace {

int failures = 0;

void Expect(std::uint32_t lua_action, std::uint32_t expected) {
    const std::uint32_t actual = TranslateLuaActionToEngineAction(lua_action);
    if (actual != expected) {
        std::printf("FAIL action %u: expected %u, got %u\n", lua_action, expected, actual);
        ++failures;
    }
}

}  // namespace

int main() {
'''

#: ★ 批次 393：反表的宿主夹具骨架（逐行 `Check` 由 Python 侧生成，见
#: `ActionMapReverseTests.test_every_reverse_row_matches_the_pinned_table`）。
HARNESS_REVERSE = r'''
#include "input_action_map.hpp"

#include <cstdint>
#include <cstdio>

using isaac::runtime::TranslateEngineActionToLuaAction;
using isaac::runtime::TranslateLuaActionToEngineAction;
using isaac::runtime::kSwitchEngineActionCount;

namespace {

int failures = 0;

void Check(bool condition, const char* label) {
    if (!condition) {
        std::printf("FAIL %s\n", label);
        ++failures;
    }
}

}  // namespace

int main() {
'''

#: 反表的性质断言（**比逐行表更强**）：引擎 0..23 每一条都必须能翻译回原值 ——
#: 这是"回调与查询共用同一条真值源"的判据（哪天有人只改一边，这里立刻红）。
REVERSE_PROPERTIES = r'''
    // 互逆性：引擎侧 0..23 全覆盖（一个都不能漏）。
    for (std::uint32_t engine = 0; engine < kSwitchEngineActionCount; ++engine) {
        const std::uint32_t lua = TranslateEngineActionToLuaAction(engine);
        Check(TranslateLuaActionToEngineAction(lua) == engine,
              "反表必须与正表互逆（引擎 0..23 全覆盖）");
    }
    // 越界号原样透传：引擎只会轮询 0..23（设备动作数 24）⇒ 越界说明调用方不是引擎，
    // 这时**不许编造**一个"看起来合法"的 PC 号。
    Check(TranslateEngineActionToLuaAction(kSwitchEngineActionCount) == kSwitchEngineActionCount,
          "越界号必须原样透传");
'''

REVERSE_FOOTER = '\n    std::printf("INPUT_ACTION_MAP_REVERSE_OK\\n");\n    return 0;\n}\n'

LUA_RUNTIME_SOURCE = ROOT / "runtime" / "source" / "lua_runtime.cpp"


def host_compiler() -> str | None:
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return found
    return None


def compile_and_run(body: str, includes: list[Path]) -> str:
    """编一份宿主夹具并跑它；返回 stdout（编译失败时用断言把编译器输出带出来）。"""
    compiler = host_compiler()
    if compiler is None:
        raise unittest.SkipTest("宿主机没有 C++ 编译器")
    with tempfile.TemporaryDirectory(prefix="isaac-input-action-map-") as directory:
        workdir = Path(directory)
        source = workdir / "harness.cpp"
        source.write_text(body.lstrip(), encoding="utf-8")
        binary = workdir / "harness"
        command = [compiler, "-std=c++23", "-Wall", "-Wextra", "-Werror"]
        for include in includes:
            command += ["-I", str(include)]
        command += [str(source), "-o", str(binary)]
        build = subprocess.run(command, text=True, capture_output=True)
        if build.returncode != 0:
            raise AssertionError(build.stdout + build.stderr)
        run = subprocess.run([str(binary)], text=True, capture_output=True)
        if run.returncode != 0:
            raise AssertionError(run.stdout + run.stderr)
        return run.stdout


class ActionMapTableTests(unittest.TestCase):
    """表本身：逐行取值（值写错一位就是"按了这个键触发别的功能"，不报错、不崩）。"""

    def test_every_row_matches_the_pinned_table(self):
        body = [HARNESS_TABLE]
        for lua_action, engine_action in sorted(EXPECTED.items()):
            expected = "kNoEngineAction" if engine_action is None else f"{engine_action}u"
            body.append(f"    Expect({lua_action}u, {expected});\n")
        body.append('\n    std::printf("INPUT_ACTION_MAP_TABLE_OK\\n");\n    return 0;\n}\n')
        stdout = compile_and_run("".join(body), [LUA_DIR])
        self.assertIn("INPUT_ACTION_MAP_TABLE_OK", stdout)

    def test_the_header_documents_its_evidence(self):
        """表头必须自己写着证据（换版本重建时，这是唯一能复核的东西）。

        这一条不是形式主义：本项目已经出现过"注释里有、门禁里没有 ⇒ 谁也不知道"的坑
        （`tools/png_to_pcx.py` 那条），所以证据标记必须钉住。
        """
        text = ACTION_MAP.read_text(encoding="utf-8")
        for marker in (
            "0x4F76A8",        # 设备层 IsActionPressed（动作号直接作下标）
            "0x4F9920",        # 管理器层（不翻译）
            "0x40D770",        # Menu_Game::Update（19=上、20=下）
            "s_ButtonMap",     # 默认按键表（17..20 ← 十字键四向 + 左摇杆）
            "SpawnCoPlayer",   # 16 = JOINMULTIPLAYER
            "kSwitchEngineActionCount",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)
        # 24..29 那一段契约页自相矛盾的取舍必须写明（不许悄悄猜）。
        self.assertIn("矛盾", text)
        self.assertIn("pc_enum_docs/ButtonAction.md", text)


class ActionMapReverseTests(unittest.TestCase):
    """★ 批次 393（2026-10-07）：反表 —— `MC_INPUT_ACTION` 的 `buttonAction` 实参。

    为什么必须钉：引擎轮询时给我们的是**内部号**，而 PC 契约里这个实参是**模组的
    `ButtonAction` 值**。两张表只在 0..15 同号（`ACTION_MAP=13` 恰好同号 ⇒ minimapi 从来没被咬到，
    这也是这个错一直没人发现的原因），`16..23` 那段整体错开 3 ⇒ **比较动作号的模组会判错**
    （真消费者形状：`InputHelper.HandleForceActionPressed` 的 `forcingActionPressed[ci][buttonAction]`）。
    """

    def test_every_reverse_row_matches_the_pinned_table(self):
        body = [HARNESS_REVERSE]
        for engine_action, lua_action in sorted(EXPECTED_REVERSE.items()):
            body.append(
                f"    Check(TranslateEngineActionToLuaAction({engine_action}u) == {lua_action}u,\n"
                f'          "engine {engine_action} -> PC {lua_action}");\n'
            )
        body.append(REVERSE_PROPERTIES)
        body.append(REVERSE_FOOTER)
        stdout = compile_and_run("".join(body), [LUA_DIR])
        self.assertIn("INPUT_ACTION_MAP_REVERSE_OK", stdout)

    def test_the_reverse_table_covers_every_engine_action(self):
        """逐行表必须**写满**引擎的 24 个内部号。

        漏一行的后果不是崩溃，而是那个号在回调里被**原样透传**（模组拿到引擎内部号、
        悄悄比较失败）—— 正是这一批要修的那类"看起来正常"的错。
        """
        self.assertEqual(sorted(EXPECTED_REVERSE), list(range(24)))
        text = ACTION_MAP.read_text(encoding="utf-8")
        self.assertIn("kEngineActionToLuaAction[kSwitchEngineActionCount]", text)


class ActionMapConsumerTests(unittest.TestCase):
    """消费者视角：照 MCM 那样读这套 API，必须只得到"用户推的那个方向"。"""

    def test_pushing_a_direction_never_reads_as_another_direction(self):
        stdout = compile_and_run(HARNESS, [LUA_DIR])
        self.assertIn("INPUT_ACTION_MAP_CHECKS_PASSED", stdout)


class ActionMapWiringTests(unittest.TestCase):
    """接线可见性（文本）。**不验行为** —— 这一半只保证"三条入口都过了这张表"。"""

    @classmethod
    def setUpClass(cls):
        cls.input_api = INPUT_API.read_text(encoding="utf-8")
        cls.deviation = DEVIATION.read_text(encoding="utf-8")

    def _handler(self, signature: str) -> str:
        text = self.input_api[self.input_api.index(signature):]
        return text[:text.index("\n}\n")]

    def test_all_three_entry_points_translate_the_action(self):
        for signature in (
            "int InputIsActionTriggered(lua_State* state) {",
            "int InputIsActionPressed(lua_State* state) {",
            "int InputGetActionValue(lua_State* state) {",
        ):
            with self.subTest(signature=signature):
                handler = self._handler(signature)
                self.assertIn("TranslateActionForEngine(", handler)

    def test_the_engine_is_asked_with_the_translated_code(self):
        """★ 要害：递给引擎的必须是**翻译后**的号。

        这一条抓的是"改了一半"：翻译算了但没用在查询上（行为与修之前一模一样，而且看不出来）。

        ★ 已随批次 381 更新（2026-10-06）：`Input.IsActionTriggered` 改成"帧上采样 + 纯读"
        （`runtime/source/input_edge.hpp` 第五节）之后**不再自己现查引擎** ⇒ 它身上不再有
        "递给引擎的号"这句话；**递动作号给引擎的唯一地方变成了采样器 `SampleInputFrame`**
        ⇒ 断言改指向那里（比原来更强：钉住的正是整批要害的那一处）。
        `IsActionPressed` / `GetActionValue` 两条仍走现查，断言照旧。
        """
        sample = self._handler("void SampleInputFrame(std::uint32_t frame) noexcept {")
        self.assertIn("TranslateLuaActionToEngineAction(code)", sample)
        self.assertIn("engineAction", sample)
        self.assertIn("actionQuery(", sample)
        for signature in ("int InputIsActionPressed(lua_State* state) {",):
            with self.subTest(signature=signature):
                handler = self._handler(signature)
                self.assertIn("query(nullptr, engine_action", handler)
                self.assertNotIn("query(nullptr, code", handler)
        value = self._handler("int InputGetActionValue(lua_State* state) {")
        self.assertIn("query(nullptr, engine_action", value)

    def test_absent_actions_never_reach_the_engine(self):
        """Switch 上没有的动作号必须**在这里就答 false / 0**（不许拿哨兵去问引擎）。

        ★ 已随批次 381 更新（2026-10-06）：采样器是**唯一**把动作号递给引擎的地方 ⇒
        守卫钉在它身上（`engineAction == kNoEngineAction` 就 `continue`，绝不把哨兵递给引擎）；
        `IsActionTriggered` 改成纯读之后不再递引擎，`IsActionPressed` 仍走守卫。
        """
        handler = self._handler("std::uint32_t TranslateActionForEngine(std::uint32_t lua_action) noexcept {")
        self.assertIn("kNoEngineAction", handler)
        sample = self._handler("void SampleInputFrame(std::uint32_t frame) noexcept {")
        self.assertIn("engineAction == kNoEngineAction", sample)
        with self.subTest(signature="int InputIsActionPressed(lua_State* state) {"):
            self.assertIn("engine_action != kNoEngineAction",
                          self._handler("int InputIsActionPressed(lua_State* state) {"))

    def test_the_snapshot_probe_still_asks_raw_numbers(self):
        """★ 普查探针**必须继续问原始内部号**（它回答的是"引擎自己怎么看"，批次 222 就靠它查出错位）。"""
        handler = self._handler("void RefreshInputSnapshot() noexcept {")
        self.assertIn("actionQuery(isaac::runtime::engine_memory::AsObject(manager), action,",
                      handler)
        self.assertNotIn("TranslateActionForEngine(", handler)

    def test_the_users_veto_is_respected(self):
        """用户裁定（2026-09-30）：**不许在转发层"拦掉某个号"来掩盖症状**。

        本批的做法是"把两个编号空间对上"（每个号都有出处），不是"见到 ≥18 就吞掉"。
        这里钉住没有任何"按数值门槛过滤动作"的写法。
        """
        for banned in ("code >= 18", "code >= 20", "action >= 18", "code > 23", "code >= 0x12"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, self.input_api)

    def test_the_translation_is_registered_in_the_deviation_ledger(self):
        """动作号翻译改变了"我们交给引擎的号"，必须在偏离台账里写明（本项目对"口径差异"的硬要求）。"""
        entry = self.deviation[self.deviation.index("{0x09010004,"):]
        entry = entry[:entry.index("},\n")]
        self.assertIn("动作号", entry)
        self.assertIn("input_action_map.hpp", entry)
        self.assertIn("判据：runtime/tests/test_input_action_translation.py", entry)

    def test_the_input_callback_hands_the_pc_number_to_mods(self):
        """★★ 批次 393 的要害：`MC_INPUT_ACTION` 派发时 `buttonAction` 必须是**翻译后**的 PC 号。

        抓的是"反表写了但没接到派发上"—— 那种情况下行为与修之前一模一样，读数也看不出来，
        只有这条文本断言能抓住。
        """
        runtime = LUA_RUNTIME_SOURCE.read_text(encoding="utf-8")
        start = runtime.index("InputActionOutcome DispatchInputAction(")
        handler = runtime[start : runtime.index("\n}\n", start)]
        self.assertIn("TranslateEngineActionToLuaAction(action)", handler,
                      "`DispatchInputAction` 又把**引擎内部号**当 `buttonAction` 递给模组了。")
        self.assertNotIn("AddInteger(static_cast<std::int64_t>(action))", handler,
                         "派发点还留着「直接把引擎内部号压进去」的旧写法。")

    def test_the_reverse_translation_comes_from_the_same_truth_source(self):
        """反表必须来自 `input_action_map.hpp`（与正向表同一条真值源），不许在派发点现编一张。"""
        runtime = LUA_RUNTIME_SOURCE.read_text(encoding="utf-8")
        self.assertIn("interfaces/lua/input_action_map.hpp", runtime)


if __name__ == "__main__":
    unittest.main()
