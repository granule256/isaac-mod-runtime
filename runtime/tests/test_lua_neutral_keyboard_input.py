import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import layered_lua_runtime_sources
except ImportError:
    from test_support import layered_lua_runtime_sources


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"


class LuaNeutralKeyboardInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-keyboard-")
        temporary = Path(cls.temporary.name)
        compatibility = temporary / "compatibility"
        compatibility.mkdir()
        (compatibility / "stdfloat").write_text(
            "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n"
        )
        harness = temporary / "lua_keyboard_harness.cpp"
        harness.write_text(
            r'''
#include "lua_runtime.hpp"
#include "domain/console/console_panel_state.hpp"
#include "game_file_reader.hpp"
#include "game_observer.hpp"

#include <cstring>

GameIsPausedObservation ObserveGameIsPaused(uintptr_t, uintptr_t) {
    return GameIsPausedObservation::ThunkUnavailable;
}
GameLevelStageObservation ReadCurrentGameLevelStage(uintptr_t, std::uint32_t*) {
    return GameLevelStageObservation::GameUnreadable;
}
GameIsGreedModeObservation ObserveGameIsGreedMode(uintptr_t, uintptr_t) {
    return GameIsGreedModeObservation::MethodUnavailable;
}
GameIsAscentObservation ObserveLevelIsAscent(uintptr_t, uintptr_t) { return GameIsAscentObservation::MethodUnavailable; }
GameItemPoolObservation ReadCurrentGameItemPool(uintptr_t, void**) {
    return GameItemPoolObservation::GameUnreadable;
}
GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {
    return GameRoomObservation::RoomUnreadable;
}
GameRoomObservation ReadCurrentGameRoomType(uintptr_t, std::uint32_t*) {
    return GameRoomObservation::RoomUnreadable;
}

// Test seam for the controller-input bindings: the Hook installation is what publishes the
// real `Manager::` trampolines, so the harness binds fakes and the Lua script asserts that the
// handlers call them with the arguments the PC API passes.
//
// ★ 2026-09-16 修正（这条断言原先写的是**错的调用约定**）：那三个绑定地址不是函数本体，而是
// 游戏自己的入口跳板 —— 它把 `x0` 换成 Manager 单例、把 `x3` 清零，然后尾调用真函数
// `(Manager*, u32 action, u32 controller, void* entity)`。也就是说**动作号在 x1、手柄序号在 x2**，
// 第一个参数是跳板要覆盖的占位。原先的假跳板按 `(action, controller)` 两个参数声明，等于把
// "动作号必须落在 x0"当成了契约，于是真机上任何按键都答"没按下"（0~27 号动作 × controller 0/1
// 全问一遍、玩家按遍所有键，一个都没触发）。证据：跳板字节 + 本项目 stage 88/89 自己的调用点
// `actionTriggered(manager, 动作号, 手柄序号, nullptr)`；新增的
// `test_lua_input_binding_abi.py` 专门钉这条约定。
// ★ 2026-09-30（批次 211）：假绑定改答 **controller == 1**（不再答 0）。
// 因为手柄号现在要先过 `pc_ns_input_device_map.hpp` 那张表：PC 的 `0` = **键盘**档，
// 在 Switch 上没有对应的输入设备（引擎设备表里 0 是触摸屏）⇒ 处理器**根本不问引擎**、直接答
// false/0.0（PC 上这两档同样是 false）。宿主 harness 里读不到引擎设备表 ⇒ `1..4` 原样透传 ⇒
// 用 `1` 当"模组眼里的第 1 台手柄"就能验"翻译之后确实问到引擎了"。
bool FakeIsActionPressed(void* /* 被跳板覆盖的 Manager* */, std::uint32_t action,
                         std::uint32_t controller) {
    return action == 3 && controller == 1;
}
bool FakeIsActionTriggered(void*, std::uint32_t action, std::uint32_t controller) {
    return action == 15 && controller == 1;
}
float FakeGetActionValue(void*, std::uint32_t action, std::uint32_t controller) {
    return (action == 3 && controller == 1) ? 0.5f : 0.0f;
}
namespace GameFileReader {
TextReadResult ReadTextFile(const Bindings&, const char*, u8*, std::size_t, std::size_t*) {
    return TextReadResult::OpenFailed;
}
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* script = nullptr;
    if (std::strcmp(argv[1], "neutral") == 0) {
        script = R"lua(
local mod = RegisterMod('Keyboard compatibility', 1)
local inputCalls = 0
mod:AddCallback(ModCallbacks.MC_INPUT_ACTION, function()
  inputCalls = inputCalls + 1
end)
mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function()
  if Keyboard.KEY_R ~= 82 or Keyboard.KEY_ENTER ~= 257 then error('keyboard constants') end
  -- ★ 2026-09-30（批次 218）：**16/17/18 三个名字在 Rep+ 变了**（原来这条写的是 AB/AB+ 的 16）。
  --   PC 契约 `tools/pc_enum_docs/ButtonAction.md`：repplus 档 16=ACTION_FULLSCREEN / 17=ACTION_MUTE / 18=ACTION_RESTART。
  --   判据与出处见 runtime/tests/test_lua_button_action_rep_plus.py（它逐行对文档）。
  if ButtonAction.ACTION_RESTART ~= 18 then error('action constant') end
  if ButtonAction.ACTION_FULLSCREEN ~= 16 then error('ACTION_FULLSCREEN must be 16 on Rep+') end
  if ButtonAction.ACTION_MUTE ~= 17 then error('ACTION_MUTE must be 17 on Rep+') end
  if InputHook.IS_ACTION_PRESSED ~= 0 then error('hook constant') end
  if Input.IsButtonTriggered(Keyboard.KEY_R, 0) ~= false then error('button trigger') end
  if Input.IsButtonPressed(Keyboard.KEY_R, 0) ~= false then error('button pressed') end
  if Input.GetButtonValue(Keyboard.KEY_R, 0) ~= 0 then error('button value') end
  -- The action queries are bound to real native trampolines on hardware; here they are bound
  -- to fakes, so these assertions prove the handler passes (action, controllerId) through.
  -- ★ 2026-09-20（批次 107）改写：`Input.IsActionTriggered` **不再问引擎那条"刚按下"**
  --   （真机上它永远是假 —— 见 api_deviation.cpp 的 0x09010004），而是问引擎的"按住"、
  --   再自己算上升沿。这里的假绑定对 (3,1) 答"按住" ⇒ **首次观察不算边沿** ⇒ false；
  --   完整的边沿往返（松开再按）在 test_lua_input_binding_abi.py 里跨两次脚本执行验。
  -- ★ 2026-09-30（批次 211）：手柄号先过 PC→NS 映射表 —— `0` 是 PC 的**键盘**档，
  --   Switch 上真值不存在（引擎设备表里 0 是触摸屏）⇒ 处理器不问引擎、直接 false/0.0。
  -- ★ 2026-09-30（批次 230）：动作号**也要过翻译表**（`input_action_map.hpp`）——
  --   这里特意用 **3（ACTION_DOWN）** 当样本：它在 PC 与 Switch 引擎里**同号**，
  --   所以本用例只管"调用约定 + 键盘档不落引擎"；"号要翻译"那件事由
  --   `test_input_action_translation.py` 与 `test_lua_input_binding_abi.py`（用 20 ⇒ 引擎 17）钉。
  if Input.IsActionTriggered(3, 1) ~= false then error('action trigger first observation') end
  if Input.IsActionTriggered(15, 1) ~= false then error('action trigger not held') end
  -- ★ 2026-10-06（批次 381）：A2 —— "按住"与"边沿"来自**同一次采样**。宿主里采样器读不到
  --   引擎（`EngineModuleBase()==0`）⇒ 这一帧的采样全是 false ⇒ `IsActionPressed(3,1)` 答 **false**。
  --   而假绑定 `FakeIsActionPressed` 对 (3,1) 答的是 **true** ⇒ 这条正好证明它**没有走"现查兜底"**、
  --   而是读了采样（这就是 A2 的判据）。调用约定（动作号落 x1、手柄号落 x2）由仍**现查**的
  --   `GetActionValue`（下面那条 0.5）钉住。
  if Input.IsActionPressed(3, 1) ~= false then error('A2: pressed must read the frame sample') end
  if Input.IsActionPressed(15, 1) ~= false then error('action pressed argument') end
  if Input.GetActionValue(3, 1) ~= 0.5 then error('action value') end
  if Input.GetActionValue(15, 1) ~= 0 then error('action value argument') end
  -- 键盘档（PC 的 controllerId 0）在 Switch 上没有真值 ⇒ 一律 false/0.0，**不许**落到引擎上。
  if Input.IsActionPressed(3, 0) ~= false then error('keyboard slot must not reach the engine') end
  if Input.GetActionValue(3, 0) ~= 0 then error('keyboard slot value') end
  if inputCalls ~= 0 then error('input callback dispatched') end
end)
)lua";
    } else if (std::strcmp(argv[1], "console_pause") == 0) {
        script = R"lua(
local mod=RegisterMod('Console pause',1)
__consoleRenders=0
__consoleUpdates=0
mod:AddCallback(ModCallbacks.MC_POST_UPDATE,function()
  __consoleUpdates=__consoleUpdates+1
  assert(Input.GetActionValue(3,1)==0.5,'restored input')
end)
mod:AddCallback(ModCallbacks.MC_POST_RENDER,function()
  __consoleRenders=__consoleRenders+1
  assert(Game():IsPaused()==true,'console pause visible to Lua')
  assert(Input.GetActionValue(3,1)==0,'console owns input')
end)
)lua";
    } else if (std::strcmp(argv[1], "input_only") == 0) {
        script = "local mod=RegisterMod('Input only',1); "
                 "mod:AddCallback(ModCallbacks.MC_INPUT_ACTION,function() error('must stay dormant') end)";
    } else if (std::strcmp(argv[1], "invalid") == 0) {
        script = "Input.IsButtonPressed(Keyboard.KEY_R)";
    } else {
        return 91;
    }
    LuaRuntime::SetInputBindings(reinterpret_cast<uintptr_t>(&FakeIsActionPressed),
                                 reinterpret_cast<uintptr_t>(&FakeIsActionTriggered),
                                 reinterpret_cast<uintptr_t>(&FakeGetActionValue));
    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@keyboard.lua");
    if (std::strcmp(argv[1], "invalid") == 0) {
        return result == LuaRuntime::LuaInitResult::ScriptRunFailed ? 0 : 1;
    }
    if (result != LuaRuntime::LuaInitResult::Success) return 2;
    if (std::strcmp(argv[1],"console_pause")==0) {
        LuaRuntime::SetGameBindings(123,456);
        isaac::runtime::console::g_ConsolePaused.store(1);
        isaac::runtime::console::g_ConsoleInputCaptured.store(1);
        LuaRuntime::DispatchPostUpdate();
        double updated=0;
        if(!LuaRuntime::ReadLuaGlobalNumber("__consoleUpdates",&updated) || updated!=0)return 4;
        LuaRuntime::DispatchPostRender(0x1000);
        double rendered=0;
        if(!LuaRuntime::ReadLuaGlobalNumber("__consoleRenders",&rendered) || rendered!=1 || LuaRuntime::TakeCallbackError())return 5;
        isaac::runtime::console::g_ConsolePaused.store(0);
        isaac::runtime::console::g_ConsoleInputCaptured.store(0);
    }
    LuaRuntime::DispatchPostUpdate();
    if(std::strcmp(argv[1],"console_pause")==0) {
        double updated=0;
        if(!LuaRuntime::ReadLuaGlobalNumber("__consoleUpdates",&updated) || updated!=1)return 6;
    }
    return LuaRuntime::TakeCallbackError() ? 3 : 0;
}
'''.lstrip()
        )
        lua_root = SOURCE / "third_party/lua-5.3.3/src"
        excluded = {"lua.c", "luac.c", "liolib.c", "loslib.c", "loadlib.c", "ldblib.c", "linit.c"}
        lua_objects = []
        for lua_source in sorted(lua_root.glob("*.c")):
            if lua_source.name in excluded:
                continue
            output = temporary / f"{lua_source.stem}.o"
            build = subprocess.run(
                ["cc", "-std=c99", "-w", "-DLUA_C89_NUMBERS", "-I", str(lua_root), "-c",
                 str(lua_source), "-o", str(output)], text=True, capture_output=True,
            )
            if build.returncode != 0:
                raise AssertionError(build.stdout + build.stderr)
            lua_objects.append(output)
        cls.harness = temporary / "lua_keyboard_harness"
        build = subprocess.run(
            ["c++", "-std=c++23", "-Wall", "-Wextra", "-Werror", "-DLUA_C89_NUMBERS",
             "-DEXL_LAYERED_RUNTIME=1", "-DEXL_LOAD_KIND=Module",
             "-DEXL_LOAD_KIND_ENUM=2", "-DEXL_PROGRAM_ID=0",
             "-I", str(compatibility), "-I", str(SOURCE), "-I", str(SOURCE.parent / "src"),
             "-I", str(lua_root), str(harness),
             *(str(path) for path in layered_lua_runtime_sources(SOURCE)),
             *map(str, lua_objects), "-o", str(cls.harness)],
            text=True, capture_output=True,
        )
        if build.returncode != 0:
            raise AssertionError(build.stdout + build.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario):
        result = subprocess.run([str(self.harness), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_neutral_keyboard_queries_allow_mod_loading_without_dispatching_input_callback(self):
        self.run_scenario("neutral")

    def test_neutral_keyboard_queries_reject_missing_controller_id(self):
        self.run_scenario("invalid")

    def test_console_pauses_updates_keeps_render_and_restores_input(self):
        self.run_scenario("console_pause")

    def test_input_only_mod_is_loaded_even_though_its_callback_stays_dormant(self):
        self.run_scenario("input_only")

    def test_input_dispatch_exists_only_through_the_documented_entry_and_never_hooks_processing(self):
        """★ 2026-10-07（批次 392）**翻向**：这条原来叫 `test_runtime_has_no_native_input_dispatch_or_hook`，
        钉的是"运行时**没有**原生输入派发、也没有挂钩"。

        那条断言在**批次 390** 就作废了（当时漏跑这个门禁 ⇒ 存量红）——`MC_INPUT_ACTION` 现在是
        **真派发**（用户报的"按住 `-` 小地图不放大"要它：`minimapi` 只挂在这一条回调上）。
        翻向之后这条门禁保住原来那份价值，改成钉现在的架构：

        * `DispatchInputAction` 必须**在**（谁把它删了、改名了，这里先红）；
        * 输入这条路**不许出现 `ProcessInput`**：我们只在 `KAGE::Input::ManagerBase` 的三条**查询**
          入口上挂中继（`hook_manager.cpp` 的 `ISAAC_RUNTIME_INPUT_ACTION_RELAY`），
          绝不挂引擎本体那些 `*::ProcessInput` 处理函数 —— 挂那里等于把引擎的输入流程整体接管，
          而不是只回答"某次查询的结果能不能被覆盖"。
        """
        source = (SOURCE / "lua_runtime.cpp").read_text()
        self.assertIn(
            "DispatchInputAction",
            source,
            "`MC_INPUT_ACTION` 的派发入口（批次 390）不见了 —— minimapi 的放大又要失效。",
        )
        self.assertNotIn(
            "ProcessInput",
            source,
            "`lua_runtime.cpp` 里出现了 `ProcessInput` —— 我们只挂「查询」入口，不碰引擎的输入处理函数。",
        )


if __name__ == "__main__":
    unittest.main()
