"""Fancy Menu callbacks preserve upstream filters and Lua argument order."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support

SOURCE = Path(__file__).resolve().parents[1] / "source"

DRIVER = r'''
#include "lua_runtime.hpp"
#include "interfaces/lua/repentogon_character_menu_api.hpp"
#include "interfaces/lua/repentogon_callbacks.hpp"
#include "interfaces/lua/repentogon_environment.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "ports/save_file_port.hpp"
#include "runtime_constants.hpp"

#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>

using namespace isaac::runtime;
using namespace isaac::runtime::repentogon;

struct Files final : ISaveFilePort {
    std::string value = "isaac-repentogon 1\nenabled 1\n";
    Status Read(std::string_view, char* out, std::size_t capacity,
                std::size_t* size) noexcept override {
        if (size == nullptr || capacity < value.size()) {
            return Status{StatusCode::CapacityExceeded};
        }
        *size = value.size();
        std::memcpy(out, value.data(), value.size());
        return Status::Ok();
    }
    Status Write(std::string_view, std::string_view) noexcept override {
        return Status::Ok();
    }
    Status Remove(std::string_view) noexcept override {
        return Status{StatusCode::Unsupported};
    }
    Status Exists(const char*, bool*) noexcept override {
        return Status{StatusCode::Unsupported};
    }
};

static bool Ready() noexcept { return true; }
static bool Install() noexcept { return true; }
alignas(16) static unsigned char sprite[kSpriteObjectSize]{};
alignas(16) static unsigned char module[0x10000]{};

static bool SpriteAlive(std::uintptr_t value) noexcept {
    return value == engine_memory::AddressOf(sprite);
}

static std::uintptr_t Address(const void* value) {
    return reinterpret_cast<std::uintptr_t>(value);
}

static double Number(const char* name) {
    double value{};
    assert(LuaRuntime::ReadLuaGlobalNumber(name, &value));
    return value;
}

int main() {
    Files files;
    SetSessionSaveFilePort(&files);
    LuaRuntime::SetEngineModuleBase(Address(module));
    LuaRuntime::ObserveGameThread();
    const NativePort port{Ready, Install, SpriteAlive};
    SetNativePort(&port);

    constexpr const char* script = R"lua(
local m=RegisterMod("fancy-callback-shapes",1)
assert(ModCallbacks.MC_PRE_COMPLETION_MARKS_RENDER==1216)
assert(ModCallbacks.MC_POST_COMPLETION_MARKS_RENDER==1217)
assert(ModCallbacks.MC_PRE_RENDER_CUSTOM_CHARACTER_MENU==1333)
assert(ModCallbacks.MC_POST_ROOM_TRANSITION_UPDATE==1271)
calls=0

m:AddCallback(1216,function(_,sprite,pos,scale,playerType)
    assert(type(sprite)=="userdata")
    assert(pos.X==10 and pos.Y==20 and scale.X==2 and scale.Y==3)
    assert(playerType==7)
    calls=calls+1
    if calls==1 then return true end
    if calls==2 then return false end
end)
m:AddCallback(1217,function(_,sprite,pos,scale,playerType)
    assert(type(sprite)=="userdata")
    assert(pos.X==11 and pos.Y==21 and scale.X==4 and scale.Y==5)
    assert(playerType==8)
    calls=calls+1
end)
m:AddCallback(1333,function(_,playerType,pos,sprite)
    assert(playerType==7 and pos.X==12 and pos.Y==22)
    assert(type(sprite)=="userdata")
    calls=calls+1
end,7)
m:AddCallback(1333,function() error("wrong 1333 filter") end,8)
m:AddCallback(1271,function(_,...)
    assert(select("#",...) == 0)
    calls=calls+1
end,9)
m:AddCallback(1271,function() error("wrong 1271 filter") end,8)
)lua";

    assert(LuaRuntime::InitializeFromBuffer(
               script, std::strlen(script), "@fancy-callback-shapes.lua") ==
           LuaRuntime::LuaInitResult::Success);

    Vector pos{10, 20};
    Vector scale{2, 3};
    assert(DispatchRepentogonPreCompletionMarksRender(
        Address(sprite), &pos, &scale, 7));
    assert(Number("calls") == 1);

    assert(DispatchRepentogonPreCompletionMarksRender(
        Address(sprite), &pos, &scale, 7));
    assert(Number("calls") == 2);

    assert(!DispatchRepentogonPreCompletionMarksRender(
        Address(sprite), &pos, &scale, 7));
    assert(Number("calls") == 3);

    Vector postPos{11, 21};
    Vector postScale{4, 5};
    Event event = {1217, EventKind::Global, Address(sprite), Address(&postPos),
                   &postScale, false, nullptr, 8};
    Dispatch(event);
    assert(Number("calls") == 4);

    Vector customPos{12, 22};
    event = {1333, EventKind::Global, Address(sprite), Address(&customPos),
             nullptr, false, nullptr, 7};
    Dispatch(event);
    assert(Number("calls") == 5);

    event = {1271, EventKind::Global, 0, 0, nullptr, false, nullptr, 9};
    Dispatch(event);
    assert(Number("calls") == 6);

    assert(LuaRuntime::ShutdownForModReload());
    SetNativePort(nullptr);
    SetSessionSaveFilePort(nullptr);
}
'''


class RepentogonFancyMenuCallbackTests(unittest.TestCase):
    def test_callback_arguments_and_filters(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fancy-menu-callbacks-") as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE,
                workdir=Path(folder),
                harness_source=DRIVER,
            )
            result = subprocess.run(
                [str(binary)], capture_output=True, text=True, check=False
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
