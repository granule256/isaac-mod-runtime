"""Notification failures stay visible and queue identity never crosses save slots."""
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
#include "interfaces/lua/repentogon_achievement_notification.hpp"
#include "interfaces/lua/repentogon_callbacks.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "ports/save_file_port.hpp"
#include "program/xml_data_store.hpp"
#include "lua_runtime.hpp"

#include <array>
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <string>
#include <utility>
#include <vector>

extern "C" {
#include <lua.h>
#include <lauxlib.h>
}

using namespace isaac::runtime;

static constexpr std::uintptr_t kPopup = 0x36509;
static constexpr std::uintptr_t kOverlay = 0x2d338;
static constexpr std::uintptr_t kQueueSize = 0x28;
static constexpr std::uintptr_t kDisplayed = 0x30;
static constexpr std::uintptr_t kState = 0x38;
static constexpr std::uintptr_t kSprite = 0x40;

alignas(16) static std::array<unsigned char, 0x38000> managerA{}, managerB{};
static unsigned showCalls{}, replacementCalls{}, loadCalls{}, updateCalls{};
static bool failApply{}, failRestore{};
static std::string lastLayer2{}, lastLayer3{};

static unsigned char* Manager(std::uintptr_t address) {
    return reinterpret_cast<unsigned char*>(address);
}
static void SetState(std::uintptr_t address, std::int32_t value) {
    std::memcpy(Manager(address) + kOverlay + kState, &value, sizeof(value));
}
static void SetQueueSize(std::uintptr_t address, std::uint64_t value) {
    std::memcpy(Manager(address) + kOverlay + kQueueSize, &value, sizeof(value));
}
static void SetPopup(std::uintptr_t address) {
    Manager(address)[kPopup] = 1;
}

namespace LuaRuntime {
std::uintptr_t EngineModuleBase() noexcept { return 0; }
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

namespace isaac::runtime {
struct Files : ISaveFilePort {
    unsigned slot = 2;
    Status GetSaveSlot(unsigned* out) noexcept override { *out = slot; return Status::Ok(); }
    Status Read(std::string_view, char*, std::size_t, std::size_t*) noexcept override {
        return Status{StatusCode::NotFound};
    }
    Status Write(std::string_view, std::string_view) noexcept override {
        return Status{StatusCode::Unsupported};
    }
    Status Remove(std::string_view) noexcept override {
        return Status{StatusCode::Unsupported};
    }
    Status Exists(const char*, bool*) noexcept override {
        return Status{StatusCode::Unsupported};
    }
};
static Files filesA, filesB;
}

namespace isaac::runtime::xml_data {
static XmlRecord good, bad;

const XmlRecord* FindEntryById(XmlNodeType type, int id) noexcept {
    if (type != XmlNodeType::Achievement) return nullptr;
    if (id == 641) return &good;
    if (id == 642) return &bad;
    return nullptr;
}
static void Attribute(XmlRecord* record, int id, const char* name, const char* value) {
    record->id = id;
    record->attributes.push_back(XmlAttribute{name, value});
}
}

namespace isaac::runtime::repentogon {
bool HasSpriteValidator() noexcept { return true; }
bool CallbackSpriteAlive(std::uintptr_t address) noexcept {
    return address == reinterpret_cast<std::uintptr_t>(managerA.data()) + kOverlay + kSprite ||
           address == reinterpret_cast<std::uintptr_t>(managerB.data()) + kOverlay + kSprite;
}
}

namespace isaac::runtime {
static int Replace(lua_State* L) {
    ++replacementCalls;
    const int layer = static_cast<int>(luaL_checkinteger(L, 2));
    const char* path = luaL_checkstring(L, 3);
    if (failApply && layer == 3 && std::strstr(path, "bad.png") != nullptr) {
        return luaL_error(L, "injected custom layer failure");
    }
    if (failRestore && layer == 2 && std::strstr(path, "Paper.png") != nullptr) {
        return luaL_error(L, "injected native restore failure");
    }
    if (layer == 2) lastLayer2 = path;
    if (layer == 3) lastLayer3 = path;
    return 0;
}
static int Load(lua_State*) {
    ++loadCalls;
    return 0;
}
static int Update(lua_State*) {
    ++updateCalls;
    return 0;
}
void PushCallbackSpriteHandle(lua_State* L, std::uintptr_t, int) {
    lua_newtable(L);
    lua_pushcfunction(L, Replace);
    lua_setfield(L, -2, "ReplaceSpritesheet");
    lua_pushcfunction(L, Load);
    lua_setfield(L, -2, "LoadGraphics");
    lua_pushcfunction(L, Update);
    lua_setfield(L, -2, "Update");
}
}

static void Show(std::uintptr_t manager, int id) noexcept {
    ++showCalls;
    const std::int32_t state = 1;
    const std::int32_t displayed = id;
    std::memcpy(Manager(manager) + kOverlay + kState, &state, sizeof(state));
    std::memcpy(Manager(manager) + kOverlay + kDisplayed, &displayed, sizeof(displayed));
}

static void ResetScenario(ISaveFilePort* files, std::uintptr_t manager) {
    using namespace isaac::runtime;
    ResetRepentogonAchievementNotifications();
    SetSessionSaveFilePort(files);
    SetRepentogonAchievementNotificationTestBindings({manager, &Show});
    showCalls = replacementCalls = loadCalls = updateCalls = 0;
    failApply = failRestore = false;
    lastLayer2.clear();
    lastLayer3.clear();
    std::memset(managerA.data(), 0, managerA.size());
    std::memset(managerB.data(), 0, managerB.size());
    SetPopup(reinterpret_cast<std::uintptr_t>(managerA.data()));
    SetPopup(reinterpret_cast<std::uintptr_t>(managerB.data()));
    SetState(manager, 0);
    SetQueueSize(manager, 0);
}

static void RequireError(lua_State* L, int top, const char* stage, int id) {
    assert(lua_gettop(L) == top + 1);
    assert(lua_type(L, -1) == LUA_TSTRING);
    const char* message = lua_tostring(L, -1);
    assert(std::strstr(message, stage) != nullptr);
    const std::string idText = std::to_string(id);
    assert(std::strstr(message, idText.c_str()) != nullptr);
    lua_pop(L, 1);
}

int main() {
    using namespace isaac::runtime;
    auto* good = &xml_data::good;
    xml_data::Attribute(good, 641, "name", "Good");
    xml_data::Attribute(good, 641, "sourceid", "ModA");
    xml_data::Attribute(good, 641, "gfxroot", "gfx/custom/");
    xml_data::Attribute(good, 641, "gfx", "good.png");
    xml_data::Attribute(good, 641, "gfxback", "back.png");
    auto* bad = &xml_data::bad;
    xml_data::Attribute(bad, 642, "name", "Bad");
    xml_data::Attribute(bad, 642, "sourceid", "ModA");
    xml_data::Attribute(bad, 642, "gfxroot", "gfx/custom/");
    xml_data::Attribute(bad, 642, "gfx", "bad.png");

    lua_State* L = luaL_newstate();
    assert(L);
    const auto managerAAddress = reinterpret_cast<std::uintptr_t>(managerA.data());
    const auto managerBAddress = reinterpret_cast<std::uintptr_t>(managerB.data());

    // Custom sheet failure: report -1, retain the active failure state, and do
    // not retry LoadGraphics every frame while the dummy animation is running.
    ResetScenario(&filesA, managerAAddress);
    filesA.slot = 2;
    failApply = true;
    assert(QueueRepentogonAchievementNotification(642));
    int top = lua_gettop(L);
    assert(PumpRepentogonAchievementNotifications(L) == -1);
    RequireError(L, top, "ApplyCustom", 642);
    assert(showCalls == 1);
    assert(HasPendingRepentogonAchievementNotifications());
    auto diagnostics = SnapshotRepentogonAchievementNotificationDiagnostics();
    assert(diagnostics.applyFailures == 1);
    assert(diagnostics.lastFailure ==
           RepentogonAchievementNotificationFailure::ApplyCustom);
    assert(diagnostics.lastFailureId == 642);
    const auto replacementsAfterFailure = replacementCalls;
    const auto loadsAfterFailure = loadCalls;
    SetState(managerAAddress, 1);
    for (int index = 0; index < 20; ++index) {
        assert(PumpRepentogonAchievementNotifications(L) == 0);
    }
    assert(replacementCalls == replacementsAfterFailure);
    assert(loadCalls == loadsAfterFailure);
    failApply = false;
    SetState(managerAAddress, 0);
    assert(PumpRepentogonAchievementNotifications(L) == 1);
    assert(!HasPendingRepentogonAchievementNotifications());

    // Native restore failure is also surfaced once, then latched without retry.
    ResetScenario(&filesA, managerAAddress);
    filesA.slot = 2;
    assert(QueueRepentogonAchievementNotification(641));
    assert(PumpRepentogonAchievementNotifications(L) == 1);
    SetState(managerAAddress, 0);
    failRestore = true;
    top = lua_gettop(L);
    assert(PumpRepentogonAchievementNotifications(L) == -1);
    RequireError(L, top, "RestoreNative", 641);
    assert(!HasPendingRepentogonAchievementNotifications());
    diagnostics = SnapshotRepentogonAchievementNotificationDiagnostics();
    assert(diagnostics.restoreFailures == 1);
    assert(diagnostics.lastFailure ==
           RepentogonAchievementNotificationFailure::RestoreNative);
    const auto callsAtRestoreFailure = replacementCalls;
    for (int index = 0; index < 20; ++index) {
        assert(PumpRepentogonAchievementNotifications(L) == 0);
    }
    assert(replacementCalls == callsAtRestoreFailure);

    // Pending entries do not survive a slot change.
    ResetScenario(&filesA, managerAAddress);
    filesA.slot = 2;
    assert(QueueRepentogonAchievementNotification(641));
    filesA.slot = 3;
    assert(PumpRepentogonAchievementNotifications(L) == 1);
    assert(!HasPendingRepentogonAchievementNotifications());
    assert(showCalls == 0);
    diagnostics = SnapshotRepentogonAchievementNotificationDiagnostics();
    assert(diagnostics.identityResets >= 1);
    assert(QueueRepentogonAchievementNotification(641));
    assert(PumpRepentogonAchievementNotifications(L) == 1);
    assert(showCalls == 1);

    // Switching slots during an active custom notification restores the old
    // sprites immediately instead of carrying them into the new slot.
    ResetScenario(&filesA, managerAAddress);
    filesA.slot = 2;
    assert(QueueRepentogonAchievementNotification(641));
    assert(PumpRepentogonAchievementNotifications(L) == 1);
    lastLayer2.clear();
    lastLayer3.clear();
    filesA.slot = 3;
    assert(PumpRepentogonAchievementNotifications(L) == 1);
    assert(!HasPendingRepentogonAchievementNotifications());
    assert(lastLayer2 == "gfx/ui/achievement/Paper.png");
    assert(lastLayer3 == "gfx/ui/achievement/achievement_locked.png");
    diagnostics = SnapshotRepentogonAchievementNotificationDiagnostics();
    assert(diagnostics.identityResets >= 1);

    // Provider and Manager identity changes discard queued bookkeeping too.
    ResetScenario(&filesA, managerAAddress);
    filesA.slot = 2;
    filesB.slot = 2;
    assert(QueueRepentogonAchievementNotification(641));
    SetSessionSaveFilePort(&filesB);
    assert(PumpRepentogonAchievementNotifications(L) == 1);
    assert(!HasPendingRepentogonAchievementNotifications());
    assert(showCalls == 0);

    ResetScenario(&filesA, managerAAddress);
    filesA.slot = 2;
    assert(QueueRepentogonAchievementNotification(641));
    SetRepentogonAchievementNotificationTestBindings({managerBAddress, &Show});
    assert(PumpRepentogonAchievementNotifications(L) == 1);
    assert(!HasPendingRepentogonAchievementNotifications());
    assert(showCalls == 0);

    // Slot zero follows the persistence layer's slot-1 normalization.
    ResetScenario(&filesA, managerAAddress);
    filesA.slot = 0;
    assert(QueueRepentogonAchievementNotification(641));
    assert(PumpRepentogonAchievementNotifications(L) == 1);
    assert(showCalls == 1);

    SetSessionSaveFilePort(nullptr);
    lua_close(L);
}
'''


class AchievementNotificationFailureTests(unittest.TestCase):
    def test_failures_are_visible_and_queue_is_profile_scoped(self):
        with tempfile.TemporaryDirectory(prefix="achievement-notification-failures-") as folder:
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
                 str(ROOT / "src/interfaces/lua/repentogon_achievement_notification.cpp"),
                 *map(str, lua_objects), "-lm", "-o", str(binary)],
                capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
