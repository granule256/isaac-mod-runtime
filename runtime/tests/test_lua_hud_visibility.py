"""`Game:GetHUD()` / `HUD:IsVisible()` / `HUD:SetVisible(bool)` 的宿主行为测试（批次 207）。

## 为什么有它

MCM（Mod Config Menu）**每次开/关菜单**都要走这三条：
`OpenConfigMenu`/`CloseConfigMenu` 里 `local hud = Game():GetHUD()`，然后
`if hud:IsVisible() then hud:SetVisible(false) end`（`scripts/modconfig.lua:1199/1203` 与
`2939/2961`；`1202/1206` 读、`1203/1207/2940/2962` 写）。
缺任意一条就是 `attempt to call a nil value (method 'GetHUD')` ⇒ **整条回调被摘掉**
（菜单打开时游戏画面不会藏 HUD，也就等于功能没生效）。

## 这一族**没有**引擎入口，全部是"读/写引擎的一个字节"

证据（反汇编，记在 `runtime_constants.hpp` 的批次 207 段）：

* `HUD` 是 `Game` 里**内嵌**的子对象 —— `HUD* = Game* + kGameHudObjectOffset`（加法，不解引用；
  `Game::Game() @ 0x34B3F8` 里 `add x0, x20, x8` + `bl HUD::HUD()`）；
* 可见与否 = `HUD + kHudVisibleFlagOffset` 这**一个字节**：
  `HUD::Render() @ 0x3AC71C` 的**第一条有效判断**就是把它 `ldrb` 进 `w8`、`cbz` 跳过整段渲染；
* ★ 全镜像扫描（AArch64 立即数装配模拟器，11 210 752 字节）确认：构造这个偏移的**只有
  `HUD::Render` 那一处、而且是读** ⇒ 引擎自己从不写这一格。所以 `SetVisible` 是"我们写一格
  引擎只读的开关"，由本用例在**宿主伪造内存**上把这件事钉死。

因此这个用例断言的是"我们这一侧读得对、写得对、参数校验对、读不到时降级得对"：

1. `Game:GetHUD()` 存在、可重复调用、**不接受参数**；
2. `IsVisible()` 读的确实是引擎那一格（伪造内存里先放 1 ⇒ Lua 侧为 true）；
3. `SetVisible(false)` **真的把那一格写成 0**（C++ 侧直接读伪造内存复核，而不是只看 Lua 自己说），
   而且**跨帧仍然有效**（第二帧再读还是 false —— 证明写的是引擎内存，不是某个每帧重建的缓存）；
4. 缺省参数按 PC 契约是 `false`（`HUD.md:56` 的 `boolean Visible = false`）——
   `SetVisible()` / `SetVisible(nil)` 都必须是"藏起来"，不是"什么都不做"；
5. 参数校验：多给参数要**报 Lua 错误并点出 API 名字**（静默接受会让模组的笔误变成
   "看起来生效了"）；
6. **没有引擎基址**（`SetEngineModuleBase` 没被调用，例如加载期）时：`IsVisible()` 安静给
   `false`、`SetVisible()` 安静返回，**都不许报错** —— 报错会把整条回调摘掉。
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


def render_harness() -> str:
    """把 Lua 脚本注入 harness（`@SCRIPT@` 占位，避免误替换其它同名标识符）。"""
    return HARNESS.replace("@SCRIPT@", SCRIPT).lstrip()


class LuaHudVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compilers = host_compilers()
        if compilers is None:
            raise unittest.SkipTest("需要宿主 C/C++ 编译器（本用例不需要 docker）")
        cc, cxx = compilers
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-hud-")
        temporary = Path(cls.temporary.name)
        compatibility = temporary / "compatibility"
        compatibility.mkdir()
        (compatibility / "stdfloat").write_text(
            "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n"
        )
        harness = temporary / "hud_harness.cpp"
        harness.write_text(render_harness(), encoding="utf-8")
        lua_root = SOURCE / "third_party/lua-5.3.3/src"
        excluded = {"lua.c", "luac.c", "liolib.c", "loadlib.c", "ldblib.c", "linit.c"}
        objects = []
        for source in sorted(lua_root.glob("*.c")):
            if source.name in excluded:
                continue
            output = temporary / f"{source.stem}.o"
            build = subprocess.run(
                [cc, "-std=c99", "-w", "-DLUA_C89_NUMBERS", "-I", str(lua_root),
                 "-c", str(source), "-o", str(output)], text=True, capture_output=True)
            if build.returncode != 0:
                raise AssertionError(build.stdout + build.stderr)
            objects.append(output)
        cls.binary = temporary / "hud_harness"
        build = subprocess.run(
            [cxx, "-std=c++23", "-Wall", "-Wextra", "-Werror", "-DLUA_C89_NUMBERS",
             "-DEXL_LAYERED_RUNTIME=1", "-DEXL_LOAD_KIND=Module",
             "-DEXL_LOAD_KIND_ENUM=2", "-DEXL_PROGRAM_ID=0",
             "-I", str(compatibility), "-I", str(SOURCE), "-I", str(SOURCE.parent / "src"),
             "-I", str(lua_root), str(harness),
             *(str(path) for path in layered_lua_runtime_sources(SOURCE)),
             *(str(path) for path in objects), "-o", str(cls.binary)],
            text=True, capture_output=True)
        if build.returncode != 0:
            raise AssertionError(build.stdout + build.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_harness(self, scenario):
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_the_flag_byte_round_trips_through_engine_memory(self):
        """主判据：读得到、写得进、**跨帧**还成立（写的是引擎内存，不是每帧重建的缓存）。"""
        result = self.run_harness("with_engine")
        self.assertIn("HUD_OK scenario=with_engine", result.stdout)
        # harness 打印了两帧各自读回的字节：第一帧脚本写 0、第二帧脚本写 1。
        self.assertIn("frame1_flag=0", result.stdout)
        self.assertIn("frame2_flag=1", result.stdout)

    def test_without_an_engine_base_the_family_degrades_silently(self):
        """没有引擎基址时读给 false、写安静返回 —— 报错会摘掉整条回调。"""
        result = self.run_harness("no_base")
        self.assertIn("HUD_OK scenario=no_base", result.stdout)

    def test_the_hud_handle_never_stores_a_native_pointer(self):
        """句柄里不许存原生指针（存了就会在房间/关卡切换后变成野指针）。

        与 `RoomHandle` 同一条纪律：每次调用都从 `Game*` 重新解析。
        """
        handles = (SOURCE / "lua_object_handles.hpp").read_text(encoding="utf-8")
        handle = handles[handles.index("struct HudHandle"):]
        handle = handle[:handle.index("};")]
        self.assertNotIn("uintptr_t", handle)
        self.assertNotIn("HUD*", handle)
        self.assertNotIn("void*", handle)


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_file_reader.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

// 别的家族的观察面：本用例不碰它们，按"不可读/不可用"回答（与其它 Lua 运行时测试一致）。
GameIsPausedObservation ObserveGameIsPaused(uintptr_t, uintptr_t) {
    return GameIsPausedObservation::OwnerUnreadable;
}
GameLevelStageObservation ReadCurrentGameLevelStage(uintptr_t, std::uint32_t*) {
    return GameLevelStageObservation::GameUnreadable;
}
GameItemPoolObservation ReadCurrentGameItemPool(uintptr_t, void**) {
    return GameItemPoolObservation::GameUnreadable;
}
GameIsGreedModeObservation ObserveGameIsGreedMode(uintptr_t, uintptr_t) {
    return GameIsGreedModeObservation::MethodUnavailable;
}
GameIsAscentObservation ObserveLevelIsAscent(uintptr_t, uintptr_t) {
    return GameIsAscentObservation::MethodUnavailable;
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

// 注入进来的 Lua 脚本（Python 侧把下面这个原始字符串的占位换成脚本正文）。
// ★ 别在别处再写那个占位符 —— 替换是全文 `str.replace`，注释里出现一次就会把字符串截断。
const char* kScriptTemplate = R"lua(@SCRIPT@)lua";

// --- 伪造的引擎内存 ---------------------------------------------------------
//
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_Game 变量（槽里是**变量地址**，不是对象）
//   g_Game 变量                              = Game*
//   Game + kGameHudObjectOffset + kHudVisibleFlagOffset = HUD 的可见字节
constexpr std::size_t kHudFlagOffset = kGameHudObjectOffset + kHudVisibleFlagOffset;

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameSlotBytes;
std::vector<unsigned char> g_GameBytes;
std::uintptr_t g_EngineBase = 0;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void CreateBlocks() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameSlotBytes.assign(sizeof(std::uint64_t), 0);
    // Game 块要一直盖住 HUD 的可见字节（HUD 是 Game 的内嵌子对象）。
    g_GameBytes.assign(kHudFlagOffset + 8, 0);
    g_EngineBase = AddressOf(g_ModuleBytes);
}

void PublishGame() {
    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_GameSlotBytes));
    WriteAt<std::uint64_t>(g_GameSlotBytes, 0, AddressOf(g_GameBytes));
}

//: 引擎默认是"可见"。脚本第一帧要把它藏起来 —— 藏成功了第一帧读回就该是 0。
constexpr std::uint8_t kInitiallyVisible = 1;

void PublishHudFlag(std::uint8_t value) {
    WriteAt<std::uint8_t>(g_GameBytes, kHudFlagOffset, value);
}

unsigned ReadHudFlag() {
    return static_cast<unsigned>(g_GameBytes[kHudFlagOffset]);
}

bool ExpectGlobal(const char* name, double expected) {
    double value = 0.0;
    if (!LuaRuntime::ReadLuaGlobalNumber(name, &value)) {
        std::printf("HUD_FAIL: global %s was never written\n", name);
        return false;
    }
    if (value != expected) {
        std::printf("HUD_FAIL: %s expected %.0f, got %.0f\n", name, expected, value);
        return false;
    }
    return true;
}

} // namespace

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const std::string scenario = argv[1];
    if (scenario != "with_engine" && scenario != "no_base") return 91;
    const bool withEngine = scenario == "with_engine";

    CreateBlocks();
    if (withEngine) {
        LuaRuntime::SetEngineModuleBase(g_EngineBase);
        PublishGame();
        PublishHudFlag(kInitiallyVisible);
    }

    const std::string script = "SCENARIO = '" + scenario + "'\n" + kScriptTemplate;
    const auto result =
        LuaRuntime::InitializeFromBuffer(script.c_str(), script.size(), "@hud.lua");
    if (result != LuaRuntime::LuaInitResult::Success) {
        std::printf("HUD_FAIL: the Lua state did not initialize\n");
        return 2;
    }

    // 第一帧：脚本把 HUD 藏起来（`SetVisible(false)`）。藏成功 ⇒ 引擎那一格必须是 0。
    LuaRuntime::DispatchPostUpdate();
    if (LuaRuntime::TakeCallbackError()) {
        std::printf("HUD_FAIL: the Lua callback raised an error on the first frame\n");
        return 1;
    }
    const unsigned firstFrameFlag = ReadHudFlag();
    if (withEngine && firstFrameFlag != 0) {
        std::printf("HUD_FAIL: SetVisible(false) did not reach the engine byte (flag=%u)\n",
                    firstFrameFlag);
        return 1;
    }

    // 第二帧：脚本先复核"藏起来这件事跨帧仍然成立"（读同一格），再放回去。
    LuaRuntime::DispatchPostUpdate();
    if (LuaRuntime::TakeCallbackError()) {
        std::printf("HUD_FAIL: the Lua callback raised an error on the second frame\n");
        return 1;
    }
    const unsigned secondFrameFlag = ReadHudFlag();
    if (withEngine && secondFrameFlag != 1) {
        std::printf("HUD_FAIL: SetVisible(true) did not reach the engine byte (flag=%u)\n",
                    secondFrameFlag);
        return 1;
    }

    if (!ExpectGlobal("HUD_OK", 1.0)) return 1;
    std::printf("HUD_OK scenario=%s frame1_flag=%u frame2_flag=%u\n", scenario.c_str(),
                firstFrameFlag, secondFrameFlag);
    return 0;
}
'''

SCRIPT = r'''
local mod = RegisterMod('HUD visibility probe', 1)

local function check(condition, message)
  if not condition then error(message, 2) end
end

local function describe(value)
  if value == nil then return 'nil' end
  return type(value) .. ':' .. tostring(value)
end

--: 错误文本里必须出现 API 名字（MCM 用的是光秃秃的顺序语句，出错时唯一的线索就是这句文本）。
local function rejects(call, apiName, what)
  local ok, failure = pcall(call)
  check(not ok, what .. ' must raise, but it succeeded')
  check(string.find(tostring(failure), apiName, 1, true) ~= nil,
        what .. ' must name the API in its error, got ' .. tostring(failure))
end

local function verifySurface()
  local game = Game()
  local hud = game:GetHUD()
  check(hud ~= nil, 'Game:GetHUD() must return a HUD object, got ' .. describe(hud))
  check(game:GetHUD() ~= nil, 'Game:GetHUD() must be callable repeatedly')
  -- `Game:GetHUD` 不接受参数（PC 契约 `Game.md:279` 的 `HUD GetHUD ( )`）。
  rejects(function() return game:GetHUD(1) end, 'GetHUD', 'Game:GetHUD with an argument')

  -- `IsVisible`/`SetVisible` 的参数口径。
  rejects(function() return hud:IsVisible(1) end, 'IsVisible', 'HUD:IsVisible with an argument')
  rejects(function() return hud:SetVisible(false, false) end, 'SetVisible',
          'HUD:SetVisible with two arguments')

  -- 拿别的对象当 self：`luaL_checkudata` 必须拦下来（别静默读错内存）。
  --   HUD 的方法在元表的 `__index` 表里 ⇒ 可以当成字段取出来，再故意喂一个 Game 句柄当 self。
  local isVisible = hud.IsVisible
  check(type(isVisible) == 'function',
        'HUD.IsVisible must be reachable as a field, got ' .. describe(isVisible))
  local wrongSelf = pcall(isVisible, game)
  check(not wrongSelf, 'HUD:IsVisible must reject a Game handle as self')
end

local function verifyWithEngine()
  local hud = Game():GetHUD()

  -- ① 伪造内存里引擎默认是"可见"（`kInitiallyVisible = 1`）。
  check(hud:IsVisible() == true,
        'IsVisible must read the engine byte (expected true), got ' .. describe(hud:IsVisible()))

  -- ② 藏起来 ⇒ 引擎那一格变 0（C++ 侧在本帧结束后直接读那块伪造内存复核）。
  hud:SetVisible(false)
  check(hud:IsVisible() == false,
        'SetVisible(false) must clear the engine byte, got ' .. describe(hud:IsVisible()))

  -- ③ ★ 缺省参数按 PC 契约就是 `false`（`HUD.md:56` 的 `boolean Visible = false`）：
  --    "省略"必须等于"藏起来"，不是"什么都不做"。先把状态置回 true 再验。
  hud:SetVisible(true)
  check(hud:IsVisible() == true, 'SetVisible(true) must set the engine byte')
  hud:SetVisible()
  check(hud:IsVisible() == false,
        'SetVisible() without an argument must default to false (PC contract)')
  hud:SetVisible(nil)
  check(hud:IsVisible() == false, 'SetVisible(nil) must behave like false')
  -- 序号小计：现在那一格是 0（C++ 侧第一帧读回 0）。

  PHASE = 1
end

local function verifyWithoutEngine()
  local hud = Game():GetHUD()
  -- 没有引擎基址（加载期 / Hook 还没装）：读给 false，写安静返回 —— 一条都不许报错。
  check(hud:IsVisible() == false,
        'without an engine base IsVisible must degrade to false, got '
        .. describe(hud:IsVisible()))
  local ok, failure = pcall(function() hud:SetVisible(false) end)
  check(ok, 'SetVisible must stay silent without an engine base: ' .. tostring(failure))
  local okTrue, failureTrue = pcall(function() hud:SetVisible(true) end)
  check(okTrue, 'SetVisible(true) must stay silent too: ' .. tostring(failureTrue))
  -- 句柄本身仍然可用（每次调用重新解析，不缓存指针）。
  check(Game():GetHUD() ~= nil, 'GetHUD must keep working without an engine base')
  PHASE = 1
end

local frame = 0

mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function()
  frame = frame + 1
  if frame == 1 then
    verifySurface()
    if SCENARIO == 'with_engine' then
      verifyWithEngine()
    else
      verifyWithoutEngine()
    end
  elseif frame == 2 and SCENARIO == 'with_engine' then
    local hud = Game():GetHUD()
    -- ★ 跨帧复核：第一帧写进引擎内存的 0 必须还在（证明写的是引擎那一格，
    --   不是某个每帧重建的缓存）。
    check(hud:IsVisible() == false,
          'the byte written in the previous frame must still read false')
    hud:SetVisible(true)
    check(hud:IsVisible() == true, 'SetVisible(true) must set the engine byte')
    HUD_OK = 1
  elseif frame == 2 then
    HUD_OK = 1
  end
end)
'''
