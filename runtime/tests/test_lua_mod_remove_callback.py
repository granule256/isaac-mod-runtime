"""`Mod:RemoveCallback` 的宿主行为测试（2026-09-18）。

## 为什么需要它

EID 在真机上真的会调它（4 处：`features/eid_repentogon.lua:53/126/168`、
`features/eid_bagofcrafting_search.lua:96`），此前我们没实现 ⇒ 那几处报
`attempt to call a nil value (method 'RemoveCallback')`。

但这条 API 真正的风险不在"有没有"，而在**摘错人**：

* 同一 Mod 对同一 id 可以登记**多个**回调（EID 一家就登记 5 个 `MC_POST_NEW_ROOM`、
  10 个 `MC_PRE_USE_ITEM`）⇒ 按 id 摘会把同 id 上其余登记**一起摘掉**，
  症状是本项目最难查的那一类：不报错、不崩，那几块功能静默失效；
* PC 按**函数身份**匹配（同一个闭包的不同引用相等，而"代码完全相同的另一个闭包"不相等）。

## 本用例钉住什么

判据全部来自 Lua 侧可观察的计数 + 注册表条数（不读实现内部）：

1. 摘掉一个函数 ⇒ 同 id 上的**另一个**函数照旧被派发；
2. 传"代码完全相同但不是同一个闭包"的函数 ⇒ **什么都不摘**；
3. 拿"没登记过的 id"、或"登记在另一个 id 上的函数"来摘 ⇒ 无效果、且不报错；
4. 同一个函数摘两次 ⇒ 第二次无效果；
5. 摘除发生在**不被派发的那个 id** 上（在 `POST_RENDER` 的回调里摘 `POST_UPDATE` 的登记）——
   既与 EID 的真实用法一致，也避免制造"派发迭代中改表"这种另一类问题
   （那属于"运行时对重入的容忍度"，不在本用例的范围内）。
"""

import shutil
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
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/sprite_api.hpp"

#include "lua_runtime.hpp"
#include "game_file_reader.hpp"
#include "game_observer.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime_state.hpp"
#include "runtime_constants.hpp"

#include "application/callback/callback_registry.hpp"
#include "domain/callback/callback_descriptor.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

int g_Failures = 0;

void Check(bool condition, const char* what) {
    if (!condition) {
        std::printf("REMOVECB_FAIL %s\n", what);
        ++g_Failures;
    }
}

bool ExpectNumber(const char* name, double expected) {
    double value = 0.0;
    if (!LuaRuntime::ReadLuaGlobalNumber(name, &value)) {
        std::printf("REMOVECB_FAIL global %s was never written\n", name);
        return false;
    }
    if (value != expected) {
        std::printf("REMOVECB_FAIL %s expected %.0f got %.0f\n", name, expected, value);
        return false;
    }
    return true;
}

// 读 `counts.<field>`。用 `ReadLuaTableNumber` 而不是 `ReadLuaGlobalNumber("counts.a")` ——
// 后者走的是 `lua_getglobal`，**不解析点号**（会把 "counts.a" 当成一个全局名去找，永远读不到）。
bool ExpectField(const char* field, double expected) {
    double value = 0.0;
    // 返回 0 = 读到了。
    if (LuaRuntime::ReadLuaTableNumber("counts", field, &value) != 0) {
        std::printf("REMOVECB_FAIL counts.%s was never written\n", field);
        return false;
    }
    if (value != expected) {
        std::printf("REMOVECB_FAIL counts.%s expected %.0f got %.0f\n", field, expected, value);
        return false;
    }
    return true;
}

// 夹具脚本：登记 4 条回调（POST_UPDATE × 2、POST_RENDER × 2），由 `driver` 在
// POST_RENDER 的派发里做那几次摘除 —— 摘的对象都是 **POST_UPDATE** 上的登记，
// 与"正在被派发的那张表"错开（见文件头第 5 条）。
constexpr const char* kScript = R"LUA(
local mod = RegisterMod('RemoveCallbackTest', 1)

counts = { a = 0, b = 0, c = 0, driver = 0 }

local function a() counts.a = counts.a + 1 end
local function b() counts.b = counts.b + 1 end
local function c() counts.c = counts.c + 1 end

-- 与 a **代码完全相同**、但是另一个闭包：PC 按闭包身份比 ⇒ 拿它去摘不该摘掉任何东西。
local function sameCodeDifferentClosure() counts.a = counts.a + 1 end

local driver = function()
    counts.driver = counts.driver + 1
    if counts.driver == 1 then
        -- ① 不同闭包：无效果   ② 真身：摘掉 a（同 id 上的 b 必须留下）
        mod:RemoveCallback(ModCallbacks.MC_POST_UPDATE, sameCodeDifferentClosure)
        mod:RemoveCallback(ModCallbacks.MC_POST_UPDATE, a)
    elseif counts.driver == 2 then
        -- ③ 没登记过的 id：无效果   ④ 登记在另一个 id 上的函数：无效果
        mod:RemoveCallback(ModCallbacks.MC_PRE_GAME_EXIT, a)
        mod:RemoveCallback(ModCallbacks.MC_POST_UPDATE, c)
        -- ⑤ 同一个函数摘第二次：无效果
        mod:RemoveCallback(ModCallbacks.MC_POST_UPDATE, a)
    end
end

mod:AddCallback(ModCallbacks.MC_POST_UPDATE, a)
mod:AddCallback(ModCallbacks.MC_POST_UPDATE, b)
mod:AddCallback(ModCallbacks.MC_POST_RENDER, c)
mod:AddCallback(ModCallbacks.MC_POST_RENDER, driver)

REMOVE_CB_DONE = 1
)LUA";

}  // namespace

int main() {
    // 假的 manager 指针：`DispatchPostRender` 只要求它非 0（它是转给回调的上下文）。
    const std::uintptr_t kFakeManager = 0x1000;

    const auto result = LuaRuntime::InitializeFromBuffer(
        kScript, std::strlen(kScript), "@remove_callback.lua");
    if (result != LuaRuntime::LuaInitResult::Success) {
        std::printf("REMOVECB_FAIL the Lua state did not initialize\n");
        return 2;
    }
    Check(ExpectNumber("REMOVE_CB_DONE", 1.0), "the fixture script ran to the end");

    isaac::runtime::CallbackRegistry& registry = LuaRuntime::ManagedCallbackRegistry();
    Check(registry.Count() == 4, "the registry holds all four registrations");

    // 第 1 帧：只派发 POST_UPDATE ⇒ a、b 各一次；POST_RENDER 那两位还没动。
    LuaRuntime::DispatchPostUpdate();
    Check(!LuaRuntime::TakeCallbackError(), "no Lua error on the first POST_UPDATE dispatch");
    Check(ExpectField("a", 1.0), "a ran once on the first frame");
    Check(ExpectField("b", 1.0), "b ran once on the first frame");
    Check(ExpectField("c", 0.0), "c must not run before POST_RENDER is dispatched");
    Check(registry.Count() == 4, "nothing was removed before the driver ran");

    // 第 2 帧：派发 POST_RENDER ⇒ c 一次、driver 第一次运行（摘掉 a；"同代码另一个闭包"那次无效）。
    LuaRuntime::DispatchPostRender(kFakeManager);
    Check(!LuaRuntime::TakeCallbackError(), "no Lua error on the POST_RENDER dispatch");
    Check(registry.Count() == 3, "exactly one registration was removed (the different closure "
                                 "must not remove anything)");

    // 第 3 帧：再派发 POST_UPDATE ⇒ a 冻结在 1，b 走到 2（同 id 的另一条必须还活着）。
    LuaRuntime::DispatchPostUpdate();
    Check(!LuaRuntime::TakeCallbackError(), "no Lua error on the second POST_UPDATE dispatch");

    // 第 4、5 帧：driver 第二次运行做三种"应当无效"的摘除；c 必须一直活着。
    LuaRuntime::DispatchPostRender(kFakeManager);
    LuaRuntime::DispatchPostRender(kFakeManager);
    Check(!LuaRuntime::TakeCallbackError(), "noop removals must not raise a Lua error");
    Check(registry.Count() == 3, "noop removals must not change the registry");

    Check(ExpectField("a", 1.0), "a stays frozen after being removed");
    Check(ExpectField("b", 2.0), "b keeps running (same id, different function)");
    Check(ExpectField("c", 3.0), "c keeps running (registered under another id)");
    Check(ExpectField("driver", 3.0), "the driver ran on every POST_RENDER frame");

    if (g_Failures == 0) {
        std::printf("REMOVECB_OK registry=%zu a=1 b=2 c=3 driver=3\n", registry.Count());
    }
    return g_Failures == 0 ? 0 : 1;
}
'''


def host_compilers() -> tuple[str, str] | None:
    """(C 编译器, C++ 编译器)；缺任何一个就整体 skip，不伪装成通过。"""
    cc = shutil.which("cc")
    if cc is None:
        return None
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return cc, found
    return None


class ModRemoveCallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compilers = host_compilers()
        if compilers is None:
            raise unittest.SkipTest("需要宿主 C/C++ 编译器（本用例不需要 docker）")
        cc, cxx = compilers
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-remove-callback-")
        temporary = Path(cls.temporary.name)
        compatibility = temporary / "compatibility"
        compatibility.mkdir()
        (compatibility / "stdfloat").write_text(
            "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n"
        )
        harness = temporary / "remove_callback_harness.cpp"
        harness.write_text(HARNESS.lstrip(), encoding="utf-8")
        lua_root = SOURCE / "third_party/lua-5.3.3/src"
        excluded = {"lua.c", "luac.c", "liolib.c", "loslib.c", "loadlib.c", "ldblib.c", "linit.c"}
        lua_objects = []
        for lua_source in sorted(lua_root.glob("*.c")):
            if lua_source.name in excluded:
                continue
            output = temporary / f"{lua_source.stem}.o"
            build = subprocess.run(
                [cc, "-std=c99", "-w", "-DLUA_C89_NUMBERS", "-I", str(lua_root), "-c",
                 str(lua_source), "-o", str(output)], text=True, capture_output=True,
            )
            if build.returncode != 0:
                raise AssertionError(build.stdout + build.stderr)
            lua_objects.append(output)
        cls.harness = temporary / "remove_callback_harness"
        build = subprocess.run(
            [cxx, "-std=c++23", "-Wall", "-Wextra", "-Werror", "-DLUA_C89_NUMBERS",
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
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def test_remove_callback_matches_by_function_identity_and_keeps_its_siblings(self):
        result = subprocess.run([str(self.harness)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("REMOVECB_OK registry=3 a=1 b=2 c=3 driver=3", result.stdout)
        self.assertNotIn("REMOVECB_FAIL", result.stdout)


if __name__ == "__main__":
    unittest.main()
