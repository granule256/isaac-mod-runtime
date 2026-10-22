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


class LuaModPersistenceTests(unittest.TestCase):
    def test_event_diagnostic_wraps_all_mod_persistence_operations_after_validation(self):
        runtime = (
            SOURCE.parent / "src" / "interfaces" / "lua" / "mod_api.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn('#include "persistence_event_journal.hpp"', runtime)
        expectations = (
            ("ModSaveData", "SaveData", "ModPersistence::SaveModData"),
            ("ModLoadData", "LoadData", "ModPersistence::LoadModData"),
            ("ModHasData", "HasData", "ModPersistence::HasModData"),
            ("ModRemoveData", "RemoveData", "ModPersistence::RemoveModData"),
        )
        for function, operation, persistence_call in expectations:
            with self.subTest(function=function):
                signature = f"int {function}(lua_State* state) {{"
                body = runtime[runtime.index(signature) + len(signature):]
                body = body[:body.index("\n}\n") + 3]
                entered = "PersistenceEventJournal::Event::OperationEntered"
                returned = "PersistenceEventJournal::Event::OperationReturned"
                self.assertIn(entered, body)
                self.assertIn(returned, body)
                self.assertIn("PersistenceEventJournal::Operation::" + operation, body)
                self.assertLess(body.index(entered), body.index(persistence_call))
                self.assertLess(body.index(persistence_call), body.index(returned))
        self.assertIn("ModPersistence::Result::Missing", runtime)
        self.assertIn("*has = false", (SOURCE / "mod_persistence.hpp").read_text(encoding="utf-8"))

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-persistence-")
        cls.temporary_path = Path(cls.temporary.name)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_mod_persistence_contract_exists(self):
        header = SOURCE / "mod_persistence.hpp"
        mod_api = SOURCE.parent / "src" / "interfaces" / "lua" / "mod_api.cpp"

        self.assertTrue(header.is_file(), "mod persistence storage is missing")
        source = header.read_text(encoding="utf-8")
        for token in (
            "HashModNamespace",
            "SaveModData",
            "LoadModData",
            "HasModData",
            "RemoveModData",
            "ISMODST2",
            "SessionSaveFilePort",
            "kStateName",
        ):
            self.assertIn(token, source)
        for token in ("SaveData", "LoadData", "HasData", "RemoveData", "ModPersistence"):
            self.assertIn(token, mod_api.read_text(encoding="utf-8"))

    def test_persistence_port_is_wired_on_the_game_thread_before_any_read(self):
        """新不变量（2026-09-17 用户指令后）：注入点在**游戏线程**的模组加载路径上，
        而且"先开线程硬闸、再挂端口"；消费者在没端口时如实报「不可用」，不静默失败。

        旧版这条钉的是"原子发布标志先置位再读"，那套机制随 `IFilePort` 一起退休了 ——
        现在"能不能用"由**端口在不在**回答，"能不能碰卡"由适配器的硬闸回答。
        """
        consumer = (SOURCE / "mod_persistence.hpp").read_text(encoding="utf-8")
        self.assertIn("isaac::runtime::SessionSaveFilePort() != nullptr", consumer)
        self.assertIn("bool IsFileApiReady()", consumer)
        wiring = (SOURCE / "hook_manager.cpp").read_text(encoding="utf-8")
        gate = wiring.index("g_SaveFileAdapter.AllowFromGameThread();")
        inject = wiring.index("isaac::runtime::SetSessionSaveFilePort(&g_SaveFileAdapter);")
        self.assertLess(gate, inject, "必须先打开线程硬闸，再把它挂成会话默认端口")

    def test_retired_plugin_persistence_path_is_gone(self):
        """旧的"插件持久化"通道已退役（2026-09-17，用户批准）：源文件、构建目标、开关都不许回来。

        为什么钉"消失"而不是钉"能用"：这条旧路（运行时导出 `IsaacModRuntime_RegisterSaltyFileApi`、
        等 SaltyNX 插件把 `SaltySDCore_fopen` 一族传进来）与现在的"存档分区直写"
        （`ISaveFilePort` / `EngineSaveFileAdapter`）是**两份互不相干的持久化实现**，留着就会有人
        照着错的那条走。退役的代码与标注备份在 `docs/legacy-plugin-persistence-20260917/`。
        """
        for name in (
            "saltynx_external_plugin_persistence_bridge.cpp",
            "saltynx_external_plugin_persistence_bridge.hpp",
            "saltynx_external_plugin_persistence_bridge_trace.cpp",
            "saltynx_external_plugin_persistence_entry.cpp",
        ):
            with self.subTest(file=name):
                self.assertFalse((SOURCE / "program" / name).is_file(), f"{name} 又回到插件目录里了")

        makefile = (ROOT / "runtime" / "Makefile").read_text(encoding="utf-8")
        for token in (
            "SALTYNX_STAGE144",
            "SALTYNX_STAGE145",
            "mod-persistence-deploy",
            "mod-persistence-probe-deploy",
            "mod-persistence-probe-trace-deploy",
            "mod-persistence-event-diagnostic-deploy",
            "PERSISTENCE_REQUIRED",
            "-DEXL_PERSISTENCE_REQUIRED",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, makefile, f"Makefile 里还有退役线的痕迹：{token}")
        common = (ROOT / "runtime" / "misc" / "mk" / "common.mk").read_text(encoding="utf-8")
        self.assertNotIn("saltynx_external_plugin_persistence", common)

        legacy = ROOT / "docs" / "legacy-plugin-persistence-20260917"
        self.assertTrue((legacy / "README.md").is_file(), "退役代码的备份说明不见了（用户要求单独留一份）")
        for name in (
            "saltynx_external_plugin_persistence_bridge.cpp",
            "saltynx_external_plugin_persistence_bridge_trace.cpp",
            "saltynx_external_plugin_persistence_entry.cpp",
        ):
            with self.subTest(backup=name):
                self.assertTrue((legacy / "sources" / name).is_file(), f"备份里缺 {name}")

    def test_persistence_has_exactly_one_path(self):
        """持久化只有一条路：`ISaveFilePort` 会话端口（写存档分区），不再依赖任何插件文件 API。"""
        port = (ROOT / "runtime" / "src" / "ports" / "save_file_port.hpp").read_text(encoding="utf-8")
        for token in ("class ISaveFilePort", "SessionSaveFilePort", "SetSessionSaveFilePort"):
            with self.subTest(token=token):
                self.assertIn(token, port)
        consumer = (SOURCE / "mod_persistence.hpp").read_text(encoding="utf-8")
        self.assertIn("isaac::runtime::SessionSaveFilePort() != nullptr", consumer)
        for retired in ("SaltySDCore_fopen", "SaltySDCore_fread", "SaltySDCore_fwrite"):
            with self.subTest(retired=retired):
                self.assertNotIn(retired, consumer)

    def test_hardware_probe_uses_one_pc_mod_to_cover_save_load_and_remove(self):
        probe = ROOT / "runtime" / "diagnostic" / "mod-persistence-probe" / "pc-mods" / "00 Runtime Persistence Probe" / "main.lua"

        self.assertTrue(probe.is_file(), "persistence hardware probe Mod is missing")
        source = probe.read_text(encoding="utf-8")
        for token in ("RegisterMod", "HasData", "SaveData", "LoadData", "RemoveData"):
            self.assertIn(token, source)

    def test_mod_persistence_lua_contract(self):
        header = SOURCE / "mod_persistence.hpp"
        if not header.is_file():
            self.fail("mod persistence storage is missing")

        compatibility = self.temporary_path / "compatibility"
        compatibility.mkdir(exist_ok=True)
        (compatibility / "stdfloat").write_text(
            "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n",
            encoding="utf-8",
        )
        harness = self.temporary_path / "lua_mod_persistence_harness.cpp"
        harness.write_text(
            r'''
#include "lua_runtime.hpp"
#include "mod_persistence.hpp"
#include "game_file_reader.hpp"
#include "game_observer.hpp"

extern "C" {
#include <lua.h>
}

#include <array>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>

namespace {
std::map<std::string,std::string> g_files;
bool g_fail_write = false;

// 内存里的"存档分区"：实现统一端口 `ISaveFilePort`（2026-09-17 用户指令：所有持久化走存档分区、
// 消费者只认同一个接口）。这里不碰任何真实文件 —— 它证明消费者不依赖具体提供方。
class HarnessStore final : public isaac::runtime::ISaveFilePort {
public:
    [[nodiscard]] isaac::runtime::Status Read(std::string_view name, char* out, std::size_t capacity,
                                              std::size_t* size) noexcept override {
        if(size==nullptr) return isaac::runtime::Status{isaac::runtime::StatusCode::InvalidArgument};
        *size=0;auto it=g_files.find(std::string(name));
        if(it==g_files.end()) return isaac::runtime::Status{isaac::runtime::StatusCode::NotFound};
        *size=it->second.size();
        if(*size>capacity) return isaac::runtime::Status{isaac::runtime::StatusCode::CapacityExceeded};
        std::memcpy(out,it->second.data(),*size);return isaac::runtime::Status::Ok();
    }
    [[nodiscard]] isaac::runtime::Status Write(std::string_view name,
                                               std::string_view data) noexcept override {
        if(g_fail_write) return isaac::runtime::Status{isaac::runtime::StatusCode::IoFailure};
        g_files[std::string(name)]=std::string(data);return isaac::runtime::Status::Ok();
    }
    [[nodiscard]] isaac::runtime::Status Remove(std::string_view name) noexcept override {
        g_files.erase(std::string(name));return isaac::runtime::Status::Ok();
    }
    [[nodiscard]] isaac::runtime::Status Exists(const char*,bool* out) noexcept override {
        if(out) *out=!g_files.empty();return isaac::runtime::Status::Ok();
    }
};

HarnessStore g_store{};

void Configure() {
    // 唯一注入点：会话默认端口（生产里那一个是存档分区适配器，这里换成内存实现）。
    isaac::runtime::SetSessionSaveFilePort(&g_store);
    ModPersistence::ResetCacheForTesting();
}

void RefreshChecksum(std::string& file) {
    auto* p=reinterpret_cast<std::uint8_t*>(file.data());
    ModPersistence::detail::WriteU32(p+28,ModPersistence::detail::Checksum(p+32,file.size()-32));
}

}

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
    Configure();
    const char* scenario = argv[1];
    const char* script = nullptr;
    if (std::strcmp(scenario, "save") == 0) {
        script = "local m=RegisterMod('Persistent Probe',1); if m:HasData() or m:LoadData()~='' then error('empty') end; m:SaveData('{\"v\":1}'); if not m:HasData() or m:LoadData()~='{\"v\":1}' then error('save') end; m:AddCallback(ModCallbacks.MC_POST_UPDATE,function() end)";
    } else if (std::strcmp(scenario, "load_remove") == 0) {
        const auto key = ModPersistence::HashModNamespace("Persistent Probe", 16);
        if (ModPersistence::SaveModData(key, "previous", 8) != ModPersistence::Result::Success) return 10;
        ModPersistence::ResetCacheForTesting();
        script = "local m=RegisterMod('Persistent Probe',1); if not m:HasData() or m:LoadData()~='previous' then error('load') end; m:RemoveData(); if m:HasData() or m:LoadData()~='' then error('remove') end; m:AddCallback(ModCallbacks.MC_POST_UPDATE,function() end)";
    } else if (std::strcmp(scenario, "isaac_mod_data") == 0) {
        // 批次 026：`Isaac.SaveModData` / `Isaac.LoadModData` 与 `Mod:SaveData` / `Mod:LoadData`
        // 是**同一件事**（PC 上读写同一份 "saveX.dat"，栈形状也一样）⇒ 这里交叉验证：
        // 用 Isaac 那一层写、用 Mod 那一层读回来，再反过来写读一次。
        // 为什么这条重要：EID 开局时判 `EID:HasData()` 之后就是
        // `json.decode(Isaac.LoadModData(EID))`，旧桩返回 nil 会让 `json.decode` 直接抛错。
        script = "local m=RegisterMod('Persistent Probe',1); "
                 "if Isaac.LoadModData(m)~='' then error('isaac empty') end; "
                 "Isaac.SaveModData(m,'[1,2]'); "
                 "if m:LoadData()~='[1,2]' then error('isaac save not visible to Mod') end; "
                 "m:SaveData('mod-side'); "
                 "if Isaac.LoadModData(m)~='mod-side' then error('mod save not visible to Isaac') end; "
                 "Isaac.RemoveModData(m); if m:HasData() or Isaac.LoadModData(m)~='' then error('Isaac.RemoveModData not visible to Mod') end; "
                 "Isaac.RemoveModData(m); if m:HasData() then error('idempotent remove') end; "
                 "if pcall(function()Isaac.RemoveModData({})end) then error('invalid mod accepted') end; "
                 "m:AddCallback(ModCallbacks.MC_POST_UPDATE,function() end)";
    } else if (std::strcmp(scenario, "invalid") == 0) {
        script = "local m=RegisterMod('Persistent Probe',1); m:SaveData({})";
    } else if (std::strcmp(scenario, "corrupt") == 0) {
        g_files["isaac-mod-data.bin"]="bad!";
        script = "local m=RegisterMod('Persistent Probe',1); m:HasData()";
    } else if (std::strcmp(scenario, "namespace") == 0) {
        const auto first = ModPersistence::HashModNamespace("First", 5);
        const auto second = ModPersistence::HashModNamespace("Second", 6);
        if (ModPersistence::SaveModData(first, "one", 3) != ModPersistence::Result::Success ||
            ModPersistence::SaveModData(second, "two", 3) != ModPersistence::Result::Success) return 11;
        ModPersistence::ResetCacheForTesting();
        const char* data = nullptr;
        std::size_t length = 0;
        return ModPersistence::LoadModData(first, &data, &length) == ModPersistence::Result::Success &&
                       length == 3 && std::memcmp(data, "one", 3) == 0 &&
                       ModPersistence::LoadModData(second, &data, &length) == ModPersistence::Result::Success &&
                       length == 3 && std::memcmp(data, "two", 3) == 0
                   ? 0
                   : 12;
    } else if (std::strcmp(scenario, "unknown") == 0) {
        const auto key = ModPersistence::HashModNamespace("Persistent Probe", 16);
        // 旧ISMODST2里未知记录类型完整保留，新独立文件不改历史容器。
        std::string legacy(59,'\0');auto* p=reinterpret_cast<std::uint8_t*>(legacy.data());
        std::memcpy(p,"ISMODST2",8);ModPersistence::detail::WriteU16(p+8,2);
        ModPersistence::detail::WriteU16(p+10,32);ModPersistence::detail::WriteU32(p+20,1);
        ModPersistence::detail::WriteU32(p+24,27);ModPersistence::detail::WriteU64(p+32,key);
        ModPersistence::detail::WriteU64(p+40,ModPersistence::detail::kModDataKey);
        p[48]=99;ModPersistence::detail::WriteU32(p+52,3);std::memcpy(p+56,"old",3);
        RefreshChecksum(legacy);g_files["isaac-mod-data.bin"]=legacy;
        ModPersistence::ResetCacheForTesting();
        if (ModPersistence::SaveModData(key, "new", 3) != ModPersistence::Result::Success) return 14;
        if (g_files["isaac-mod-data.bin"]!=legacy) return 15;
        ModPersistence::ResetCacheForTesting();
        const char* data = nullptr;
        std::size_t length = 0;
        return ModPersistence::LoadModData(key, &data, &length) == ModPersistence::Result::Success &&
                       length == 3 && std::memcmp(data, "new", 3) == 0
                   ? 0
                   : 16;
    } else if (std::strcmp(scenario, "callback_error") == 0) {
        script = "local m=RegisterMod('Persistent Probe',1); m:AddCallback(ModCallbacks.MC_POST_UPDATE,function() error('trace') end)";
    } else if (std::strcmp(scenario, "callback_save_failure") == 0) {
        g_fail_write = true;
        script = "local m=RegisterMod('Persistent Probe',1); m:AddCallback(ModCallbacks.MC_POST_UPDATE,function() m:SaveData('x') end)";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@persistence.lua");
    if (std::strcmp(scenario, "invalid") == 0 || std::strcmp(scenario, "corrupt") == 0) {
        return result == LuaRuntime::LuaInitResult::ScriptRunFailed ? 0 : 20;
    }
    if (result != LuaRuntime::LuaInitResult::Success) return 21;
    if (std::strcmp(scenario, "callback_error") == 0 ||
        std::strcmp(scenario, "callback_save_failure") == 0) {
        LuaRuntime::DispatchPostUpdate();
        if (!LuaRuntime::TakeCallbackError()) return 23;
        const std::uint64_t detail = LuaRuntime::CallbackFailureDetail();
        const std::uint8_t operation = static_cast<std::uint8_t>(detail >> 8);
        if ((detail & 0xFFU) != LUA_ERRRUN) return 24;
        return operation == (std::strcmp(scenario, "callback_save_failure") == 0 ? 1U : 0U) ? 0 : 25;
    }
    if (std::strcmp(scenario, "save") == 0) {
        ModPersistence::ResetCacheForTesting();
        const auto key = ModPersistence::HashModNamespace("Persistent Probe", 16);
        const char* data = nullptr;
        std::size_t length = 0;
        return ModPersistence::LoadModData(key, &data, &length) == ModPersistence::Result::Success &&
                       length == 7 && std::memcmp(data, "{\"v\":1}", 7) == 0
                   ? 0
                   : 22;
    }
    return 0;
}
'''.lstrip(),
            encoding="utf-8",
        )

        lua_root = SOURCE / "third_party" / "lua-5.3.3" / "src"
        excluded = {"lua.c", "luac.c", "liolib.c", "loslib.c", "loadlib.c", "ldblib.c", "linit.c"}
        lua_objects = []
        for lua_source in sorted(lua_root.glob("*.c")):
            if lua_source.name in excluded:
                continue
            output = self.temporary_path / (lua_source.stem + ".o")
            build = subprocess.run(
                ["cc", "-std=c99", "-w", "-DLUA_C89_NUMBERS", "-I", str(lua_root), "-c", str(lua_source), "-o", str(output)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            lua_objects.append(output)

        binary = self.temporary_path / "lua_mod_persistence_harness"
        build = subprocess.run(
            [
                "c++", "-std=c++23", "-Wall", "-Wextra", "-Werror", "-DLUA_C89_NUMBERS",
                "-DEXL_LAYERED_RUNTIME=1",
                "-DEXL_LOAD_KIND=Module", "-DEXL_LOAD_KIND_ENUM=2", "-DEXL_PROGRAM_ID=0",
                "-DEXL_PERSISTENCE_TRACE",
                "-I", str(compatibility), "-I", str(SOURCE), "-I", str(SOURCE.parent / "src"),
                "-I", str(lua_root), str(harness),
                *(str(path) for path in layered_lua_runtime_sources(SOURCE)),
                *(str(path) for path in lua_objects), "-lm", "-o", str(binary),
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        for scenario in (
            "save", "load_remove", "invalid", "corrupt", "namespace", "unknown",
            "callback_error", "callback_save_failure",
            # 批次 026：`Isaac` 那一层的读写与 `Mod` 那一层是同一份存储（交叉验证）。
            "isaac_mod_data",
        ):
            result = subprocess.run([str(binary), scenario], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, scenario + "\n" + result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
