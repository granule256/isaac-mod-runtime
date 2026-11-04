"""Production effect scan initializes reused addresses for each native lifetime."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from . import test_lua_entity_query as fixture
from . import test_support


MAIN = r'''
#include "interfaces/lua/entity_lifetime.hpp"
int main() {
    static_cast<void>(kScriptTemplate);
    static_cast<void>(&HarnessHasCollectible);
    static_cast<void>(&BuildPrelude);
    CreateBlocks(); FillEntities(); PublishLists(); PublishGame();
    PublishEntityList(g_RoomBytes, true);
    // The production callback scan uses the all-live table, not the effect query partition.
    WriteWord(g_LiveArrayBytes, 0, AddressOf(g_Entities[kEffect]));
    WriteAt<std::uint32_t>(g_RoomBytes,
        kRoomEntityListOffset + kEntityListLiveCountOffset, 1);
    LuaRuntime::SetEngineModuleBase(g_EngineBase);
    LuaRuntime::SetGameBindings(g_EngineBase + kGameOwnerGlobalSlotOffset, 0x2222);
    const char* script = R"lua(
local m = RegisterMod('effect lifecycle', 1)
otherInit, animationInit, animationUpdate = 0, 0, 0
m:AddCallback(ModCallbacks.MC_POST_EFFECT_INIT, function(_, effect)
    if effect.Variant == 7 then otherInit = otherInit + 1 end
end)
m:AddCallback(ModCallbacks.MC_POST_EFFECT_INIT, function(_, effect)
    assert(not effect:GetData().initialized, 'duplicate effect INIT')
    effect:GetData().initialized = true
    animationInit = animationInit + 1
end, 999)
m:AddCallback(ModCallbacks.MC_POST_EFFECT_UPDATE, function(_, effect)
    assert(effect:GetData().initialized, 'new effect UPDATE before INIT')
    animationUpdate = animationUpdate + 1
end, 999)
)lua";
    if (LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@effect-lifecycle.lua") !=
        LuaRuntime::LuaInitResult::Success) return 1;
    LuaRuntime::DispatchPostUpdate();
    LuaRuntime::DispatchPostUpdate();
    if (!ExpectNumber("otherInit", 1) || !ExpectNumber("animationInit", 0)) return 2;
    const auto effect = AddressOf(g_Entities[kEffect]);
    // D2 retires variant 7; allocator reuses exactly its address for the animation variant.
    isaac::runtime::RetireEntityLifetime(effect);
    WriteAt<std::uint32_t>(g_Entities[kEffect], kEntityVariantOffset, 999);
    LuaRuntime::DispatchPostUpdate();
    LuaRuntime::DispatchPostUpdate();
    if (!ExpectNumber("animationInit", 1) || !ExpectNumber("animationUpdate", 2)) return 3;
    // Reuse for the same variant must also create a fresh initialized lifetime.
    isaac::runtime::RetireEntityLifetime(effect);
    LuaRuntime::DispatchPostUpdate();
    LuaRuntime::DispatchPostUpdate();
    if (!ExpectNumber("animationInit", 2) || !ExpectNumber("animationUpdate", 4)) return 4;
    if (LuaRuntime::TakeCallbackError()) {
        LuaRuntime::LuaErrorHistoryEntryView errors[16]{};
        const auto count = LuaRuntime::CopyLuaErrorHistory(errors, 16);
        for (std::size_t i = 0; i < count; ++i) std::puts(errors[i].text);
        return 5;
    }
    return 0;
}
'''


class EffectCallbackLifecycleTests(unittest.TestCase):
    def test_scan_initializes_reused_effect_address_before_update(self):
        flags = tuple(flag for flag in test_support.HARNESS_COMPILE_FLAGS
                      if not flag.startswith("-DEXL_DIAGNOSTIC_STAGE="))
        with tempfile.TemporaryDirectory(prefix="isaac-effect-lifecycle-") as temp:
            with patch.object(test_support, "HARNESS_COMPILE_FLAGS", flags):
                binary = test_support.build_lua_harness(
                    source_root=fixture.SOURCE, workdir=Path(temp),
                    harness_source=fixture.HARNESS.split("int main(", 1)[0] + MAIN)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
