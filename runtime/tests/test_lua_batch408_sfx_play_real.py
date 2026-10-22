"""门禁：`SFXManager:Play` 从**空实现**升级成**真调引擎**（批次 408，2026-10-08）。

## 这一批是什么

真机上所有模组的音效都是哑的 —— 因为批次 045 只补了"`SFXManager()` 对象与 `Play` 方法都在、
调用不报错"，`Play` 一直是**明确的空实现**（`return 0;`）。中文版 MCM 在"房间不安全"时应当响
`SOUND_BOSS2INTRO_ERRORBUZZ`（`dist/mcm-card-20261007/scripts/modconfig.lua:136`：
`SFXManager():Play(SoundEffect.SOUND_BOSS2INTRO_ERRORBUZZ, 0.75, 0, false, 1)`），用户实测
**一点声音都没有** ⇒ "打不开"看起来像"毫无反应"。

本批把同一族 `IsPlaying`（批次 185）的那套"真调引擎"照搬到 `Play`：
引擎入口 `SoundEffects::Play(eSoundEffect, float, int, bool, float, float)` @ `0x4A2FD0`
（三条独立证据 + 16 字节指纹见 `runtime_constants.hpp` 的批次 408 段；PC 契约
`tools/pc_contract_docs/SFXManager.md:53`）。

## 宿主验到了什么、没验到什么

* **验到**：三道守卫的接线、参数被**按契约顺序**递进引擎（`x0=音效子对象`、
  `w1=ID`、`s0=Volume`、`w2=FrameDelay`、`w3=Loop`、`s1=Pitch`、`s2=Pan`）、缺省值、
  形状**只钉"至少一个整数"**（不因多给参数/参数类型怪报错）、取不到入口时**安静 no-op**。
* **没验**：声音真的响不响（引擎侧副作用只有真机给，作业单里已登记）。宿主"引擎"是
  `music_api.cpp` 里那套 `extern "C"` 探针 + 一个**本进程的真函数**假冒 `SoundEffects::Play`。

## 判据分层

* 行为（宿主 harness）：`Play` 的实参顺序、缺省值、形状、no-op 降级。
* 静态接线：常量两两点名、处理器走 `EngineOffsetAddress` + `ResolveSoundEffectsPlayForCall`、
  `IsPlaying` 段里"`Play` 是空实现"的过时描述已更新、探针符号被读数工具登记。
* 镜像：`kSoundEffectsPlayExpectedBytes` 与 `Repentance.nro` 同偏移逐字节一致（本该
  `tools/verify_runtime_constants_against_nro.py` 覆盖，这里再钉一次，以免常量被改脏）。
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import build_lua_harness
except ImportError:
    from test_support import build_lua_harness

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
MUSIC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "music_api.cpp"
LUA_RUNTIME = ROOT / "runtime" / "source" / "lua_runtime.cpp"
LUA_RUNTIME_STATE = ROOT / "runtime" / "source" / "lua_runtime_state.hpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
GDB_TOOL = ROOT / "tools" / "read_device_state_via_gdb.py"
NRO = (ROOT / "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
       / "Program #0" / "1" / ".nro" / "Repentance.nro")

#: `SoundEffects::Play(eSoundEffect, float, int, bool, float, float)` @ `0x4A2FD0`（取证在常量段）。
PLAY_OFFSET = 0x4A2FD0
PLAY_ENTRY = bytes.fromhex("ff0302d1ea0b00fde923026dfd7b03a9")


HARNESS = r'''
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"

#include <atomic>
#include <cstdint>
#include <cstring>

// 批次 408：`SFXManager:Play` 的探针（`extern "C"`，定义在 `music_api.cpp`）。
// 宿主直接读它们做断言 —— 它们本身就是读数工具按符号直读的那几格。
extern "C" {
extern std::atomic<std::uint32_t> g_SfxPlayCalls;
extern std::atomic<std::uint32_t> g_SfxPlayDelivered;
extern std::atomic<std::uint32_t> g_SfxPlayLastId;
extern std::atomic<std::uint32_t> g_SfxPlayLastVolume;
extern std::atomic<std::uint32_t> g_SfxPlayLastFrameDelay;
extern std::atomic<std::uint32_t> g_SfxPlayLastLoop;
extern std::atomic<std::uint32_t> g_SfxPlayLastPitch;
extern std::atomic<std::uint32_t> g_SfxPlayLastPan;
extern std::atomic<std::uint32_t> g_SfxPlayLastFailure;
}

namespace {

// 假 Manager：块要盖住 `kManagerSoundEffectsOffset`（音效子对象就在这个偏移上）。
struct alignas(std::uintptr_t) ManagerBlock {
    unsigned char padding[kManagerSoundEffectsOffset + 0x40];
};
ManagerBlock g_Manager{};

// 假引擎 `SoundEffects::Play` 的实参记录（**按到来顺序逐条记**，验的就是"参数被按契约递进来"）。
unsigned g_PlayCalls = 0;
std::uintptr_t g_LastThis = 0;
std::int32_t g_LastId = 0;
float g_LastVolume = 0.0F;
std::int32_t g_LastFrameDelay = 0;
int g_LastLoop = -1;
float g_LastPitch = 0.0F;
float g_LastPan = 0.0F;

// ★ 签名必须与 `music_api.cpp` 里那个 `PlayFn` 逐字一致（这是"按契约顺序递参"的判据本身）。
void FakeSfxPlay(void* self, std::int32_t id, float volume, std::int32_t frameDelay, int loop,
                 float pitch, float pan) {
    ++g_PlayCalls;
    g_LastThis = reinterpret_cast<std::uintptr_t>(self);
    g_LastId = id;
    g_LastVolume = volume;
    g_LastFrameDelay = frameDelay;
    g_LastLoop = loop;
    g_LastPitch = pitch;
    g_LastPan = pan;
}

std::uint32_t Raw(std::atomic<std::uint32_t>& slot) {
    return slot.load(std::memory_order_relaxed);
}
float BitsToFloat(std::atomic<std::uint32_t>& slot) {
    const std::uint32_t bits = Raw(slot);
    float out = 0.0F;
    std::memcpy(&out, &bits, sizeof(out));
    return out;
}

std::uintptr_t ExpectedSoundEffects() {
    return reinterpret_cast<std::uintptr_t>(&g_Manager) + kManagerSoundEffectsOffset;
}

bool Near(float a, float b) {
    const float d = a - b;
    return (d < 0 ? -d : d) < 1e-6F;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    const bool noEngine = std::strcmp(scenario, "no_engine") == 0;
    if (!noEngine) {
        // 让 `base + kSoundEffectsPlayOffset` 正好等于那个**本进程的真函数** ⇒ 三道守卫都过。
        LuaRuntime::SetEngineModuleBase(
            reinterpret_cast<std::uintptr_t>(&FakeSfxPlay) - kSoundEffectsPlayOffset);
    }

    const char* script = nullptr;
    if (std::strcmp(scenario, "play_defaults") == 0) {
        // 只给 ID（PC 缺省：Volume=1 / FrameDelay=2 / Loop=false / Pitch=1 / Pan=0）。
        script = "local mod=RegisterMod('SfxDefaults',1); local sfx=SFXManager(); "
                 "mod:AddCallback(ModCallbacks.MC_POST_RENDER,function() sfx:Play(187) end)";
    } else if (std::strcmp(scenario, "play_full") == 0) {
        // 逐字照中文版 MCM 的现场调用：`Play(SOUND_BOSS2INTRO_ERRORBUZZ, 0.75, 0, false, 1)`。
        script = "local mod=RegisterMod('SfxFull',1); local sfx=SFXManager(); "
                 "mod:AddCallback(ModCallbacks.MC_POST_RENDER,function() "
                 "sfx:Play(187, 0.75, 0, false, 1) end)";
    } else if (std::strcmp(scenario, "play_args") == 0) {
        // 六个参数全给 + **多给一个**（第 7 个）：形状不许因此报错（不钉个数）。
        script = "local mod=RegisterMod('SfxArgs',1); local sfx=SFXManager(); "
                 "mod:AddCallback(ModCallbacks.MC_POST_RENDER,function() "
                 "sfx:Play(5, 0.5, 7, true, 1.5, -0.25, 99) end)";
    } else if (std::strcmp(scenario, "shape") == 0) {
        // 非整数 ID / 少给 ID：**必须报同一条错**；其余形状一律不报错。
        script = "local mod=RegisterMod('SfxShape',1); "
                 "mod:AddCallback(ModCallbacks.MC_POST_RENDER,function() end); "
                 "local sfx=SFXManager(); "
                 "local ok1,err1=pcall(function() return sfx:Play('x') end); "
                 "if ok1 then error('Play(string) must be rejected') end; "
                 "if not string.find(tostring(err1),'SFXManager:Play accepts a sound effect id',1,true) "
                 "then error('wrong message: '..tostring(err1)) end; "
                 "local ok2=pcall(function() return sfx:Play() end); "
                 "if ok2 then error('Play() must be rejected') end; "
                 "local ok3=pcall(function() return sfx:Play(1, 'x', 'y') end); "
                 "if not ok3 then error('Play(1,string,string) must NOT be rejected') end";
    } else if (noEngine) {
        script = "local mod=RegisterMod('SfxNoEngine',1); local sfx=SFXManager(); "
                 "mod:AddCallback(ModCallbacks.MC_POST_RENDER,function() sfx:Play(187, 0.75) end)";
    } else {
        return 91;
    }

    const auto init = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b408.lua");
    if (init != LuaRuntime::LuaInitResult::Success) return 2;

    if (std::strcmp(scenario, "shape") == 0) {
        return LuaRuntime::TakeCallbackError() ? 3 : 0;
    }

    LuaRuntime::DispatchPostRender(reinterpret_cast<std::uintptr_t>(&g_Manager));
    if (LuaRuntime::TakeCallbackError()) return 4;

    if (std::strcmp(scenario, "no_engine") == 0) {
        // 没发模块基址 ⇒ `EngineOffsetAddress` 返回 0 ⇒ 守卫①没过 ⇒ 安静 no-op（失败码 3）。
        const bool ok = g_PlayCalls == 0 && Raw(g_SfxPlayCalls) == 1 && Raw(g_SfxPlayDelivered) == 0 &&
                        Raw(g_SfxPlayLastFailure) == 3;
        return ok ? 0 : 5;
    }

    if (std::strcmp(scenario, "play_defaults") == 0) {
        const bool ok = g_PlayCalls == 1 && g_LastId == 187 && Near(g_LastVolume, 1.0F) &&
                        g_LastFrameDelay == 2 && g_LastLoop == 0 && Near(g_LastPitch, 1.0F) &&
                        Near(g_LastPan, 0.0F) && g_LastThis == ExpectedSoundEffects() &&
                        Raw(g_SfxPlayCalls) == 1 && Raw(g_SfxPlayDelivered) == 1 &&
                        Raw(g_SfxPlayLastFailure) == 0 && static_cast<std::int32_t>(Raw(g_SfxPlayLastId)) == 187;
        return ok ? 0 : 6;
    }
    if (std::strcmp(scenario, "play_full") == 0) {
        const bool ok = g_PlayCalls == 1 && g_LastId == 187 && Near(g_LastVolume, 0.75F) &&
                        g_LastFrameDelay == 0 && g_LastLoop == 0 && Near(g_LastPitch, 1.0F) &&
                        Near(g_LastPan, 0.0F) && g_LastThis == ExpectedSoundEffects() &&
                        Raw(g_SfxPlayDelivered) == 1;
        return ok ? 0 : 7;
    }
    if (std::strcmp(scenario, "play_args") == 0) {
        // 第 7 个参数（99）被忽略；前六个按契约顺序到达。
        const bool ok = g_PlayCalls == 1 && g_LastId == 5 && Near(g_LastVolume, 0.5F) &&
                        g_LastFrameDelay == 7 && g_LastLoop == 1 && Near(g_LastPitch, 1.5F) &&
                        Near(g_LastPan, -0.25F) && g_LastThis == ExpectedSoundEffects() &&
                        BitsToFloat(g_SfxPlayLastVolume) == g_LastVolume &&
                        BitsToFloat(g_SfxPlayLastPitch) == g_LastPitch &&
                        BitsToFloat(g_SfxPlayLastPan) == g_LastPan &&
                        static_cast<std::int32_t>(Raw(g_SfxPlayLastFrameDelay)) == 7 &&
                        Raw(g_SfxPlayLastLoop) == 1;
        return ok ? 0 : 8;
    }
    return 92;
}
'''


class SfxPlayBatch408Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b408-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario):
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    # ---------------------------------------------------------------- 行为（宿主）

    def test_defaults_match_the_pc_contract(self):
        """`Play(187)`：Volume=1 / FrameDelay=2 / Loop=false / Pitch=1 / Pan=0，接收者 = `Manager+0x364A8`。"""
        self.run_scenario("play_defaults")

    def test_mcm_call_reaches_the_engine_in_order(self):
        """逐字照 MCM 现场：`Play(187, 0.75, 0, false, 1)` —— 六个实参按契约顺序到达。"""
        self.run_scenario("play_full")

    def test_all_six_parameters_are_passed_and_extra_arity_is_tolerated(self):
        """六参全给 + 多给一个：前六个按序到达，多给的不报错（形状**不加严**）。"""
        self.run_scenario("play_args")

    def test_shape_only_pins_one_integer_argument(self):
        """非整数 ID / 少给 ID ⇒ 报同一条错；`Play(1, 'x', 'y')` **不许**报错（不钉个数/类型）。"""
        self.run_scenario("shape")

    def test_unavailable_engine_entry_is_a_silent_noop(self):
        """取不到引擎入口（基址没发布）⇒ **安静 no-op**（不报错、不假装成功），失败码记 3。"""
        self.run_scenario("no_engine")

    # ---------------------------------------------------------------- 静态接线

    def test_constants_and_handlers_are_wired(self):
        constants = CONSTANTS.read_text(encoding="utf-8")
        music_api = MUSIC_API.read_text(encoding="utf-8")
        runtime = LUA_RUNTIME.read_text(encoding="utf-8")
        state = LUA_RUNTIME_STATE.read_text(encoding="utf-8")

        self.assertIn("inline constexpr uintptr_t kSoundEffectsPlayOffset = 0x4A2FD0;", constants)
        self.assertIn("kSoundEffectsPlayExpectedBytes", constants)
        self.assertIn("kSoundEffectsPlayOffset", music_api)
        self.assertIn("ResolveSoundEffectsPlayForCall(method, &soundEffects, &failureCode)", music_api)
        # 引擎调用只走 `AsFunction`（解析 + 守卫在之前），不裸 `reinterpret_cast`。
        self.assertIn("engine_call::AsFunction<PlayFn>(method)", music_api)
        self.assertNotIn("reinterpret_cast<PlayFn>", music_api)
        # 接收者解析在旧 TU，且**换了指纹**（不复用 IsPlaying 的字节）。
        self.assertIn("ResolveSoundEffectsPlayForCall", state)
        self.assertIn("kSoundEffectsPlayExpectedBytes.data()", runtime)

    def test_is_playing_comment_is_no_longer_stale(self):
        """`IsPlaying` 段里那句"`Play` 是空实现"必须已被更正（只改注释、不删原文）。"""
        music_api = MUSIC_API.read_text(encoding="utf-8")
        self.assertIn("批次 408（2026-10-08）把 `Play` 也补上", music_api)
        # 旧措辞仍在（项目不许删除式精简），但被明确标成"过时"。
        self.assertIn("上面那句\"`Play` 是空实现\"到此为止已**过时**", music_api)

    def test_probe_symbols_are_registered_for_the_readout_tool(self):
        tool = GDB_TOOL.read_text(encoding="utf-8")
        for key in ("g_SfxPlayCalls", "g_SfxPlayDelivered", "g_SfxPlayLastId", "g_SfxPlayLastVolume",
                    "g_SfxPlayLastFrameDelay", "g_SfxPlayLastLoop", "g_SfxPlayLastPitch",
                    "g_SfxPlayLastPan", "g_SfxPlayLastFailure"):
            with self.subTest(key=key):
                self.assertIn(key, tool)

    def test_entry_bytes_match_the_game_image(self):
        """16 字节入口指纹必须与 `Repentance.nro` 逐字节一致（常量被改脏这里就红）。"""
        if not NRO.exists():
            self.skipTest("缺少本机镜像 Repentance.nro")
        actual = NRO.read_bytes()[PLAY_OFFSET:PLAY_OFFSET + 16]
        self.assertEqual(actual, PLAY_ENTRY,
                         f"Play 入口指纹不符：镜像 = {actual.hex()}、常量 = {PLAY_ENTRY.hex()}")


if __name__ == "__main__":
    unittest.main()
