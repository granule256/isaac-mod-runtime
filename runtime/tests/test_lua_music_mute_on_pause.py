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


class LuaMusicMuteOnPauseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-music-")
        temporary = Path(cls.temporary.name)
        compatibility = temporary / "compatibility"
        compatibility.mkdir()
        (compatibility / "stdfloat").write_text(
            "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n"
        )
        harness = temporary / "lua_music_harness.cpp"
        harness.write_text(
            r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "game_file_reader.hpp"

#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>

namespace {
bool g_Paused = false;
unsigned g_PauseCalls = 0;
unsigned g_ResumeCalls = 0;
// 批次 137（2026-09-26）：`MusicManager:UpdateVolume()` 的宿主实现。与 `Pause`/`Resume` 同一手法 ——
// 用**本进程的真函数**当"引擎方法"，于是"到底有没有调到、x0 收到的是不是 Manager 派生的 Music
// 对象"这两件事在宿主上也能被断言（真机上是 16 字节入口守卫后跳进引擎）。
unsigned g_UpdateVolumeCalls = 0;
std::uintptr_t g_LastUpdateVolumeMusic = 0;
// 批次 138（2026-09-26）：`MusicManager:Play(ID, Volume)` 的宿主实现 —— 记下 **ID 与 Volume 是否
// 原样到达**（`Play` 的第 2 个参数是浮点，走 `s0`，与整数参数各走各的寄存器：这条断言钉的就是
// "我们没有把它当整数传"）。
unsigned g_PlayCalls = 0;
int g_PlayIds[4] = {0, 0, 0, 0};
float g_PlayVolumes[4] = {0.0F, 0.0F, 0.0F, 0.0F};
std::uintptr_t g_LastPlayMusic = 0;
struct alignas(uintptr_t) Manager { unsigned char padding[0x36068]; int musicId; } g_Manager{};
std::string g_ModRoot;

bool ReadHostFile(const std::string& path, std::string* output) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) return false;
    output->assign(std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>());
    return !output->empty();
}
}

GameIsPausedObservation ObserveGameIsPaused(uintptr_t ownerSlot, uintptr_t thunk) {
    if (ownerSlot != 0x1111 || thunk != 0x2222) return GameIsPausedObservation::ThunkUnavailable;
    return g_Paused ? GameIsPausedObservation::PausedTrue : GameIsPausedObservation::PausedFalse;
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

int CurrentMusicId(const void* music) { return *reinterpret_cast<const int*>(music); }
void PauseMusic(void*) { ++g_PauseCalls; }
void ResumeMusic(void*) { ++g_ResumeCalls; }
void UpdateVolumeMusic(void* music) {
    ++g_UpdateVolumeCalls;
    g_LastUpdateVolumeMusic = reinterpret_cast<std::uintptr_t>(music);
}
void PlayMusic(void* music, int id, float volume) {
    if (g_PlayCalls < 4) {
        g_PlayIds[g_PlayCalls] = id;
        g_PlayVolumes[g_PlayCalls] = volume;
    }
    ++g_PlayCalls;
    g_LastPlayMusic = reinterpret_cast<std::uintptr_t>(music);
}

namespace GameFileReader {
TextReadResult ReadTextFile(const Bindings&, const char* path, u8* buffer,
                            std::size_t capacity, std::size_t* length) {
    constexpr char prefix[] = "rom:/isaac_mods/mods/MuteOnPause/";
    if (path == nullptr || buffer == nullptr || length == nullptr ||
        std::strncmp(path, prefix, sizeof(prefix) - 1) != 0) {
        return TextReadResult::InvalidArgument;
    }
    std::fprintf(stderr, "read=%s\n", path);
    std::string source;
    if (!ReadHostFile(g_ModRoot + "/" + (path + sizeof(prefix) - 1), &source)) {
        return TextReadResult::OpenFailed;
    }
    if (source.size() > capacity) return TextReadResult::LengthOutOfRange;
    std::memcpy(buffer, source.data(), source.size());
    *length = source.size();
    return TextReadResult::Success;
}
}

int main(int argc, char** argv) {
    const bool realHold = argc >= 2 && std::strcmp(argv[1], "real_hold") == 0;
    const bool realResume = argc >= 2 && std::strcmp(argv[1], "real_resume") == 0;
    const bool realMod = realHold || realResume;
    if ((!realMod && argc != 2) || (realMod && argc != 3)) return 90;
    LuaRuntime::SetGameBindings(0x1111, 0x2222);
    LuaRuntime::SetMusicBindings(reinterpret_cast<uintptr_t>(&CurrentMusicId),
                                 reinterpret_cast<uintptr_t>(&PauseMusic),
                                 reinterpret_cast<uintptr_t>(&ResumeMusic));
    // 批次 137：`MusicManager:UpdateVolume()` 的单方法绑定（与上面那三条同一个发布形态）。
    LuaRuntime::SetMusicUpdateVolumeBinding(reinterpret_cast<uintptr_t>(&UpdateVolumeMusic));
    // 批次 138：`MusicManager:Play(ID, Volume)` 的单方法绑定（同上）。
    LuaRuntime::SetMusicPlayBinding(reinterpret_cast<uintptr_t>(&PlayMusic));
    const char* script = nullptr;
    std::string realEntry;
    if (std::strcmp(argv[1], "outside") == 0) {
        script = "local music=MusicManager(); music:GetCurrentMusicID()";
    } else if (std::strcmp(argv[1], "outside_update_volume") == 0) {
        // 批次 137：托管回调之外调用 `UpdateVolume` 必须**报错**（原生绑定只在回调里可用），
        // 与 `GetCurrentMusicID` 同口径 —— 绝不允许"静默假装成功"。
        script = "local music=MusicManager(); music:UpdateVolume()";
    } else if (std::strcmp(argv[1], "outside_play") == 0) {
        // 批次 138：同样的口径，`Play(ID, Volume)` 在回调之外也必须报错。
        script = "local music=MusicManager(); music:Play(7, 1)";
    } else if (std::strcmp(argv[1], "play") == 0) {
        // 批次 138：`Play(ID, Volume)` 的**消费者视角**判据 —— 照模组写法调两次：
        // 一次省缺 Volume（PC 默认 1）、一次给 0.5。ID 与 Volume 都要原样到达引擎。
        script = "local mod=RegisterMod('Play',1); local music=MusicManager(); "
                 "mod:AddCallback(ModCallbacks.MC_POST_RENDER,function() "
                 "music:Play(7); music:Play(9, 0.5); end)";
    } else if (std::strcmp(argv[1], "play_type") == 0) {
        // 批次 138：参数**类型**错必须报错并现拼方法名；`Play()`（少给 ID）也要报错。
        script = "local mod=RegisterMod('PlayType',1); "
                 "mod:AddCallback(ModCallbacks.MC_POST_UPDATE,function() end); "
                 "local music=MusicManager(); "
                 "local ok1,err1=pcall(function() return music:Play('x') end); "
                 "if ok1 then error('Play(string) must be rejected') end; "
                 "if not string.find(tostring(err1),'Music:Play accepts',1,true) "
                 "then error('wrong message: '..tostring(err1)) end; "
                 "local ok2=pcall(function() return music:Play(1,'x') end); "
                 "if ok2 then error('Play(1, string) must be rejected') end; "
                 "local ok3=pcall(function() return music:Play() end); "
                 "if ok3 then error('Play() must be rejected') end";
    } else if (std::strcmp(argv[1], "arity") == 0) {
        // 批次 137：参数个数不对时必须报错、且消息里现拼出方法名（与手写时代逐字一致）。
        // 脚本要登记一个 `MC_POST_UPDATE` 回调，否则运行时按设计判 `MissingPostUpdateCallback`
        // （那与本次要验的事情无关，见 `LuaInitResult` 的最后一个枚举）。
        script = "local mod=RegisterMod('Arity',1); "
                 "mod:AddCallback(ModCallbacks.MC_POST_UPDATE,function() end); "
                 "local music=MusicManager(); "
                 "local ok,err=pcall(function() return music:UpdateVolume(1) end); "
                 "if ok then error('UpdateVolume(1) must be rejected') end; "
                 "if not string.find(tostring(err),'Music:UpdateVolume accepts no arguments',1,true) "
                 "then error('wrong message: '..tostring(err)) end";
    } else if (std::strcmp(argv[1], "mod_fields") == 0) {
        script = "local mod=RegisterMod('Fields',1); function mod:run() return 7 end; "
                 "if type(mod.run)~='function' or mod:run()~=7 then error('mod field mismatch') end; "
                 "mod:AddCallback(ModCallbacks.MC_POST_RENDER,mod.run)";
    } else if (std::strcmp(argv[1], "separate") == 0) {
        script = "local mod=RegisterMod('Probe',1); local update=0; local render=0; "
                 "mod:AddCallback(ModCallbacks.MC_POST_UPDATE,function() update=update+1 end); "
                 "mod:AddCallback(ModCallbacks.MC_POST_RENDER,function() render=render+1; "
                 "if update~=1 or render~=1 then error('phase mismatch') end end)";
    } else if (!realMod) {
        script = "local mod=RegisterMod('Mute on Pause',1); local game=Game(); local music=MusicManager(); "
                 "if type(music)~='userdata' then error('not userdata') end; local wasPaused=false; local storedTrack=nil; "
                 "mod:AddCallback(ModCallbacks.MC_POST_RENDER,function() local isPaused=game:IsPaused(); "
                 "if isPaused and not wasPaused then storedTrack=music:GetCurrentMusicID(); music:Pause(); "
                 "elseif not isPaused and wasPaused then if storedTrack and storedTrack~=Music.MUSIC_NULL then music:Resume() end end; "
                 "wasPaused=isPaused; music:UpdateVolume(); RuntimeTest.MarkPostUpdate() end)";
    }
    LuaRuntime::LuaInitResult init = LuaRuntime::LuaInitResult::ScriptLoadFailed;
    if (realMod) {
        g_ModRoot = argv[2];
        if (!ReadHostFile(g_ModRoot + "/main.lua", &realEntry)) return 91;
        init = LuaRuntime::InitializeManifestMod(
            realEntry.data(), realEntry.size(), "@rom:/isaac_mods/main.lua",
            "rom:/isaac_mods/mods/MuteOnPause", GameFileReader::Bindings{});
    } else {
        init = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@mute.lua");
    }
    if (std::strcmp(argv[1], "outside") == 0 ||
        std::strcmp(argv[1], "outside_update_volume") == 0 ||
        std::strcmp(argv[1], "outside_play") == 0) {
        return init == LuaRuntime::LuaInitResult::ScriptRunFailed ? 0 : 1;
    }
    if (init != LuaRuntime::LuaInitResult::Success) {
        std::fprintf(stderr, "init=%u\n", static_cast<unsigned>(init));
        return 2;
    }
    if (std::strcmp(argv[1], "mod_fields") == 0) return 0;
    if (std::strcmp(argv[1], "arity") == 0) return 0;
    if (std::strcmp(argv[1], "play_type") == 0) return 0;
    if (std::strcmp(argv[1], "play") == 0) {
        // 批次 138：一帧里调两次（`Play(7)` 与 `Play(9, 0.5)`）。三条都要成立：
        // ① 两次都到达引擎；② ID 原样；③ **Volume 走浮点寄存器**（省缺 ⇒ 1.0，给定 ⇒ 0.5）；
        // ④ 接收者仍是 Manager 派生的那个 Music 对象。
        const std::uintptr_t expectedMusic = reinterpret_cast<std::uintptr_t>(&g_Manager.musicId);
        if (LuaRuntime::TakeCallbackError()) return 3;
        LuaRuntime::DispatchPostRender(reinterpret_cast<uintptr_t>(&g_Manager));
        if (LuaRuntime::TakeCallbackError()) return 4;
        const bool ok = g_PlayCalls == 2 && g_PlayIds[0] == 7 && g_PlayVolumes[0] == 1.0F &&
                        g_PlayIds[1] == 9 && g_PlayVolumes[1] == 0.5F &&
                        g_LastPlayMusic == expectedMusic;
        return ok ? 0 : 5;
    }
    if (std::strcmp(argv[1], "separate") == 0) {
        LuaRuntime::DispatchPostUpdate();
        LuaRuntime::DispatchPostRender(reinterpret_cast<uintptr_t>(&g_Manager));
        return LuaRuntime::TakeCallbackError() ? 3 : 0;
    }
    g_Manager.musicId = 7;
    LuaRuntime::DispatchPostRender(reinterpret_cast<uintptr_t>(&g_Manager));
    g_Paused = true;
    LuaRuntime::DispatchPostRender(reinterpret_cast<uintptr_t>(&g_Manager));
    LuaRuntime::DispatchPostRender(reinterpret_cast<uintptr_t>(&g_Manager));
    if (realHold) {
        return g_PauseCalls == 1 && g_ResumeCalls == 0 && !LuaRuntime::TakeCallbackError() ? 0 : 5;
    }
    g_Paused = false;
    LuaRuntime::DispatchPostRender(reinterpret_cast<uintptr_t>(&g_Manager));
    // 批次 137：`UpdateVolume` 每一帧都被调一次（回调里无条件调）⇒ 4 次；而且 x0 收到的必须是
    // Manager 派生的那个 Music 对象（`manager + kManagerMusicOffset`，即 `&g_Manager.musicId`）
    // —— 这两条一起证明"绑定真的接到了、接收者也没解错"。
    // `realMod`（未改动的 MuteOnPause）不调 `UpdateVolume`，所以那两条只在内嵌脚本路径上核对。
    const bool updateVolumeOk =
        realMod || (g_UpdateVolumeCalls == 4 &&
                    g_LastUpdateVolumeMusic == reinterpret_cast<std::uintptr_t>(&g_Manager.musicId));
    return g_PauseCalls == 1 && g_ResumeCalls == 1 && updateVolumeOk &&
                   !LuaRuntime::TakeCallbackError()
               ? 0
               : 4;
}
'''.lstrip()
        )

        lua_root = SOURCE / "third_party/lua-5.3.3/src"
        excluded = {"lua.c", "luac.c", "liolib.c", "loslib.c", "loadlib.c", "ldblib.c", "linit.c"}
        lua_objects = []
        for lua_source in sorted(lua_root.glob("*.c")):
            if lua_source.name in excluded:
                continue
            output = temporary / (lua_source.stem + ".o")
            build = subprocess.run(
                ["cc", "-std=c99", "-w", "-DLUA_C89_NUMBERS", "-I", str(lua_root), "-c", str(lua_source), "-o", str(output)],
                text=True, capture_output=True,
            )
            if build.returncode != 0:
                raise AssertionError(build.stdout + build.stderr)
            lua_objects.append(output)

        cls.harness = temporary / "lua_music_harness"
        build = subprocess.run(
            ["c++", "-std=c++23", "-Wall", "-Wextra", "-Werror", "-DLUA_C89_NUMBERS",
             "-DEXL_LAYERED_RUNTIME=1", "-DEXL_LOAD_KIND=Module",
             "-DEXL_LOAD_KIND_ENUM=2", "-DEXL_PROGRAM_ID=0",
             "-I", str(compatibility), "-I", str(SOURCE), "-I", str(SOURCE.parent / "src"),
             "-I", str(lua_root), str(harness),
             *(str(path) for path in layered_lua_runtime_sources(SOURCE)),
             *(str(path) for path in lua_objects), "-lm", "-o", str(cls.harness)],
            text=True, capture_output=True,
        )
        if build.returncode != 0:
            raise AssertionError(build.stdout + build.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_harness(self, scenario, *arguments):
        result = subprocess.run([str(self.harness), scenario, *arguments], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_music_manager_is_no_pointer_userdata_and_runs_mute_on_pause_edges(self):
        self.run_harness("mute")

    def test_post_update_and_post_render_callbacks_are_independent(self):
        self.run_harness("separate")

    def test_music_api_is_rejected_outside_a_managed_render_callback(self):
        self.run_harness("outside")

    def test_update_volume_is_rejected_outside_a_managed_render_callback(self):
        """★ 批次 137（2026-09-26）：`MusicManager:UpdateVolume()` 的消费者视角边界判据。

        The Specialist for Good Items 的"捡到四级物品放歌"要在托管回调里调它：
          * 回调里 ⇒ 真的到达引擎（宿主注入的真函数被调到，且 `x0` = Manager 派生的 Music 对象，
            见 `test_music_manager_is_no_pointer_userdata_and_runs_mute_on_pause_edges`）；
          * 回调外 ⇒ 必须**报错**（与 `GetCurrentMusicID` 同口径），不许静默假装成功；
          * 参数个数不对 ⇒ 必须报错、消息里现拼出方法名。
        """
        self.run_harness("outside_update_volume")
        self.run_harness("arity")

    def test_play_reaches_the_engine_with_the_id_and_a_float_volume(self):
        """★ 批次 138（2026-09-26）：`MusicManager:Play(ID, Volume = 1)` 的消费者视角边界判据。

        The Specialist for Good Items 放歌走的就是这一条（`main.lua:483/489/494` 的
        `MusicManager():Play(id, 1)`）：
          * 回调里 ⇒ 两次调用都到达引擎，ID 原样、**Volume 走浮点寄存器**（省缺 1.0 / 给定 0.5），
            接收者是 Manager 派生的那个 Music 对象；
          * 回调外 ⇒ 必须报错（不许静默假装成功）；
          * ID/Volume 类型错、少给 ID ⇒ 必须报错且消息里现拼出 `Music:Play accepts`。
        """
        self.run_harness("play")
        self.run_harness("outside_play")
        self.run_harness("play_type")

    def test_register_mod_supports_custom_method_fields(self):
        self.run_harness("mod_fields")

    def test_unmodified_mute_on_pause_holds_music_while_pause_state_stays_true(self):
        self.run_harness("real_hold", str(ROOT / "runtime" / "pc-mods" / "MuteOnPause"))

    def test_unmodified_mute_on_pause_resumes_after_a_false_render_state(self):
        self.run_harness("real_resume", str(ROOT / "runtime" / "pc-mods" / "MuteOnPause"))

    def test_music_bindings_are_guarded_and_userdata_has_no_native_address(self):
        """The handle stays pointer-free and the method guards stay in the legacy unit.

        `MusicHandle` and the Music handlers moved to the shared transitional header
        and the `music_api.cpp` family unit; the byte guards and the Manager-derived
        object resolution still live in `lua_runtime.cpp` behind the accessors the
        family unit calls.
        """
        legacy = (SOURCE / "lua_runtime.cpp").read_text(encoding="utf-8")
        handles = (SOURCE / "lua_object_handles.hpp").read_text(encoding="utf-8")
        music_api = (
            SOURCE.parent / "src" / "interfaces" / "lua" / "music_api.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("struct MusicHandle {\n    std::uint8_t reserved;\n};", handles)
        self.assertNotIn("uintptr_t", handles[handles.index("struct MusicHandle"):handles.index("struct RngHandle")])
        self.assertIn("Music:GetCurrentMusicID native bindings are unavailable", music_api)
        self.assertIn("kManagerMusicOffset", legacy)
        self.assertIn("ValidateMusicMethod", legacy)
        for accessor in ("ResolveMusicGetCurrentMusicId", "ResolveMusicPause", "ResolveMusicResume",
                         "ResolveMusicUpdateVolume", "ResolveMusicPlay"):
            with self.subTest(accessor=accessor):
                self.assertIn(accessor, music_api)
                self.assertIn(accessor, legacy)
        # 批次 137/138：两条单方法发布点（与 `SetMusicBindings` 分开，见 `lua_runtime.hpp`）。
        self.assertIn("MusicUpdateVolumeThunk", music_api)
        self.assertIn("kMusicUpdateVolumeExpectedBytes", legacy)
        self.assertIn("MusicPlayThunk", music_api)
        self.assertIn("kMusicPlayExpectedBytes", legacy)


if __name__ == "__main__":
    unittest.main()
