"""Partial PersistentGameData:Unlock: custom force only; native force stays unavailable."""
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LUA = ROOT / "source/third_party/lua-5.3.3/src"
COMPILE_FLAGS = (
    "-std=c++23", "-Wall", "-Wextra", "-Werror", "-DLUA_C89_NUMBERS",
    "-DEXL_LAYERED_RUNTIME=1", "-DEXL_DIAGNOSTIC_STAGE=14",
    "-DEXL_LOAD_KIND=Module", "-DEXL_LOAD_KIND_ENUM=2", "-DEXL_PROGRAM_ID=0",
)

DRIVER = r'''
#include "interfaces/lua/repentogon_persistent_api.hpp"
#include "interfaces/lua/repentogon_achievement_notification.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "ports/save_file_port.hpp"
#include "program/xml_data_store.hpp"
#include "lua_runtime.hpp"

#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <string>
#include <unordered_map>
#include <vector>

extern "C" {
#include <lua.h>
#include <lauxlib.h>
#include <lualib.h>
}

using namespace isaac::runtime;

static unsigned char persistent[16]{};
static unsigned queueCalls{}, pumpCalls{}, resetCalls{};
static bool persistedBeforeQueue = true;
static bool failPump = false;
static std::vector<int> eventOrder;

namespace isaac::runtime {
struct Files : ISaveFilePort {
    unsigned slot = 2;
    bool fail = false;
    std::unordered_map<std::string, std::string> data;

    Status GetSaveSlot(unsigned* out) noexcept override { *out = slot; return Status::Ok(); }
    Status Read(std::string_view path, char* out, std::size_t cap,
                std::size_t* size) noexcept override {
        const auto found = data.find(std::string(path));
        if (found == data.end()) return Status{StatusCode::NotFound};
        *size = found->second.size();
        if (*size > cap) return Status{StatusCode::CapacityExceeded};
        std::memcpy(out, found->second.data(), *size);
        return Status::Ok();
    }
    Status Write(std::string_view path, std::string_view bytes) noexcept override {
        if (fail) return Status{StatusCode::IoFailure};
        data[std::string(path)] = std::string(bytes);
        return Status::Ok();
    }
    Status Remove(std::string_view) noexcept override {
        return Status{StatusCode::Unsupported};
    }
    Status Exists(const char*, bool*) noexcept override {
        return Status{StatusCode::Unsupported};
    }
};
static Files files;

std::uintptr_t PersistentGameDataObjectArgument(lua_State*, int) noexcept {
    return reinterpret_cast<std::uintptr_t>(persistent);
}

bool QueueRepentogonAchievementNotification(int id) {
    ++queueCalls;
    eventOrder.push_back(100 + id);
    persistedBeforeQueue =
        files.data.find("repentogon-achievements-2.dat") != files.data.end();
    return true;
}
int PumpRepentogonAchievementNotifications(lua_State* state) {
    ++pumpCalls;
    eventOrder.push_back(200);
    if (failPump) {
        lua_pushliteral(state, "pump failure");
        return -1;
    }
    return 0;
}
bool HasPendingRepentogonAchievementNotifications() noexcept {
    return queueCalls > pumpCalls;
}
void ResetRepentogonAchievementNotifications() noexcept {
    ++resetCalls;
}
}

namespace LuaRuntime {
bool IsOnGameThread() noexcept { return true; }
int ReportAndRecordLuaError(lua_State* state, const char* format, ...) {
    char message[1024]{};
    va_list args;
    va_start(args, format);
    std::vsnprintf(message, sizeof(message), format, args);
    va_end(args);
    lua_pushstring(state, message);
    return lua_error(state);
}
}

namespace isaac::runtime::api100_native {
std::uintptr_t Resolve(lua_State*, const Entry&, Cache&, std::uintptr_t) { return 0; }
}

namespace isaac::runtime::xml_data {
static XmlRecord r641, r642, r643, r644, r645, r646;

const XmlRecord* FindEntryById(XmlNodeType type, int id) noexcept {
    if (type != XmlNodeType::Achievement) return nullptr;
    if (id == 641) return &r641;
    if (id == 642) return &r642;
    if (id == 643) return &r643;
    if (id == 644) return &r644;
    if (id == 645) return &r645;
    if (id == 646) return &r646;
    return nullptr;
}

static void Attribute(XmlRecord* record, int id, const char* name, const char* value) {
    record->id = id;
    record->attributes.push_back(XmlAttribute{name, value});
}
}

static void Run(lua_State* L, const char* script) {
    if (luaL_dostring(L, script) != LUA_OK) {
        std::fprintf(stderr, "%s\n", lua_tostring(L, -1));
        assert(false);
    }
}

int main() {
    using namespace isaac::runtime;
    xml_data::Attribute(&xml_data::r641, 641, "name", "First");
    xml_data::Attribute(&xml_data::r641, 641, "sourceid", "ModA");
    xml_data::Attribute(&xml_data::r641, 641, "gfx", "first.png");
    xml_data::Attribute(&xml_data::r642, 642, "name", "Second");
    xml_data::Attribute(&xml_data::r642, 642, "sourceid", "ModA");
    xml_data::Attribute(&xml_data::r642, 642, "gfx", "second.png");
    xml_data::Attribute(&xml_data::r643, 643, "name", "Hidden");
    xml_data::Attribute(&xml_data::r643, 643, "sourceid", "ModA");
    xml_data::Attribute(&xml_data::r643, 643, "hidden", "true");
    xml_data::Attribute(&xml_data::r643, 643, "gfx", "hidden.png");
    xml_data::Attribute(&xml_data::r644, 644, "name", "NoPopup");
    xml_data::Attribute(&xml_data::r644, 644, "sourceid", "ModA");
    xml_data::Attribute(&xml_data::r644, 644, "gfx", "nopopup.png");
    xml_data::Attribute(&xml_data::r645, 645, "name", "Failing");
    xml_data::Attribute(&xml_data::r645, 645, "sourceid", "ModA");
    xml_data::Attribute(&xml_data::r645, 645, "gfx", "failing.png");
    xml_data::Attribute(&xml_data::r646, 646, "name", "PumpFailure");
    xml_data::Attribute(&xml_data::r646, 646, "sourceid", "ModA");
    xml_data::Attribute(&xml_data::r646, 646, "gfx", "pump.png");

    SetSessionSaveFilePort(&files);
    ResetRepentogonAchievementState();
    resetCalls = 0;
    lua_State* L = luaL_newstate();
    assert(L);
    luaL_requiref(L, "_G", luaopen_base, 1);
    lua_pop(L, 1);
    lua_pushcfunction(L, RepentogonPersistentGameDataTryUnlock);
    lua_setglobal(L, "tryUnlock");
    lua_pushcfunction(L, RepentogonPersistentGameDataUnlock);
    lua_setglobal(L, "unlock");

    persistent[1] = 0;
    Run(L, "assert(tryUnlock({},641))");
    assert(queueCalls == 1 && pumpCalls == 1 && persistedBeforeQueue);
    assert(eventOrder.size() == 2 && eventOrder[0] == 741 && eventOrder[1] == 200);
    Run(L, "assert(not tryUnlock({},641))");
    assert(queueCalls == 1 && pumpCalls == 1);

    persistent[1] = 1;
    Run(L, "assert(not tryUnlock({},642))");
    assert(persistent[1] == 1);
    assert(queueCalls == 1 && pumpCalls == 1);
    Run(L, "assert(unlock({},642))");
    assert(persistent[1] == 1);
    assert(queueCalls == 2 && pumpCalls == 2 && persistedBeforeQueue);
    assert(eventOrder[2] == 742 && eventOrder[3] == 200);
    Run(L, "assert(not unlock({},642))");
    assert(queueCalls == 2 && pumpCalls == 2);

    persistent[1] = 0;
    Run(L, "assert(tryUnlock({},643))");
    assert(queueCalls == 2 && pumpCalls == 2);
    Run(L, "assert(tryUnlock({},644,true))");
    assert(queueCalls == 2 && pumpCalls == 2);
    Run(L, "assert(not tryUnlock({},999))");
    Run(L, "assert(not unlock({},999))");
    persistent[1] = 1;
    Run(L, "local ok,e=pcall(function() return unlock({},2) end);"
           "assert(not ok and e=='PersistentGameData:Unlock native force-unlock is unavailable')");
    assert(persistent[1] == 1);
    persistent[1] = 0;
    Run(L, "assert(not unlock({},0) and not unlock({},-1))");
    Run(L, "assert(not unlock({},638) and not unlock({},639) and not unlock({},640))");
    assert(persistent[1] == 0);

    persistent[1] = 0;
    files.fail = true;
    Run(L, "assert(not pcall(function() return tryUnlock({},645) end))");
    assert(queueCalls == 2 && pumpCalls == 2);
    files.fail = false;
    Run(L, "assert(tryUnlock({},645))");
    assert(queueCalls == 3 && pumpCalls == 3);
    failPump = true;
    Run(L, "local ok,e=pcall(function() return tryUnlock({},646) end);assert(not ok and e=='pump failure')");
    assert(queueCalls == 4 && pumpCalls == 4);
    failPump = false;
    lua_close(L);
    SetSessionSaveFilePort(nullptr);
}
'''


class PersistentUnlockTests(unittest.TestCase):
    def test_custom_force_unlock_partial_native_rejected_without_mutating_readonly(self):
        with tempfile.TemporaryDirectory(prefix="persistent-unlock-") as folder:
            folder = Path(folder)
            compatibility = folder / "compatibility"
            compatibility.mkdir()
            (compatibility / "stdfloat").write_text(
                "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n")
            source = folder / "driver.cpp"
            source.write_text(DRIVER)
            lua_objects = []
            for path in sorted(LUA.glob("*.c")):
                if path.name in {"lua.c", "luac.c", "liolib.c", "loslib.c", "loadlib.c",
                                 "ldblib.c", "linit.c"}:
                    continue
                obj = folder / (path.stem + ".o")
                compiled = subprocess.run(
                    ["cc", "-std=c99", "-w", "-DLUA_C89_NUMBERS", f"-I{LUA}",
                     "-c", str(path), "-o", str(obj)],
                    capture_output=True, text=True)
                self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
                lua_objects.append(obj)
            binary = folder / "test"
            compiled = subprocess.run(
                ["c++", *COMPILE_FLAGS,
                 "-I", str(compatibility), "-I", str(ROOT / "src"),
                 "-I", str(ROOT / "source"), "-I", str(LUA),
                 str(source),
                 str(ROOT / "src/interfaces/lua/repentogon_persistent_api.cpp"),
                 str(ROOT / "src/application/repentogon/achievement_state.cpp"),
                 *map(str, lua_objects), "-lm", "-o", str(binary)],
                capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
