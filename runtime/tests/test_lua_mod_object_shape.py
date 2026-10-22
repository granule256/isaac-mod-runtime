"""`RegisterMod` 返回的是 **table**（PC 形态）—— 批次 216，2026-09-30。

## 为什么单开一条门禁

我们的 `RegisterMod` 以前返回 **userdata**，而 PC 返回 **table**（`GlobalFunctions.md:101`：
「Returns a table which acts the [Mod Reference](ModReference.md).」）。这条偏差平时看不出来，
**一旦有模组按 PC 的形态写就当场炸**：

* 中文版 MCM（工坊 2494192799）`scripts/customcallbacks.lua:161`：
  `if type(mod) ~= "table" then error("CustomCallbackHelper.AddCallback Error: No valid mod
  reference provided") end` —— 而 `savehelper.lua:89` 的 `SaveHelper.Mod` 正是 `RegisterMod(...)`，
  于是**加载期脚本失败**（真机读数：清单安装结果字 = 21 = `ScriptRunFailed`）⇒ 它的回调一条都没登记
  ⇒ **菜单打不开**。
* MinimapAPI `scripts/minimapapi/main.lua:1315`（另一个毫不相干的作者）：
  `if type(modtable) == "table" and modtable.Name and modtable.AddCallback then`。

⇒ 两处独立佐证 + 文档三条互证 = PC 的 Mod 对象是**带 `Name` 变量与那些方法的表**。

## 这条门禁钉什么

1. `type(RegisterMod(...)) == "table"`，且 `mod.Name` 就是传进去的名字（PC 的 `Name` 变量）；
2. 七个方法（`AddCallback`/`AddPriorityCallback`/`RemoveCallback`/`HasData`/`SaveData`/`LoadData`/
   `RemoveData`）都能从 mod 对象上取到、并且 `mod:Method(...)` 仍然可用；
3. **照中文版 MCM 那段写法逐句复刻**（`type` 检查 → 往 mod 身上加方法 → 调用它）不许报错 ——
   这一条就是"菜单打不开"那个事故的回归判据；
4. 模组往自己身上写字段（`mod.foo = 1`）可读可写，而**内部句柄对 `pairs()` 不可见**
   （表里只应有 `Name` 与模组自己写的东西 —— 我们塞进元表的 `__handle` 不该漏出来）；
5. `mod:AddCallback(...)` 登记的归属仍按**这个 Mod 对象自己**算：两个 Mod 各登记一条，
   两条都派发且 `self` 各是**自己那张表**（表形态没把"多模组归属"搞坏）；
6. `Isaac.GetCallbacks(name)` 的条目里 `Mod` 仍是**同一个** mod 对象。
"""

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


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "game_file_reader.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

GameIsPausedObservation ObserveGameIsPaused(uintptr_t, uintptr_t) {
    return GameIsPausedObservation::ThunkUnavailable;
}
GameLevelStageObservation ReadCurrentGameLevelStage(uintptr_t, std::uint32_t*) {
    return GameLevelStageObservation::GameUnreadable;
}
GameIsGreedModeObservation ObserveGameIsGreedMode(uintptr_t, uintptr_t) {
    return GameIsGreedModeObservation::MethodUnavailable;
}
GameIsAscentObservation ObserveLevelIsAscent(uintptr_t, uintptr_t) {
    return GameIsAscentObservation::MethodUnavailable;
}
GameItemPoolObservation ReadCurrentGameItemPool(uintptr_t, void**) {
    return GameItemPoolObservation::GameUnreadable;
}
GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {
    return GameRoomObservation::RoomUnreadable;
}
GameRoomObservation ReadCurrentGameRoomType(uintptr_t, std::uint32_t*) {
    return GameRoomObservation::RoomUnreadable;
}
namespace GameFileReader {
TextReadResult ReadTextFile(const Bindings&, const char*, u8*, std::size_t, std::size_t*) {
    return TextReadResult::OpenFailed;
}
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const std::string scenario = argv[1];
    std::string script;
    if (scenario == "shape") {
        script = R"lua(
local mod = RegisterMod('Probe', 1)
if type(mod) ~= 'table' then error('RegisterMod must return a table, got ' .. type(mod)) end
if mod.Name ~= 'Probe' then error('mod.Name must be the registered name, got ' .. tostring(mod.Name)) end
for _, method in ipairs({'AddCallback', 'AddPriorityCallback', 'RemoveCallback', 'HasData',
                         'SaveData', 'LoadData', 'RemoveData'}) do
  if type(mod[method]) ~= 'function' then
    error('mod.' .. method .. ' must be a function, got ' .. type(mod[method]))
  end
end
-- 模组往自己身上写字段（PC 用 table 的理由）
mod.myField = 41
if mod.myField ~= 41 then error('a mod must be able to store its own fields') end
-- 内部句柄不许漏出来：表里只应有 Name 与自己写的那个键
local keys = {}
for key in pairs(mod) do keys[#keys + 1] = tostring(key) end
table.sort(keys)
if #keys ~= 2 or keys[1] ~= 'Name' or keys[2] ~= 'myField' then
  error('the mod table must expose only its own fields, got: ' .. table.concat(keys, ','))
end
-- `InitializeFromBuffer` 会核对"至少登记了一个 MC_POST_UPDATE"（结果码 6 = 缺它）
mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function() end)
print('SHAPE_OK')
)lua";
    } else if (scenario == "mcm_pattern") {
        // ★ 逐句复刻中文版 MCM 的 customcallbacks.lua：合法性检查 + 往 mod 身上加方法 + 调用它。
        // 事故就是这段的第一行 `type(mod) ~= "table"` 炸掉的（加载期 ⇒ 整个模组回调全没登记）。
        script = R"lua(
local function AddCustomCallbackHelper(mod, callbackId, fn)
  if type(mod) ~= 'table' then
    error('CustomCallbackHelper.AddCallback Error: No valid mod reference provided', 3)
  end
  if type(callbackId) ~= 'number' then
    error('CustomCallbackHelper.AddCallback Error: No valid callback ID provided', 3)
  end
  if type(fn) ~= 'function' then
    error('CustomCallbackHelper.AddCallback Error: No valid callback function provided', 3)
  end
  if not mod.AddCustomCallback then
    mod.AddCustomCallback = function(self, id, callback)
      return AddCustomCallbackHelper(self, id, callback)
    end
  end
  return true
end
local mod = RegisterMod('Save Helper', 1)
if not AddCustomCallbackHelper(mod, 4, function() end) then error('helper must succeed') end
mod:AddCustomCallback(4, function() end)   -- savehelper.lua:696 的那一行
mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function() end)
print('MCM_PATTERN_OK')
)lua";
    } else {
        // dispatch / two_mods / getcallbacks 共用：登记 + 派发，看 self 是不是各自的 mod 表
        script = R"lua(
local first = RegisterMod('First', 1)
local second = RegisterMod('Second', 1)
if first == second then error('each RegisterMod must return a fresh object') end
if first.Name ~= 'First' or second.Name ~= 'Second' then error('names must differ') end
local hits = { first = 0, second = 0, selfMatches = true }
-- 名字回调：只钉"登记进列表的那个 Mod 对象是同一个"（本夹具不派发名字回调）
first:AddCallback('Probe.Named', function(self, text)
  hits.named = (hits.named or 0) + 1
  if self ~= first then hits.selfMatches = false end
end)
first:AddCallback(ModCallbacks.MC_POST_UPDATE, function(self)
  hits.first = hits.first + 1
  if self ~= first then hits.selfMatches = false end
end)
second:AddPriorityCallback(ModCallbacks.MC_POST_UPDATE, CallbackPriority.EARLY, function(self)
  hits.second = hits.second + 1
  if self ~= second then hits.selfMatches = false end
end)
-- 最后登记 ⇒ 最后跑：在这里汇总（同一 id、同优先级按登记顺序）
first:AddCallback(ModCallbacks.MC_POST_UPDATE, function()
  local list = Isaac.GetCallbacks('Probe.Named')
  if type(list) ~= 'table' or #list ~= 1 then error('GetCallbacks must list one entry') end
  if list[1].Mod ~= first then error('GetCallbacks entry must carry the same mod object') end
  print('DISPATCH_OK first=' .. tostring(hits.first) .. ' second=' .. tostring(hits.second)
        .. ' self=' .. tostring(hits.selfMatches))
end)
)lua";
    }
    const auto result = LuaRuntime::InitializeFromBuffer(script.c_str(), script.size(), "@modshape.lua");
    if (result != LuaRuntime::LuaInitResult::Success) {
        std::printf("MODSHAPE_FAIL: the Lua state did not initialize (%d)\n", static_cast<int>(result));
        return 2;
    }
    if (scenario == "shape" || scenario == "mcm_pattern") {
        if (LuaRuntime::TakeCallbackError()) {
            std::printf("MODSHAPE_FAIL: the load-time script raised\n");
            return 3;
        }
        return 0;
    }
    LuaRuntime::DispatchPostUpdate();
    if (LuaRuntime::TakeCallbackError()) {
        std::printf("MODSHAPE_FAIL: a Lua callback raised\n");
        return 4;
    }
    return 0;
}
'''


class LuaModObjectShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-modshape-")
        temporary = Path(cls.temporary.name)
        compatibility = temporary / "compatibility"
        compatibility.mkdir()
        (compatibility / "stdfloat").write_text(
            "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n"
        )
        harness = temporary / "mod_shape_harness.cpp"
        harness.write_text(HARNESS.lstrip(), encoding="utf-8")
        lua_root = SOURCE / "third_party/lua-5.3.3/src"
        excluded = {"lua.c", "luac.c", "liolib.c", "loslib.c", "loadlib.c", "ldblib.c", "linit.c"}
        objects = []
        for source in sorted(lua_root.glob("*.c")):
            if source.name in excluded:
                continue
            output = temporary / f"{source.stem}.o"
            build = subprocess.run(
                ["cc", "-std=c99", "-w", "-DLUA_C89_NUMBERS", "-I", str(lua_root),
                 "-c", str(source), "-o", str(output)], text=True, capture_output=True)
            if build.returncode != 0:
                raise AssertionError(build.stdout + build.stderr)
            objects.append(output)
        cls.harness = temporary / "mod_shape_harness"
        build = subprocess.run(
            ["c++", "-std=c++23", "-Wall", "-Wextra", "-Werror", "-DLUA_C89_NUMBERS",
             "-DEXL_LAYERED_RUNTIME=1", "-DEXL_LOAD_KIND=Module",
             "-DEXL_LOAD_KIND_ENUM=2", "-DEXL_PROGRAM_ID=0",
             "-I", str(compatibility), "-I", str(SOURCE), "-I", str(SOURCE.parent / "src"),
             "-I", str(lua_root), str(harness),
             *(str(path) for path in layered_lua_runtime_sources(SOURCE)),
             *map(str, objects), "-o", str(cls.harness)],
            text=True, capture_output=True)
        if build.returncode != 0:
            raise AssertionError(build.stdout + build.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario: str) -> subprocess.CompletedProcess:
        result = subprocess.run([str(self.harness), scenario], text=True, capture_output=True)
        self.assertNotIn("MODSHAPE_FAIL", result.stdout, result.stdout + result.stderr)
        return result

    def test_register_mod_returns_a_pc_shaped_table(self):
        """type == table、Name 是模组名、七个方法都在、模组能往自己身上写字段、句柄不漏出来。"""
        result = self.run_scenario("shape")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SHAPE_OK", result.stdout)

    def test_the_chinese_mcm_registration_pattern_no_longer_raises(self):
        """★ 回归判据：中文版 MCM 的 `type(mod) ~= 'table'` 那条检查必须过。

        事故现场（2026-09-30 傍晚）：`scripts/savehelper.lua:89` 的
        `SaveHelper.Mod = RegisterMod("Save Helper", 1)` 拿到 userdata ⇒
        `customcallbacks.lua:161` 当场 `error(...)` ⇒ **加载期脚本失败** ⇒ MCM 的回调一条都没登记
        ⇒ 右摇杆按下**菜单打不开**。这条用例逐句复刻那段写法。
        """
        result = self.run_scenario("mcm_pattern")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("MCM_PATTERN_OK", result.stdout)

    def test_callbacks_still_carry_the_right_owner_and_self(self):
        """表形态没把"多模组归属"搞坏：两条回调都派发、`self` 各是自己那张表、GetCallbacks 里是同一个对象。"""
        result = self.run_scenario("dispatch")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("first=1", result.stdout)
        self.assertIn("second=1", result.stdout)
        self.assertIn("self=true", result.stdout)


if __name__ == "__main__":
    unittest.main()
