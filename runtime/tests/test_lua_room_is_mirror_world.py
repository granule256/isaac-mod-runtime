"""`Room:IsMirrorWorld()` 的宿主行为测试（2026-09-18）。

## 为什么需要它

EID 在 `main.lua:839` **无条件**调这条（`EID.isMirrorRoom = level:GetCurrentRoom():IsMirrorWorld()`），
缺它就是一行 nil 调用报错。这条 API 的风险有两个，都很轻但都"静默"：

1. **布尔映射**：判据是"当前房间的维度 == 1"（维度枚举含义来自 PC 文档快照 `RoomDescriptor.md`）。
   映射写反（!= 1）不会报错，只会让 EID 在镜像维度里做出相反的决定；
2. **读不到时的降级**：这里**故意选择报错**而不是答 `false` —— 编一个 false 会让 EID
   按"不在镜像维度"行事，那是**用假数据影响显示**；报错至少是可见的。
   本用例把这两条都钉住。

（引擎侧的取证见 `runtime_constants.hpp` 的 `kMirrorWorldDimension`：
`Level + 0x21560` 是"当前房间的维度参数"，我们为判换房早已在读它。）
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
#include "lua_runtime.hpp"
#include "game_observer.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

namespace {
std::uint32_t g_Dimension = 0;
bool g_DimensionReadable = true;
std::uint64_t g_RoomStorage = 0;
}  // namespace

// 强定义覆盖共享弱默认桩（`runtime/tests/shared_lua_stubs.cpp`）：
// 拿 Room 句柄的那条、以及读维度的那条。
GameRoomObservation ReadCurrentGameRoom(uintptr_t ownerSlot, void** room) {
    if (ownerSlot != 0x1111 || room == nullptr) return GameRoomObservation::OwnerUnreadable;
    *room = &g_RoomStorage;
    return GameRoomObservation::Success;
}

GameLevelStageObservation ReadCurrentGameRoomDimension(uintptr_t ownerSlot,
                                                      std::uint32_t* dimension) {
    if (ownerSlot != 0x1111 || dimension == nullptr) {
        return GameLevelStageObservation::OwnerUnreadable;
    }
    if (!g_DimensionReadable) return GameLevelStageObservation::GameUnreadable;
    *dimension = g_Dimension;
    return GameLevelStageObservation::Success;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const std::string scenario = argv[1];
    if (scenario == "mirror") g_Dimension = 1;          // 次级维度 = 镜子维度
    if (scenario == "escape_dimension") g_Dimension = 2;  // 死亡证明维度：不是镜像
    if (scenario == "unreadable") g_DimensionReadable = false;

    // 断言写在脚本里（与其它 Room 用例同一形态）：脚本自己检查**返回类型必须是 boolean**、
    // 以及值与期望一致；C++ 侧只看"回调有没有抛错"。
    // 为什么在脚本里断言：Lua 的 boolean 读不进 `ReadLuaGlobalNumber`（`lua_isnumber` 对
    // boolean 为假），在这儿绕一层反而容易写出"把 false 读成 0 也算过"的假判据。
    const bool expected = (scenario == "mirror");
    const std::string script = std::string(
        "EXPECTED_MIRROR = ") + (expected ? "true" : "false") + "\n" +
        "local mod = RegisterMod('MirrorProbe', 1)\n"
        "mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE, function()\n"
        "  local value = Game():GetRoom():IsMirrorWorld()\n"
        "  if type(value) ~= 'boolean' then\n"
        "    error('IsMirrorWorld must return a boolean, got ' .. type(value))\n"
        "  end\n"
        "  if value ~= EXPECTED_MIRROR then\n"
        "    error('IsMirrorWorld returned ' .. tostring(value))\n"
        "  end\n"
        "  ASSERTED = 1\n"
        "end)";
    LuaRuntime::SetGameBindings(0x1111, 0x2222);
    const auto result =
        LuaRuntime::InitializeFromBuffer(script.data(), script.size(), "@mirror.lua");
    if (result != LuaRuntime::LuaInitResult::Success) {
        std::printf("MIRROR_FAIL the Lua state did not initialize\n");
        return 2;
    }
    LuaRuntime::DispatchPreGetCollectible(nullptr, 0, 0, 1, 0);

    const bool callbackFailed = LuaRuntime::TakeCallbackError();
    if (scenario == "unreadable") {
        // 读不到 ⇒ 必须**报错**，而不是静默答 false（编 false 会让 EID 在镜像维度里反向行事）。
        if (!callbackFailed) {
            std::printf("MIRROR_FAIL an unreadable dimension must raise, not answer false\n");
            return 3;
        }
        std::printf("MIRROR_OK unreadable=raised\n");
        return 0;
    }
    if (callbackFailed) {
        std::printf("MIRROR_FAIL the callback raised: the assertions inside the script failed\n");
        return 4;
    }
    double asserted = 0.0;
    if (!LuaRuntime::ReadLuaGlobalNumber("ASSERTED", &asserted) || asserted != 1.0) {
        std::printf("MIRROR_FAIL the script never reached its assertions\n");
        return 5;
    }
    std::printf("MIRROR_OK dimension=%u expected=%s\n", g_Dimension, expected ? "true" : "false");
    return 0;
}
'''



def host_compilers() -> tuple[str, str] | None:
    cc = shutil.which("cc")
    if cc is None:
        return None
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return cc, found
    return None


class RoomIsMirrorWorldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compilers = host_compilers()
        if compilers is None:
            raise unittest.SkipTest("需要宿主 C/C++ 编译器（本用例不需要 docker）")
        cc, cxx = compilers
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-mirror-room-")
        temporary = Path(cls.temporary.name)
        compatibility = temporary / "compatibility"
        compatibility.mkdir()
        (compatibility / "stdfloat").write_text(
            "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n"
        )
        harness = temporary / "mirror_harness.cpp"
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
        cls.binary = temporary / "mirror_harness"
        build = subprocess.run(
            [cxx, "-std=c++23", "-Wall", "-Wextra", "-Werror", "-DLUA_C89_NUMBERS",
             "-DEXL_LAYERED_RUNTIME=1", "-DEXL_LOAD_KIND=Module",
             "-DEXL_LOAD_KIND_ENUM=2", "-DEXL_PROGRAM_ID=0",
             "-I", str(compatibility), "-I", str(SOURCE), "-I", str(SOURCE.parent / "src"),
             "-I", str(lua_root), str(harness),
             *(str(path) for path in layered_lua_runtime_sources(SOURCE)),
             *map(str, objects), "-o", str(cls.binary)],
            text=True, capture_output=True,
        )
        if build.returncode != 0:
            raise AssertionError(build.stdout + build.stderr)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def run_scenario(self, scenario: str) -> str:
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, f"{scenario}: {result.stdout}{result.stderr}")
        return result.stdout

    def test_mirror_dimension_reports_true(self):
        self.assertIn("MIRROR_OK dimension=1 expected=true", self.run_scenario("mirror"))

    def test_other_dimensions_report_false(self):
        # 主维度（0）与死亡证明维度（2）都不是镜像世界。
        self.assertIn("MIRROR_OK dimension=0 expected=false", self.run_scenario("main"))
        self.assertIn("MIRROR_OK dimension=2 expected=false",
                      self.run_scenario("escape_dimension"))

    def test_an_unreadable_dimension_raises_instead_of_answering_false(self):
        self.assertIn("MIRROR_OK unreadable=raised", self.run_scenario("unreadable"))


if __name__ == "__main__":
    unittest.main()
