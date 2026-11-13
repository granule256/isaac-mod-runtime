"""EntityPlayer:SetActiveCharge defaults the optional ActiveSlot to SLOT_PRIMARY."""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import build_lua_harness, layered_lua_runtime_sources
except ImportError:
    from test_support import build_lua_harness, layered_lua_runtime_sources


SOURCE = Path(__file__).resolve().parent.parent / "source"
ROOT = Path(__file__).resolve().parents[2]
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
SHAPES = ROOT / "runtime" / "src" / "interfaces" / "lua" / "engine_method_api.hpp"

CHARGE = 4
EXPLICIT_SLOT = 3

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"
#include "interfaces/lua/engine_method_api.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

extern "C" {
extern std::uint32_t g_HostEngineCallTrampolineCalls;
extern std::uintptr_t g_HostEngineCallTrampolineLastTarget;
extern std::uint64_t g_HostEngineCallTrampolineLastIntegers[8];
}

namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::uintptr_t g_EngineBase = 0;

constexpr std::size_t kModuleBytesSize =
    kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t);
constexpr std::size_t kGameBytesSize =
    kGamePlayerArrayEndOffset + sizeof(std::uint64_t);

static_assert(kEntityPlayerSetActiveChargeOffset < kGameOwnerGlobalSlotOffset);

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

void PlantEntryWord(std::size_t offset, std::uint32_t word) {
    for (std::size_t index = 0; index < 4; ++index) {
        g_ModuleBytes[offset + index] =
            static_cast<unsigned char>((word >> (8 * index)) & 0xFFU);
    }
}

void PublishFakeWorld() {
    g_ModuleBytes.assign(kModuleBytesSize, 0);
    g_EngineBase = reinterpret_cast<std::uintptr_t>(g_ModuleBytes.data());
    PlantEntryWord(kEntityPlayerSetActiveChargeOffset,
                   kEntityPlayerSetActiveChargeEntryWord);

    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGameBytesSize, 0);
    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uintptr_t>(g_PlayerBytes, 0,
                            g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, kEntityTypePlayer);

    g_PlayerArrayBytes.assign(2 * sizeof(std::uint64_t), 0);
    WriteAt<std::uint64_t>(
        g_PlayerArrayBytes, 0,
        reinterpret_cast<std::uintptr_t>(g_PlayerBytes.data()));
    WriteAt<std::uint64_t>(
        g_GameBytes, kGamePlayerArrayBeginOffset,
        reinterpret_cast<std::uintptr_t>(g_PlayerArrayBytes.data()));
    WriteAt<std::uint64_t>(
        g_GameBytes, kGamePlayerArrayEndOffset,
        reinterpret_cast<std::uintptr_t>(g_PlayerArrayBytes.data()) +
            sizeof(std::uint64_t));

    WriteAt<std::uint64_t>(
        g_ModuleBytes, kGameOwnerGlobalSlotOffset,
        reinterpret_cast<std::uintptr_t>(g_OwnerSlotBytes.data()));
    WriteAt<std::uint64_t>(
        g_OwnerSlotBytes, 0,
        reinterpret_cast<std::uintptr_t>(g_GameBytes.data()));
    LuaRuntime::SetEngineModuleBase(g_EngineBase);
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = nullptr;
    return GameRoomObservation::GameNull;
}

int main(int argc, char** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    PublishFakeWorld();
    LuaRuntime::SetGameBindings(
        reinterpret_cast<std::uintptr_t>(g_OwnerSlotBytes.data()), 0x2222);

    std::string script =
        "local function ok(f) return tostring(select(1, pcall(f))) end\n"
        "local function err(f) return tostring(select(2, pcall(f))) end\n"
        "local p = Isaac.GetPlayer(0)\n"
        "print('SAC p=' .. type(p))\n"
        "print('SAC fn=' .. type(p and p.SetActiveCharge))\n";
    if (std::strcmp(scenario, "omitted") == 0) {
        script += "print('SAC ok=' .. ok(function() return p:SetActiveCharge(4) end))\n";
    } else if (std::strcmp(scenario, "explicit") == 0) {
        script += "print('SAC ok=' .. ok(function() return p:SetActiveCharge(4, 3) end))\n";
    } else if (std::strcmp(scenario, "nil_slot") == 0) {
        script +=
            "print('SAC ok=' .. ok(function() return p:SetActiveCharge(4, nil) end))\n";
    } else if (std::strcmp(scenario, "missing_charge") == 0) {
        script +=
            "print('SAC ok=' .. ok(function() return p:SetActiveCharge() end))\n"
            "print('SAC msg=' .. err(function() return p:SetActiveCharge() end))\n";
    } else if (std::strcmp(scenario, "bad_charge") == 0) {
        script +=
            "print('SAC ok=' .. ok(function() return p:SetActiveCharge({}) end))\n"
            "print('SAC msg=' .. err(function() return p:SetActiveCharge({}) end))\n";
    } else if (std::strcmp(scenario, "bad_slot") == 0) {
        script +=
            "print('SAC ok=' .. ok(function() return p:SetActiveCharge(4, {}) end))\n"
            "print('SAC msg=' .. err(function() return p:SetActiveCharge(4, {}) end))\n";
    } else if (std::strcmp(scenario, "extra") == 0) {
        script +=
            "print('SAC ok=' .. ok(function() return p:SetActiveCharge(4, 0, 0) end))\n"
            "print('SAC msg=' .. err(function() return p:SetActiveCharge(4, 0, 0) end))\n";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(
        script.c_str(), script.size(), "@set-active-charge.lua");
    static_cast<void>(result);
    std::printf("SAC base=0x%llX\n",
                static_cast<unsigned long long>(g_EngineBase));
    std::printf("SAC player=0x%llX\n",
                static_cast<unsigned long long>(
                    reinterpret_cast<std::uintptr_t>(g_PlayerBytes.data())));
    std::printf("SAC calls=%u\n", g_HostEngineCallTrampolineCalls);
    std::printf("SAC target=0x%llX\n",
                static_cast<unsigned long long>(
                    g_HostEngineCallTrampolineLastTarget));
    std::printf("SAC x0=0x%llX\n",
                static_cast<unsigned long long>(
                    g_HostEngineCallTrampolineLastIntegers[0]));
    std::printf("SAC x1=0x%llX\n",
                static_cast<unsigned long long>(
                    g_HostEngineCallTrampolineLastIntegers[1]));
    std::printf("SAC x2=0x%llX\n",
                static_cast<unsigned long long>(
                    g_HostEngineCallTrampolineLastIntegers[2]));
    return 0;
}
'''


class SetActiveChargeDefaultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-set-active-charge-")
        notification = (
            ROOT
            / "runtime"
            / "src"
            / "interfaces"
            / "lua"
            / "repentogon_achievement_notification.cpp"
        )
        extra_sources = (
            ()
            if not notification.exists() or notification in layered_lua_runtime_sources(SOURCE)
            else (notification,)
        )
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS,
            extra_sources=extra_sources,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario):
        result = subprocess.run(
            [str(self.binary), scenario], text=True, capture_output=True
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    @staticmethod
    def value(output, label):
        match = re.search(rf"^{re.escape(label)}=(\S+)$", output, re.M)
        if match is None:
            raise AssertionError(f"missing {label}:\n{output}")
        return match.group(1)

    def assert_engine_call(self, output, slot):
        self.assertIn("SAC p=userdata", output)
        self.assertIn("SAC fn=function", output)
        self.assertIn("SAC ok=true", output)
        self.assertEqual(self.value(output, "SAC calls"), "1", output)
        base = int(self.value(output, "SAC base"), 16)
        self.assertEqual(
            int(self.value(output, "SAC target"), 16),
            base + 0x27F984,
            output,
        )
        self.assertEqual(
            int(self.value(output, "SAC x0"), 16),
            int(self.value(output, "SAC player"), 16),
            output,
        )
        self.assertEqual(int(self.value(output, "SAC x1"), 16), CHARGE, output)
        self.assertEqual(int(self.value(output, "SAC x2"), 16), slot, output)

    def test_omitted_slot_defaults_to_primary(self):
        self.assert_engine_call(self.run_scenario("omitted"), 0)

    def test_explicit_slot_is_forwarded(self):
        self.assert_engine_call(self.run_scenario("explicit"), EXPLICIT_SLOT)

    def test_nil_slot_uses_optinteger_default(self):
        self.assert_engine_call(self.run_scenario("nil_slot"), 0)

    def test_required_charge_and_argument_types_are_gated(self):
        for scenario in ("missing_charge", "bad_charge", "bad_slot", "extra"):
            with self.subTest(scenario=scenario):
                output = self.run_scenario(scenario)
                self.assertIn("SAC ok=false", output)
                self.assertIn("EntityPlayer:SetActiveCharge expects", output)
                self.assertEqual(self.value(output, "SAC calls"), "0", output)

    def test_uses_a_shared_optional_int_shape(self):
        shapes = SHAPES.read_text(encoding="utf-8")
        rows = ISAAC_API.read_text(encoding="utf-8")
        self.assertRegex(shapes, r"IntDefaultZero\s*=\s*\d+,")
        self.assertRegex(shapes, r"VoidIntIntOpt1\s*=\s*\d+,")
        self.assertRegex(
            rows,
            r"\{2, \{EngineArgKind::Int, EngineArgKind::IntDefaultZero,[^}]*\},\s*\n"
            r"\s*EngineReturnKind::Void, FieldReceipt::EntityPlayer, "
            r"IntArgumentGuard::None, 1,\s*\{0, 0, 0\}\}",
        )
        self.assertRegex(
            rows,
            r"FieldReceipt::EntityPlayer,\s*EngineCallShape::VoidIntIntOpt1,\s*2,\s*0xFF",
        )


if __name__ == "__main__":
    unittest.main()
