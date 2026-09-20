"""门禁：**数据行 API 的"调用 / 静默降级"计数器**（批次 069，2026-09-19）。

## 为什么有这条门禁

"这条 API 到底有没有被调到"在这个项目里被问过很多次，而在此之前的唯一答法是**写探针**：
改卡上第三方模组的脚本、让用户退游戏开 FTP 装上去再进游戏，一次十几分钟。
其中有几次的答案本身是**否定的**（"它压根没调这条 API"），也就是说十几分钟只为排除一个分支。

数据行处理器（`FieldApiHandler` / `EngineMethodHandler`）的设计是**静默降级**：接收者解析不到、
偏移拿不到、入口指纹不匹配，都只是"这一次没生效"，**不报错**（报错会把整条模组回调摘掉，
比"没生效"严重得多）。代价是"没生效"与"压根没被调用"在设备上长得一模一样 —— 只能靠探针区分。

批次 069 把这件事变成**常驻状态面**：数据行被调用的次数、最后一次被调用的行 id 与种类
（字段行 / 引擎方法行）、引擎方法行三类降级各自发生了多少次、最后一次降级是谁什么原因。

## 这条门禁钉住什么

一个真实 Lua 脚本里连续走四种情形，逐一断言（**四种情形必须在同一次运行里都被走到**，
否则下面的数字就没有意义）：

1. `Room:PlayMusic()` 而"当前房间"读不到 ⇒ 记 1 次**接收者**降级；
2. 读到了房间、但运行时还不知道引擎模块基址 ⇒ 记 1 次**偏移**降级；
3. 装了（假的）引擎镜像、入口 4 字节指纹不匹配 ⇒ 记 1 次**入口指纹**降级；
4. 字段行 `Level:GetStageType()` / `Level:IsAltStage()` 正常读到值 ⇒ **不记降级**，
   且把"最后一次调用"更新成字段行的 id 与种类。

第 4 条是这张表的**反例守卫**：如果哪天"成功也记降级"或"字段行不进调用计数"，
上面三条照样绿，只有它会红。
"""

import unittest
from pathlib import Path

try:
    from .test_support import layered_lua_runtime_sources
except ImportError:  # pragma: no cover - 直接跑单文件时的回退
    from test_support import layered_lua_runtime_sources


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

#: `Room:PlayMusic` 的 catalog id 与 `Level:IsAltStage` / `Level:GetStageType` 的 catalog id
#: （`api_catalog.cpp` 的 `MakeId(域, ownerGroup, 序号)`）。**故意写死在这里**：它们要与
#: `tools/read_device_state_via_gdb.py` 的 `api_catalog_names()` 解得一致，
#: 写死才能发现"编码口径被改了"。
ID_ROOM_PLAY_MUSIC = 0x0401000D
ID_LEVEL_STAGE_TYPE = 0x0301000B
ID_LEVEL_IS_ALT_STAGE = 0x0301000C

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_file_reader.hpp"
#include "game_observer.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/api_call_stats.hpp"
#include "ports/save_file_port.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
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
GameRoomObservation ReadCurrentGameRoomType(uintptr_t, std::uint32_t*) {
    return GameRoomObservation::RoomUnreadable;
}
namespace GameFileReader {
TextReadResult ReadTextFile(const Bindings&, const char*, u8*, std::size_t, std::size_t*) {
    return TextReadResult::OpenFailed;
}
}

namespace {

//: 假的"引擎镜像"。`Level` 接收者的解析链是
//: `模块基址 + 0xAAC698`（槽）→ 解出 owner → 再解一次得到 `Level*`，
//: 所以三块内存都由这个数组里的字节**喂**出来（内容是我们自己排的，不是猜的）。
alignas(8) unsigned char g_FakeImage[0xAAD000];
alignas(8) unsigned char g_FakeOwner[0x40];
alignas(4) unsigned char g_FakeLevel[0x40];

//: `ReadCurrentGameRoom` 被调用的次数 —— 它就是这个场景的"剧本"：
//:   第 1 次（`Game():GetRoom()`）           ⇒ 成功，给一个非零房间 ⇒ 拿到 Room 句柄；
//:   第 2 次（第 1 回 `PlayMusic`）          ⇒ 读不到 ⇒ **接收者**降级；
//:   第 3 次（第 2 回 `PlayMusic`）          ⇒ 成功，但模块基址仍是 0 ⇒ **偏移**降级；
//:   第 4 次（第 3 回 `PlayMusic`）          ⇒ 成功，并装好假镜像（入口指纹对不上）⇒ **入口指纹**降级。
int g_RoomStubCalls = 0;

//: 场景脚本：四种情形都在这一次运行里走到。
//:
//: **必须挂在 `MC_POST_UPDATE` 里**（与真机同形）：运行时要求脚本至少登记一条更新回调
//: （否则 `InitializeFromBuffer` 返回 `MissingPostUpdateCallback`），而"数据行 API 被调用"
//: 在真机上也都发生在回调里。回调只跑一次（`__ran` 守卫）。
constexpr char kScript[] = R"lua(
local mod = RegisterMod('ApiCallStatsProbe', 1)
mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function()
  if _G.__ran then return end
  _G.__ran = true
  local room = Game():GetRoom()
  local function attempt(fn)
    local ok, err = pcall(fn)
    if ok then _G.__okCount = (_G.__okCount or 0) + 1 end
    -- 批次 069 修正的那个缺陷会在这里露头：`room:PlayMusic()`（冒号调用）曾被判成
    -- "expects 0 argument(s)" ⇒ 记为 1，断言它必须是 0（见下面第三条测试）。
    _G.__arityError = (string.find(tostring(err), 'expects 0 argument') and 1 or 0)
                      + (_G.__arityError or 0)
  end
  attempt(function() return room:PlayMusic() end)   -- 接收者降级
  attempt(function() return room:PlayMusic() end)   -- 偏移降级
  attempt(function() return room:PlayMusic() end)   -- 入口指纹降级
  local level = Game():GetLevel()
  _G.__stageType = level:GetStageType()             -- 字段行：正常读到值
  _G.__isAlt = level:IsAltStage() and 1 or 0        -- 字段行：正常读到值（最后一次调用）
end)
)lua";

} // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    ++g_RoomStubCalls;
    if (g_RoomStubCalls == 2) {
        return GameRoomObservation::RoomUnreadable;   // ⇒ 接收者降级
    }
    if (g_RoomStubCalls >= 4) {
        // 装好假镜像：`Level` 链走通，但 `Room:PlayMusic` 的入口 4 字节是 0、指纹不为 0
        // ⇒ 走到"入口指纹不匹配"这一支。
        std::uintptr_t owner = reinterpret_cast<std::uintptr_t>(g_FakeOwner);
        std::uintptr_t level = reinterpret_cast<std::uintptr_t>(g_FakeLevel);
        std::memcpy(g_FakeImage + 0xAAC698, &owner, sizeof(owner));
        std::memcpy(g_FakeOwner, &level, sizeof(level));
        const std::uint32_t stageType = 3;
        std::memcpy(g_FakeLevel + 0x04, &stageType, sizeof(stageType));
        LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(g_FakeImage));
    }
    *room = reinterpret_cast<void*>(0x1000);
    return GameRoomObservation::Success;
}

int main() {
    const auto result = LuaRuntime::InitializeFromBuffer(kScript, std::strlen(kScript),
                                                         "@api_call_stats.lua");
    if (result != LuaRuntime::LuaInitResult::Success) {
        std::printf("STATS_FAIL init=%d\n", static_cast<int>(result));
        return 2;
    }
    // 场景挂在更新回调里 ⇒ 派发一帧才走得到（与真机同形）。
    LuaRuntime::DispatchPostUpdate();
    const isaac::runtime::ApiRowStats stats = isaac::runtime::ApiRowStatsSnapshot();
    // 字段行"真的读到了值"的独立证据：`Level + 0x04` 是我们自己填的 3，
    // 而 Lua 侧拿到的就是这个数（`Level:IsAltStage()` 则是它的 != 0）。
    double stageType = 0.0;
    double isAlt = 0.0;
    const bool readStage = LuaRuntime::ReadLuaGlobalNumber("__stageType", &stageType);
    const bool readAlt = LuaRuntime::ReadLuaGlobalNumber("__isAlt", &isAlt);
    std::printf("STUB_CALLS %d\n", g_RoomStubCalls);
    std::printf("CALLS %u LAST_ID 0x%08X LAST_KIND %u\n", stats.calls, stats.lastCallId,
                stats.lastCallKind);
    std::printf("ENGINE_CALLS %u\n", stats.engineCalls);
    std::printf("REJECT receiver=%u offset=%u entry=%u last_id=0x%08X last_reason=%u\n",
                stats.rejectReceiver, stats.rejectOffset, stats.rejectEntry, stats.lastRejectId,
                stats.lastRejectReason);
    std::printf("FIELD_VALUES stage_read=%d alt_read=%d stage=%d alt=%d\n", readStage ? 1 : 0,
                readAlt ? 1 : 0, static_cast<int>(stageType), static_cast<int>(isAlt));
    double okCount = 0.0;
    double arityError = 0.0;
    LuaRuntime::ReadLuaGlobalNumber("__okCount", &okCount);
    LuaRuntime::ReadLuaGlobalNumber("__arityError", &arityError);
    std::printf("ATTEMPTS ok=%d arity_error=%d\n", static_cast<int>(okCount),
                static_cast<int>(arityError));
    return 0;
}
'''


class ApiCallStatsGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_harness = _compile_and_run()
        cls.output = cls.run_harness()

    def numbers(self) -> dict[str, int]:
        """把 harness 的输出解析成"名字 → 数值"（键名大写，避免与断言里的字段名混淆）。"""
        found: dict[str, int] = {}
        for line in self.output.splitlines():
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "STUB_CALLS":
                found["STUB_CALLS"] = int(parts[1])
            elif parts[0] == "CALLS":
                found["CALLS"] = int(parts[1])
                found["LAST_ID"] = int(parts[3], 16)
                found["LAST_KIND"] = int(parts[5])
            elif parts[0] == "ENGINE_CALLS":
                found["ENGINE_CALLS"] = int(parts[1])
            elif parts[0] == "REJECT":
                for part in parts[1:]:
                    key, _, value = part.partition("=")
                    found["REJECT_" + key.upper()] = int(value, 16) if key == "last_id" else int(value)
            elif parts[0] == "ATTEMPTS":
                for part in parts[1:]:
                    key, _, value = part.partition("=")
                    found["ATTEMPTS_" + key.upper()] = int(value)
            elif parts[0] == "FIELD_VALUES":
                for part in parts[1:]:
                    key, _, value = part.partition("=")
                    found["FIELD_" + key.upper()] = int(value)
        return found

    def test_every_row_api_call_is_counted(self):
        """三次引擎方法行 + 两次字段行 ⇒ 计数 5，且引擎方法行单独计 3。

        真机用途：接上一个新模组之后**不用写探针**就能看到"我们那些 API 有没有被调到"。
        """
        numbers = self.numbers()
        self.assertEqual(numbers.get("STUB_CALLS"), 4, self.output)
        self.assertEqual(numbers.get("CALLS"), 5, self.output)
        self.assertEqual(numbers.get("ENGINE_CALLS"), 3, self.output)
        # ★ 批次 069 修正的缺陷回归守卫：`room:PlayMusic()` 这种**冒号调用**曾被判成参数个数
        # 不对（"expects 0 argument(s)"）⇒ 真机上这条 API 一被调用就报错、把整条模组回调打断。
        # 三次 `pcall` 必须全部成功、且没有任何一条报参数个数错。
        self.assertEqual(numbers.get("ATTEMPTS_OK"), 3, self.output)
        self.assertEqual(numbers.get("ATTEMPTS_ARITY_ERROR"), 0, self.output)

    def test_three_silent_degrade_reasons_are_distinguishable(self):
        """接收者 / 偏移 / 入口指纹三类降级**各记各的**，并留下最后一次的 id 与原因。

        这一条是"调了却没生效"与"压根没调"能被分开的关键：三种原因混成一个数字的话，
        真机上仍然得写探针去问"到底卡在哪一步"。
        """
        numbers = self.numbers()
        self.assertEqual(numbers.get("REJECT_RECEIVER"), 1, self.output)
        self.assertEqual(numbers.get("REJECT_OFFSET"), 1, self.output)
        self.assertEqual(numbers.get("REJECT_ENTRY"), 1, self.output)
        # 最后一次降级 = 第 3 回 `Room:PlayMusic`（入口指纹），id 必须是 catalog 里那条。
        self.assertEqual(numbers.get("REJECT_LAST_ID"), ID_ROOM_PLAY_MUSIC, self.output)
        self.assertEqual(numbers.get("REJECT_LAST_REASON"), 3, self.output)

    def test_successful_field_row_updates_last_call_without_recording_a_degrade(self):
        """反例守卫：字段行读到值之后，"最后一次调用"变成**字段行**，而降级计数**不许增加**。

        没有这一条，把"成功也算降级"或"字段行不进计数"这两个错误都测不出来。
        """
        numbers = self.numbers()
        self.assertEqual(numbers.get("LAST_KIND"), 1, self.output)  # 1 = 字段行
        self.assertEqual(numbers.get("LAST_ID"), ID_LEVEL_IS_ALT_STAGE, self.output)
        self.assertEqual(numbers.get("FIELD_STAGE_READ"), 1, self.output)
        self.assertEqual(numbers.get("FIELD_ALT_READ"), 1, self.output)
        self.assertEqual(numbers.get("FIELD_STAGE"), 3, self.output)
        self.assertEqual(numbers.get("FIELD_ALT"), 1, self.output)


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
    temporary = Path(tempfile.mkdtemp(prefix="api-call-stats-"))
    compatibility = temporary / "compatibility"
    compatibility.mkdir()
    (compatibility / "stdfloat").write_text(
        "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n",
        encoding="utf-8")
    harness = temporary / "harness.cpp"
    harness.write_text(HARNESS, encoding="utf-8")

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
