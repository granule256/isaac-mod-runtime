"""Custom achievement notifications use their own queue and only claim an idle native overlay."""
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
#include <cstdio>
#include <cstring>
#include <string>
#include <utility>
#include <vector>

extern "C" {
#include <lua.h>
#include <lauxlib.h>
}

static constexpr std::uintptr_t kManagerPopupOffset = 0x36509;
static constexpr std::uintptr_t kOverlayOffset = 0x2d338;
static constexpr std::uintptr_t kQueueSizeOffset = 0x28;
static constexpr std::uintptr_t kDisplayedIdOffset = 0x30;
static constexpr std::uintptr_t kStateOffset = 0x38;
static constexpr std::uintptr_t kSpriteOffset = 0x40;

alignas(16) static std::array<unsigned char, 0x38000> manager{};
static unsigned showCalls{}, showId{};
static unsigned loadGraphicsCalls{}, updateCalls{}, xmlLookups{};
static std::vector<std::pair<int, std::string>> replacements;

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
static Files files;
}

namespace LuaRuntime {
std::uintptr_t EngineModuleBase() noexcept { return 0; }
bool IsOnGameThread() noexcept { return true; }
}

namespace isaac::runtime::xml_data {
static XmlRecord first, second, hidden, third;

const XmlRecord* FindEntryById(XmlNodeType type, int id) noexcept {
    ++xmlLookups;
    if (type != XmlNodeType::Achievement) return nullptr;
    if (id == 641) return &first;
    if (id == 642) return &second;
    if (id == 643) return &hidden;
    if (id == 644) return &third;
    return nullptr;
}
}
namespace xml_data = isaac::runtime::xml_data;

namespace isaac::runtime::repentogon {
bool HasSpriteValidator() noexcept { return true; }
bool CallbackSpriteAlive(std::uintptr_t address) noexcept {
    return address == reinterpret_cast<std::uintptr_t>(manager.data()) + kOverlayOffset + kSpriteOffset;
}
}

namespace isaac::runtime {
static int Replace(lua_State* L) {
    const int layer = static_cast<int>(luaL_checkinteger(L, 2));
    const char* path = luaL_checkstring(L, 3);
    replacements.emplace_back(layer, path);
    return 0;
}
static int LoadGraphics(lua_State*) {
    ++loadGraphicsCalls;
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
    lua_pushcfunction(L, LoadGraphics);
    lua_setfield(L, -2, "LoadGraphics");
    lua_pushcfunction(L, Update);
    lua_setfield(L, -2, "Update");
}
}

static void ShowAchievement(std::uintptr_t address, int id) noexcept {
    ++showCalls;
    showId = static_cast<unsigned>(id);
    auto* overlay = reinterpret_cast<unsigned char*>(address + kOverlayOffset);
    const std::int32_t state = 1;
    const std::int32_t displayed = id;
    std::memcpy(overlay + kStateOffset, &state, sizeof(state));
    std::memcpy(overlay + kDisplayedIdOffset, &displayed, sizeof(displayed));
}

static void SetQueueSize(std::uint64_t value) {
    std::memcpy(manager.data() + kOverlayOffset + kQueueSizeOffset, &value, sizeof(value));
}
static std::int32_t State() {
    std::int32_t value{};
    std::memcpy(&value, manager.data() + kOverlayOffset + kStateOffset, sizeof(value));
    return value;
}
static void SetState(std::int32_t value) {
    std::memcpy(manager.data() + kOverlayOffset + kStateOffset, &value, sizeof(value));
}
static void SetPopup(bool enabled) {
    manager[kManagerPopupOffset] = enabled ? 1 : 0;
}

static void Attribute(xml_data::XmlRecord* record, const char* name, const char* value) {
    record->attributes.push_back(xml_data::XmlAttribute{name, value});
}

int main() {
    auto* first = &xml_data::first;
    first->id = 641;
    Attribute(first, "name", "First");
    Attribute(first, "sourceid", "ModA");
    Attribute(first, "gfxroot", "gfx/custom/");
    Attribute(first, "gfx", "first.png");
    Attribute(first, "gfxback", "back.png");

    auto* second = &xml_data::second;
    second->id = 642;
    Attribute(second, "name", "Second");
    Attribute(second, "sourceid", "ModA");
    Attribute(second, "gfxroot", "gfx/custom/");
    Attribute(second, "gfx", "second.png");

    auto* hidden = &xml_data::hidden;
    hidden->id = 643;
    Attribute(hidden, "name", "Hidden");
    Attribute(hidden, "sourceid", "ModA");
    Attribute(hidden, "hidden", "true");
    Attribute(hidden, "gfxroot", "gfx/custom/");
    Attribute(hidden, "gfx", "hidden.png");

    auto* third = &xml_data::third;
    third->id = 644;
    Attribute(third, "name", "Third");
    Attribute(third, "sourceid", "ModA");
    Attribute(third, "gfxroot", "gfx/custom/");
    Attribute(third, "gfx", "third.png");

    lua_State* L = luaL_newstate();
    assert(L);
    isaac::runtime::SetSessionSaveFilePort(&isaac::runtime::files);
    SetPopup(true);
    isaac::runtime::SetRepentogonAchievementNotificationTestBindings(
        {reinterpret_cast<std::uintptr_t>(manager.data()), &ShowAchievement});

    using namespace isaac::runtime;
    ResetRepentogonAchievementNotifications();
    assert(!HasPendingRepentogonAchievementNotifications());
    assert(QueueRepentogonAchievementNotification(641));
    assert(!QueueRepentogonAchievementNotification(641));
    assert(QueueRepentogonAchievementNotification(642));
    assert(!QueueRepentogonAchievementNotification(643));
    assert(!QueueRepentogonAchievementNotification(999));
    assert(HasPendingRepentogonAchievementNotifications());
    const auto lookupsBeforeQueries = xmlLookups;
    for (int index = 0; index < 1000; ++index) {
        assert(HasPendingRepentogonAchievementNotifications());
    }
    assert(xmlLookups == lookupsBeforeQueries);

    const auto lookupsBeforePump = xmlLookups;
    SetState(1);
    assert(PumpRepentogonAchievementNotifications(L) == 0);
    assert(showCalls == 0);
    assert(HasPendingRepentogonAchievementNotifications());
    SetState(0);
    SetQueueSize(1);
    assert(PumpRepentogonAchievementNotifications(L) == 0);
    assert(showCalls == 0);
    assert(xmlLookups == lookupsBeforePump);

    SetQueueSize(0);
    assert(PumpRepentogonAchievementNotifications(L) == 1);
    assert(showCalls == 1 && showId == 2 && State() == 1);
    assert(replacements.size() == 2);
    assert(replacements[0] == std::make_pair(2, std::string("gfx/custom/back.png")));
    assert(replacements[1] == std::make_pair(3, std::string("gfx/custom/first.png")));
    assert(loadGraphicsCalls == 1 && updateCalls == 1);
    assert(xmlLookups == lookupsBeforePump);

    assert(PumpRepentogonAchievementNotifications(L) == 0);
    assert(showCalls == 1);
    assert(HasPendingRepentogonAchievementNotifications());

    SetState(0);
    assert(PumpRepentogonAchievementNotifications(L) == 1);
    assert(replacements.size() == 4);
    assert(replacements[2] == std::make_pair(2, std::string("gfx/ui/achievement/Paper.png")));
    assert(replacements[3] == std::make_pair(3, std::string("gfx/ui/achievement/achievement_locked.png")));
    assert(loadGraphicsCalls == 2 && updateCalls == 2);
    assert(HasPendingRepentogonAchievementNotifications());

    assert(PumpRepentogonAchievementNotifications(L) == 1);
    assert(showCalls == 2 && showId == 2);
    assert(replacements.size() == 6);
    assert(replacements[4] == std::make_pair(2, std::string("gfx/ui/achievement/Paper.png")));
    assert(replacements[5] == std::make_pair(3, std::string("gfx/custom/second.png")));
    assert(loadGraphicsCalls == 3 && updateCalls == 3);

    SetState(0);
    assert(PumpRepentogonAchievementNotifications(L) == 1);
    assert(replacements.size() == 8);
    assert(loadGraphicsCalls == 4 && updateCalls == 4);
    assert(!HasPendingRepentogonAchievementNotifications());

    SetPopup(false);
    assert(QueueRepentogonAchievementNotification(644));
    assert(PumpRepentogonAchievementNotifications(L) == 1);
    assert(showCalls == 2);
    assert(!HasPendingRepentogonAchievementNotifications());

    SetPopup(true);
    assert(QueueRepentogonAchievementNotification(641));
    assert(HasPendingRepentogonAchievementNotifications());
    ResetRepentogonAchievementNotifications();
    assert(!HasPendingRepentogonAchievementNotifications());
    SetSessionSaveFilePort(nullptr);
    lua_close(L);
}
'''


class AchievementNotificationTests(unittest.TestCase):
    def test_queue_fairness_native_busy_and_sprite_replacement(self):
        with tempfile.TemporaryDirectory(prefix="achievement-notification-") as folder:
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
