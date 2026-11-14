"""An OFF REPENTOGON session must not publish active native capabilities."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support

SOURCE = Path(__file__).resolve().parents[1] / "source"

DRIVER = r'''
#include "interfaces/lua/repentogon_callbacks.hpp"
#include "interfaces/lua/repentogon_environment.hpp"
#include "lua_runtime.hpp"
#include "ports/save_file_port.hpp"

#include <cassert>
#include <cstring>

using namespace isaac::runtime;

struct Files final : ISaveFilePort {
    Status Read(std::string_view, char* out, std::size_t capacity,
                std::size_t* size) noexcept override {
        constexpr char value[] = "isaac-repentogon 1\nenabled 0\n";
        *size = sizeof(value) - 1;
        assert(capacity >= *size);
        std::memcpy(out, value, *size);
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
static bool SpriteAlive(std::uintptr_t) noexcept { return false; }

int main() {
    Files files;
    SetSessionSaveFilePort(&files);
    LuaRuntime::ObserveGameThread();
    const repentogon::NativePort port{Ready, Ready, SpriteAlive};
    repentogon::SetNativePort(&port);

    constexpr char script[] =
        "assert(REPENTOGON == nil)\n"
        "assert(not RuntimeMods.GetRepentogonState().Active)\n";
    assert(LuaRuntime::InitializeFromBuffer(script, sizeof(script) - 1,
                                            "@repentogon-isolation.lua") ==
           LuaRuntime::LuaInitResult::Success);

    assert(!RepentogonEnvironmentActive());
    assert(!repentogon::HasNativePort());
    assert(!repentogon::HasSpriteValidator());
    assert(!repentogon::UpdatePaused());

    assert(LuaRuntime::ShutdownForModReload());
    repentogon::SetNativePort(nullptr);
    SetSessionSaveFilePort(nullptr);
}
'''


class RepentogonIsolationTests(unittest.TestCase):
    def test_off_does_not_publish_native_capability(self):
        with tempfile.TemporaryDirectory(prefix="repentogon-isolation-") as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE,
                workdir=Path(folder),
                harness_source=DRIVER,
            )
            result = subprocess.run(
                [str(binary)], capture_output=True, text=True
            )
            self.assertEqual(
                result.returncode,
                0,
                result.stdout + result.stderr,
            )


if __name__ == "__main__":
    unittest.main()
