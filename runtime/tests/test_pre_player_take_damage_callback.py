"""Focused MC_PRE_PLAYER_TAKE_DMG contract tests."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from .test_lua_api_method_lookup_cost import function
from .test_player_damage_internal_hook import SOURCE, UNITS


RETURN_DRIVER = r'''
#include "player_take_damage_callback.hpp"
#include "application/callback/callback_dispatcher.hpp"

#include <cassert>
#include <cstdint>

using namespace isaac::runtime;

struct FakeInvoker final : ICallbackInvoker {
    CallbackBatchResult batch{};
    CallbackId id{};
    std::int64_t filter{};
    unsigned calls{};

    bool InvokeBatch(CallbackId requested, std::int64_t requestedFilter,
                     CallbackBatchResult* output,
                     const ModHandle* = nullptr) noexcept override {
        ++calls;
        id = requested;
        filter = requestedFilter;
        *output = batch;
        return true;
    }
    Status Invoke(const CallbackDescriptor&) noexcept override {
        return Status{StatusCode::Unsupported};
    }
    Status InvokeCollecting(const CallbackDescriptor&,
                            CallbackReturn*) noexcept override {
        return Status{StatusCode::Unsupported};
    }
};

static bool Run(FakeInvoker& invoker, CallbackRegistry& registry,
                bool nonNil, bool truthy, unsigned failed = 0) {
    invoker.batch = {};
    invoker.batch.failed = failed;
    invoker.batch.returned.nonNil = nonNil;
    invoker.batch.returned.truthy = truthy;
    CallbackDispatcher dispatcher{registry, invoker};
    return player_take_damage::DispatchPrePlayerTakeDamage(dispatcher, 31);
}

int main() {
    CallbackRegistry registry;
    FakeInvoker invoker;

    assert(Run(invoker, registry, true, false));
    assert(invoker.id == 1008);
    assert(invoker.filter == 31);

    assert(!Run(invoker, registry, false, false));
    assert(!Run(invoker, registry, true, true));
    assert(!Run(invoker, registry, true, false, 1));
    assert(invoker.calls == 4);
}
'''

ENTRY_DRIVER = r'''
#include "player_take_damage_callback.hpp"
#include "player_damage_internal_hook.hpp"
#include "application/callback/extended_callback_runtime.hpp"
#include "infrastructure/memory/engine_field_access.hpp"

#include <cassert>
#include <cstdint>

static bool callbackCalled{};
static bool cancel{};
static bool originalCalled{};
static unsigned entryDispatches{};
static unsigned postDispatches{};
static std::uint64_t Replay(void*, float, std::uint64_t, const void*,
                            std::int32_t);

namespace LuaRuntime {
bool DispatchPrePlayerTakeDamage(std::uintptr_t player, float damage,
                                 std::uint64_t flags, std::uintptr_t source,
                                 std::int32_t countdown) noexcept {
    assert(!originalCalled);
    callbackCalled = true;
    assert(player == 0x123400);
    assert(damage == 1.25F);
    assert(flags == 0x100000003ULL);
    assert(source == 0x432100);
    assert(countdown == 17);
    return cancel;
}
bool DispatchEntityTakeDamage(std::uintptr_t, float, std::uint64_t,
                              std::uintptr_t, std::int32_t, std::int32_t) {
    ++entryDispatches;
    return false;
}
void DispatchPostEntityTakeDamageValues(const isaac::runtime::damage::Values&) {
    ++postDispatches;
}
}

namespace isaac::runtime {
enum class HookId { EntityPlayerTakeDamage, EntityTakeDamage };
template <class Fn> Fn Original(HookId) { return &Replay; }
bool ReadEntityIdentity(std::uintptr_t, std::uint32_t* type,
                        std::uint32_t* variant) {
    *type = 1;
    *variant = 31;
    return true;
}
}

static std::uint64_t Replay(void*, float amount, std::uint64_t flags,
                            const void* source, std::int32_t countdown) {
    originalCalled = true;
    assert(amount == 1.25F);
    assert(flags == 0x100000003ULL);
    assert(reinterpret_cast<std::uintptr_t>(source) == 0x432100);
    assert(countdown == 17);
    return 7;
}

int main() {
    cancel = false;
    assert(EntryRelayEntityPlayerTakeDamageCallback(
               reinterpret_cast<void*>(0x123400), 1.25F, 0x100000003ULL,
               reinterpret_cast<void*>(0x432100), 17) == 7);
    assert(callbackCalled && originalCalled);

    callbackCalled = false;
    originalCalled = false;
    cancel = true;
    assert(EntryRelayEntityPlayerTakeDamageCallback(
               reinterpret_cast<void*>(0x123400), 1.25F, 0x100000003ULL,
               reinterpret_cast<void*>(0x432100), 17) == 0);
    assert(callbackCalled && !originalCalled);
    assert(entryDispatches == 0);
    assert(postDispatches == 0);
}
'''


class PrePlayerTakeDamageCallbackTests(unittest.TestCase):
    def build(self, folder, driver, sources):
        folder = Path(folder)
        (folder / "driver.cpp").write_text(driver)
        binary = folder / "driver"
        result = subprocess.run(
            ["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror",
             f"-I{SOURCE}", f"-I{UNITS}", str(folder / "driver.cpp"),
             *map(str, sources), "-o", str(binary)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return binary

    def test_only_literal_false_cancels_and_filter_is_player_variant(self):
        helper = SOURCE / "player_take_damage_callback.cpp"
        self.assertTrue(helper.is_file(), "MC_PRE_PLAYER_TAKE_DMG helper missing")
        with tempfile.TemporaryDirectory(prefix="pre-player-damage-return-") as folder:
            binary = self.build(
                folder, RETURN_DRIVER,
                [helper, UNITS / "application/callback/callback_dispatcher.cpp",
                 UNITS / "application/callback/callback_registry.cpp"],
            )
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_player_method_entry_dispatches_before_native_gates_and_cancels(self):
        path = SOURCE / "hook_manager.cpp"
        if not path.is_file():
            path = SOURCE.parents[2] / "private/runtime/source/hook_manager.cpp"
        if not path.is_file():
            self.skipTest("player entry wrapper requires assembled private source")
        text = path.read_text()
        common = (
            "template <typename Fn>\n"
            + function(text, "std::uint64_t RunEntityTakeDamageRelay(")
        )
        wrapper = function(
            text, 'extern "C" std::uint64_t EntryRelayEntityPlayerTakeDamageCallback('
        )
        with tempfile.TemporaryDirectory(prefix="pre-player-damage-entry-") as folder:
            driver = Path(folder) / "entry.cpp"
            driver.write_text(
                ENTRY_DRIVER.replace(
                    "int main() {", common + "\n" + wrapper + "\nint main() {", 1
                )
            )
            binary = self.build(
                folder, driver.read_text(),
                [SOURCE / "player_damage_internal_hook.cpp", SOURCE / "damage_context.cpp"],
            )
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_central_registration_dispatcher_arguments_filter_and_declaration(self):
        callbacks = UNITS / "interfaces/lua/repentogon_callbacks.cpp"
        runtime = SOURCE / "lua_runtime.cpp"
        header = SOURCE / "lua_runtime.hpp"
        callback_text = callbacks.read_text()
        self.assertTrue(
            re.search(r'\{\s*1008\s*,\s*"MC_PRE_PLAYER_TAKE_DMG"\s*\}', callback_text),
            "MC_PRE_PLAYER_TAKE_DMG must be registered as callback 1008",
        )
        self.assertTrue(
            re.search(r"static_assert\s*\(\s*kCallbackCount\s*==\s*140\s*\)", callback_text),
            "the REPENTOGON callback registration count must include the final batch",
        )

        declaration = (
            "bool DispatchPrePlayerTakeDamage(std::uintptr_t player,float damage,"
            "std::uint64_t damageFlags,std::uintptr_t sourceRef,"
            "std::int32_t damageCountdown) noexcept"
        )
        self.assertIn(
            re.sub(r"\s+", "", declaration),
            re.sub(r"\s+", "", header.read_text()),
        )

        body = re.sub(r"\s+", "", function(
            runtime.read_text(), "bool DispatchPrePlayerTakeDamage("
        ))
        expected = [
            "BuiltinCallbackEnabled(ptd::kPrePlayerTakeDamageCallbackId)",
            "ReadEntityIdentity(player,&type,&variant)",
            "AddEntity(player)",
            "AddFloat(damage)",
            "AddInteger(static_cast<std::int64_t>(damageFlags))",
            "AddReference(sourceRef)",
            "AddInteger(static_cast<std::int64_t>(damageCountdown))",
            "ptd::DispatchPrePlayerTakeDamage(dispatcher,filter)",
        ]
        for token in expected:
            self.assertIn(token, body, f"central 1008 wiring missing {token}")
        self.assertNotIn("FindExtraSource", body,
                         "1008 Source must remain the original EntityRef, not ExtraSource")
        self.assertLess(body.index("BuiltinCallbackEnabled(ptd::kPrePlayerTakeDamageCallbackId)"),
                        body.index("ReadEntityIdentity(player,&type,&variant)"),
                        "disabled/unregistered 1008 must avoid field reads")


if __name__ == "__main__":
    unittest.main()
