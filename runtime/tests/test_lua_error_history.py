"""门禁：**Lua 错误环形历史**的归属与去重（批次 068，2026-09-19）。

## 为什么有这条门禁

真机上"到底是哪个模组坏了"这个问题兜了**三轮**，两次吃亏都在这个观测层上：

1. **只有一个错误槽**（批次 052 之前）：A 模组的错会被 B 模组的错盖掉；
2. **有环形历史但会被刷屏**（批次 052~067）：EID 有一条"每帧都报"的错把 8 格**全部**占满，
   于是 GoodTrip 的错**一条都进不来** —— 读数里只看得到 EID，我又得写探针去问"GoodTrip 怎么了"。

批次 068 的两条判据，正是上面两次事故的对应物：

* **归属**：每条记录必须带"哪个模组（`ModHandle` 打包成 u32）+ 哪条回调 id"；
* **去重**：同一个模组的**同一条文本**只占一格 —— 重复错误不许把别人的格子挤掉，
  但它自己仍然要能被看到（第一次写进去的那一格）。

宿主 harness 用**两个模组**各注册一条 `MC_POST_UPDATE` 回调：A 每帧报同一条错（重复 5 次）、
B 报另一条；然后直接读环形历史断言上面两件事。
"""

import unittest
from pathlib import Path

try:
    from .test_support import HOST_CAPABILITY_FAKES, layered_lua_runtime_sources
except ImportError:  # pragma: no cover - 直接跑单文件时的回退
    from test_support import HOST_CAPABILITY_FAKES, layered_lua_runtime_sources


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

#: 5 帧 ⇒ 模组 A 的那条错会被重复报 5 次。
FRAMES = 5

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_file_reader.hpp"
#include "game_observer.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "ports/save_file_port.hpp"

#include "application/callback/callback_dispatcher.hpp"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string_view>

// 与其它 Lua runtime harness 同一套"观测缝"桩（写死返回"读不到"，口径照抄 `test_lua_isaac_table`）。
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

namespace {

// 两个模组各报一条错：A 每帧报同一条（重复 @FRAMES@ 次）、B 报另一条。
constexpr char kScript[] = R"lua(
local a = RegisterMod('ModA', 1)
local b = RegisterMod('ModB', 1)
a:AddCallback(ModCallbacks.MC_POST_UPDATE, function() error('A repeated failure') end)
b:AddCallback(ModCallbacks.MC_POST_UPDATE, function() error('B distinct failure') end)
)lua";

} // namespace

int main() {
    const auto result = LuaRuntime::InitializeFromBuffer(kScript, std::strlen(kScript),
                                                         "@history_mod.lua");
    if (result != LuaRuntime::LuaInitResult::Success) {
        std::printf("HISTORY_FAIL init=%d\n", static_cast<int>(result));
        return 2;
    }
    for (int frame = 0; frame < @FRAMES@; ++frame) {
        LuaRuntime::DispatchPostUpdate();
    }
    LuaRuntime::LuaErrorHistoryEntryView entries[8] = {};
    const std::size_t count = LuaRuntime::CopyLuaErrorHistory(entries, 8);
    for (std::size_t index = 0; index < count; ++index) {
        std::printf("ENTRY %zu owner=%u callback=%u text=%s\n", index, entries[index].owner,
                    entries[index].callbackId, entries[index].text);
    }
    std::printf("COUNT %zu\n", count);
    return 0;
}
'''


class LuaErrorHistoryGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_harness = _compile_and_run()
        cls.output = cls.run_harness()

    def entries(self) -> dict[str, dict]:
        found = {}
        for line in self.output.splitlines():
            if not line.startswith("ENTRY "):
                continue
            # 行格式：`ENTRY <i> owner=<n> callback=<n> text=<可能带空格的文本>`
            body = line[len("ENTRY "):]
            head, _, text = body.partition("text=")
            # `head` 形如 `0 owner=65539 callback=1 `：第 0 段是序号，其余是 `键=值`。
            fields = {}
            for part in head.split():
                if "=" in part:
                    key_name, _, value = part.partition("=")
                    fields[key_name] = value
            fields["text"] = text
            key = "A" if "A repeated failure" in text else "B"
            found[key] = fields
        return found

    def test_repeats_do_not_crowd_out_other_mods(self):
        """A 每帧报同一条错（5 次）、B 报另一条 ⇒ 历史里**两条都在**，A 只占一格。

        真机事故：EID 那条每帧刷屏的错把 8 格全占满，GoodTrip 的错一条都进不来。
        """
        entries = self.entries()
        self.assertEqual(sorted(entries), ["A", "B"], self.output)
        self.assertIn("COUNT 2", self.output, self.output)

    def test_entries_carry_owner_and_callback_id(self):
        """每条都要带"哪个模组 + 哪条回调"：两个模组的 owner 不同，回调 id = `MC_POST_UPDATE`(1)。"""
        entries = self.entries()
        self.assertNotEqual(entries["A"]["owner"], entries["B"]["owner"], self.output)
        # `ModHandle` 打包：低 16 位 = index（两个模组不同 ⇒ 两个 owner 值不同且都非 0）
        self.assertNotEqual(entries["A"]["owner"], "0", self.output)
        self.assertEqual(entries["A"]["callback"], "1", self.output)
        self.assertEqual(entries["B"]["callback"], "1", self.output)


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


def _compile_and_run():
    """按仓库既有 harness 的配方编译（vendored Lua 单独编、宏与包含路径照抄）。"""
    import subprocess
    import tempfile

    compilers = host_compilers()
    if compilers is None:
        raise unittest.SkipTest("需要宿主 C/C++ 编译器（本用例不需要 docker）")
    cc, cxx = compilers
    temporary = Path(tempfile.mkdtemp(prefix="lua-error-history-"))
    compatibility = temporary / "compatibility"
    compatibility.mkdir()
    (compatibility / "stdfloat").write_text(
        "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n",
        encoding="utf-8")
    harness = temporary / "harness.cpp"
    harness.write_text(HARNESS.replace("@FRAMES@", str(FRAMES)), encoding="utf-8")

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
        finished = subprocess.run([str(binary)], capture_output=True, text=True)
        if finished.returncode != 0:
            raise AssertionError(
                f"harness exited {finished.returncode}\n{finished.stdout}{finished.stderr}")
        return finished.stdout

    return run


if __name__ == "__main__":
    unittest.main()
