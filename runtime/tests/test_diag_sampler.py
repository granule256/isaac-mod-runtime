"""门禁：**诊断伴生采样**（批次 070，2026-09-19）—— 第三方模组的内部状态不必再靠探针问。

## 为什么有这条门禁

"GoodTrip 的 `gt.floor.crd` 现在是不是 nil""它的配置项读出来是多少"这类问题，此前唯一的答法是
**改那个模组的脚本**再装一次卡：用户"退游戏 → 开 FTP → 装 → 关 FTP → 开游戏"，一次十几分钟，
而且**一个问题一轮**（今天为同一件事装过 4 个版本的探针）。

批次 070 把它改成常驻能力：**我们自己的菜单模组**（本来就第一个加载、不占模组位、不改任何
第三方文件）定期把模组挂在全局上的入口浅表扫一遍，写进**它自己的模组数据**。
读数工具本来就会解模组数据，于是这类问题变成一条读数命令。

## 这条门禁钉住什么

宿主 harness 里放一个假的 `gt` 全局（模拟 GoodTrip 挂出来的表），跑内嵌菜单脚本 ≥120 帧
（采样的首次倒计时），然后**读回模组数据**（走真实的持久化端口）断言：

1. 确实写出了采样文本，且带 `DIAGSAMPLE` 前缀（读数时一眼能认出这是采样而不是模组自己的存档）；
2. 采样**真的看到了 `gt` 表里的值**（`gt.floor.crd=42`、`gt.config.AllowAnyRoom=true`）；
3. `gt` **不存在**时也不许报错（写 `<missing>`）—— 换模组/换卡之后采样不能把菜单弄坏。

第 3 条是"实用性"的守卫：没有它，一次表结构变化就会让采样自己在真机上抛错，
而这类错误在本项目里表现为"回调被摘掉"，看起来像"菜单坏了"。
"""

import unittest
from pathlib import Path

try:
    from .test_support import HOST_CAPABILITY_FAKES, layered_lua_runtime_sources
except ImportError:  # pragma: no cover - 直接跑单文件时的回退
    from test_support import HOST_CAPABILITY_FAKES, layered_lua_runtime_sources


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

#: 采样的首次倒计时是 120 帧（见脚本里的 `DIAG.countdown`）⇒ 多跑几帧确保采到。
FRAMES = 130

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_file_reader.hpp"
#include "game_observer.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "ports/save_file_port.hpp"
#include "program/embedded_mod_menu_script.hpp"

#include "application/callback/callback_dispatcher.hpp"

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <string_view>

// 与其它 Lua runtime harness 同一套"观测缝"桩（口径照抄 `test_lua_error_history`）。
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

@HOST_CAPABILITIES@

namespace {

//: 假模组的全局入口：形状照着"模组把自己的模块表挂在全局上"（GoodTrip 是 `gt`）。
//: Python 侧会把下面这段替换成"有 gt"或"没有 gt"两种，用来钉第 3 条判据。
constexpr char kPrelude[] = R"lua(
@FAKE_GLOBALS@
)lua";

} // namespace

int main() {
    // 宿主能力（内存版存档端口）：模组数据要真的写得出去，采样才有意义。
    PublishHostCapabilities();
    // 真实路径：菜单脚本**不是**由 `InitializeFromBuffer` 自动执行的（它由
    // `InitializeEmbeddedMenuMod` 当第一个模组加载），所以这里自己把它拼在假全局之后跑。
    std::string script(kPrelude);
    script += std::string(isaac::runtime::kEmbeddedModMenuScript);
    const auto result = LuaRuntime::InitializeFromBuffer(
        script.c_str(), script.size(), isaac::runtime::kModMenuChunkName);
    if (result != LuaRuntime::LuaInitResult::Success) {
        std::printf("DIAG_FAIL init=%d\n", static_cast<int>(result));
        return 2;
    }
    for (int frame = 0; frame < @FRAMES@; ++frame) {
        LuaRuntime::DispatchPostUpdate();
    }
    // 持久化端口写进去的就是"模组数据"（与真机上读数工具解到的那份同源）。
    // 夹具的 `Read` 不认路径（内存版存档），所以借它把整块读回来即可。
    static char buffer[16 * 1024];
    std::size_t savedSize = 0;
    g_store.Read("mod-data", buffer, sizeof(buffer), &savedSize);
    // 存档容器本身是二进制（容器头 + 每条记录 24 字节头），所以先把不可打印字节换成 `.`
    // 再按行打印 —— 直接 `printf("%s")` 会**在第一个 NUL 就停住**，把后面的正文吞掉
    // （本次第一版就是这么写的，现象是"采样前缀不见了"）。
    std::string saved(buffer, savedSize);
    for (char& byte : saved) {
        const unsigned char value = static_cast<unsigned char>(byte);
        const bool printable = (value >= 0x20 && value < 0x7F) || byte == '\n';
        if (!printable) {
            byte = '.';
        }
    }
    std::printf("SAVED_BYTES %zu\n", savedSize);
    std::size_t start = 0;
    while (start < saved.size()) {
        std::size_t end = saved.find('\n', start);
        if (end == std::string::npos) {
            end = saved.size();
        }
        std::printf("LINE %s\n", saved.substr(start, end - start).c_str());
        start = end + 1;
    }
    return 0;
}
'''


FAKE_GLOBALS_WITH_GT = """
gt = { floor = { crd = 42, rooms = { 1, 2, 3 } },
       config = { AllowAnyRoom = true, Debug = false, Note = 'hello' } }
"""

FAKE_GLOBALS_WITHOUT_GT = """
gt = nil
"""


class DiagSamplerGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.with_gt = _compile_and_run(FAKE_GLOBALS_WITH_GT)
        cls.output = cls.with_gt()
        cls.without_gt = _compile_and_run(FAKE_GLOBALS_WITHOUT_GT)
        cls.output_without_gt = cls.without_gt()

    def test_sample_is_written_to_its_own_mod_data(self):
        """采样必须真的落到模组数据里，并带 `DIAGSAMPLE` 前缀。

        这一条是整件事的意义所在：读数工具读的就是这份模组数据
        ⇒ 采样写不出去，"不用探针"就无从谈起。
        """
        self.assertIn("DIAGSAMPLE", self.output, self.output)
        saved_bytes = int([line.split()[1] for line in self.output.splitlines()
                           if line.startswith("SAVED_BYTES ")][0])
        self.assertGreater(saved_bytes, 0, self.output)

    def test_sample_sees_values_inside_the_third_party_global(self):
        """采样必须看到 `gt` 表里的**值**（深度 2 层：`gt.floor.crd` 这一层）。

        真机用途：GoodTrip 是"格子在不在可传送集合里"这类判断全靠它自己的表，
        能看到那些值，就不用再往它脚本里塞探针。
        """
        self.assertIn("gt=<table>", self.output, self.output)
        self.assertIn("gt.floor.crd=42", self.output, self.output)
        self.assertIn("gt.config.AllowAnyRoom=true", self.output, self.output)

    def test_missing_global_is_reported_instead_of_raising(self):
        """`gt` 不存在时写 `<missing>` 且不报错（换模组/换卡之后采样不能把菜单弄坏）。"""
        self.assertIn("gt=<missing>", self.output_without_gt, self.output_without_gt)
        self.assertNotIn("DIAG_FAIL", self.output_without_gt, self.output_without_gt)
        # 引擎侧概要也要照常采（三条都必须出现；真机上是 `<error>` 还是数值不影响采样成立）。
        for name in ("engine.frame=", "engine.roomType=", "engine.greedMode="):
            self.assertIn(name, self.output_without_gt, self.output_without_gt)


def host_compilers() -> tuple[str, str] | None:
    """(C 编译器, C++ 编译器)；缺任何一个就整体 skip，不伪装成通过。"""
    import shutil

    cc = shutil.which("cc")
    if cc is None:
        return None
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return cc, found
    return None


def _compile_and_run(fake_globals: str):
    """按仓库既有 harness 的配方编译（vendored Lua 单独编、宏与包含路径照抄）。"""
    import subprocess
    import tempfile

    compilers = host_compilers()
    if compilers is None:
        raise unittest.SkipTest("需要宿主 C/C++ 编译器（本用例不需要 docker）")
    cc, cxx = compilers
    temporary = Path(tempfile.mkdtemp(prefix="diag-sampler-"))
    compatibility = temporary / "compatibility"
    compatibility.mkdir()
    (compatibility / "stdfloat").write_text(
        "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n",
        encoding="utf-8")
    harness = temporary / "harness.cpp"
    harness.write_text(HARNESS.replace("@HOST_CAPABILITIES@", HOST_CAPABILITY_FAKES)
                       .replace("@FAKE_GLOBALS@", fake_globals)
                       .replace("@FRAMES@", str(FRAMES)), encoding="utf-8")

    lua_root = SOURCE / "third_party/lua-5.3.3/src"
    excluded = {"lua.c", "luac.c", "liolib.c", "loslib.c", "loadlib.c", "ldblib.c", "linit.c"}
    lua_objects = []
    for lua_source in sorted(lua_root.glob("*.c")):
        if lua_source.name in excluded:
            continue
        output = temporary / f"{lua_source.stem}.o"
        build = subprocess.run([cc, "-std=c99", "-w", "-DLUA_C89_NUMBERS", "-I", str(lua_root),
                                "-c", str(lua_source), "-o", str(output)],
                               text=True, capture_output=True)
        if build.returncode != 0:
            raise AssertionError(build.stdout + build.stderr)
        lua_objects.append(output)

    binary = temporary / "harness"
    build = subprocess.run(
        [cxx, "-std=c++23", "-w", "-DLUA_C89_NUMBERS", "-DEXL_LAYERED_RUNTIME=1",
         "-DEXL_LOAD_KIND=Module", "-DEXL_LOAD_KIND_ENUM=2", "-DEXL_PROGRAM_ID=0",
         "-I", str(compatibility), "-I", str(SOURCE), "-I", str(ROOT / "runtime" / "src"),
         "-I", str(lua_root), str(harness),
         *(str(path) for path in layered_lua_runtime_sources(SOURCE)),
         *map(str, lua_objects), "-o", str(binary)],
        text=True, capture_output=True)
    if build.returncode != 0:
        raise AssertionError(f"compile failed:\n{build.stdout}\n{build.stderr}")

    def run() -> str:
        finished = subprocess.run([str(binary)], capture_output=True, text=True,
                                  errors="replace")
        if finished.returncode != 0:
            raise AssertionError(
                f"harness exited {finished.returncode}\n{finished.stdout}{finished.stderr}")
        return finished.stdout

    return run


if __name__ == "__main__":
    unittest.main()
