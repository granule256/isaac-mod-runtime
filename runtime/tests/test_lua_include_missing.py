"""A missing include returns its diagnostic on PC and lets the caller continue."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from .test_support import build_lua_harness
from . import test_support

SOURCE = Path(__file__).resolve().parents[1] / "source"
HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_file_reader.hpp"
#include "program/mod_player_names.hpp"
#include <cstdio>
#include <cstring>

namespace GameFileReader {
TextReadResult ReadTextFile(const Bindings&, const char* path, u8* buffer,
                            std::size_t capacity, std::size_t* length) {
    const char* text = nullptr;
    if (std::strstr(path, "/good.lua")) text = "loads=(loads or 0)+1;return loads,37";
    if (std::strstr(path, "/syntax.lua")) text = "local broken = )";
    if (std::strstr(path, "/execute.lua")) text = "error('module failed')";
    if (std::strstr(path, "/read.lua")) return TextReadResult::ReadMismatch;
    if (!text) return TextReadResult::OpenFailed;
    *length = std::strlen(text);
    if (*length > capacity) return TextReadResult::LengthOutOfRange;
    std::memcpy(buffer, text, *length);
    return TextReadResult::Success;
}
}

int main() {
    const char* xml = "<players><player name='Door Menu Detector'/></players>";
    (void)isaac::runtime::IngestModPlayersXml("Menu", xml, std::strlen(xml));
    const char* entry = R"lua(
        local mod=RegisterMod('Menu',1)
        for i=1,40 do
            local ok,diagnostic=pcall(include,'optional')
            assert(ok,diagnostic)
            assert(type(diagnostic)=='string' and diagnostic:find("module 'optional' not found:",1,true))
            assert(diagnostic:find('rom:/isaac_mods/mods/Menu/optional.lua',1,true))
        end
        include('optional')
        mod.technical_character=Isaac.GetPlayerTypeByName('Door Menu Detector')
        assert(mod.technical_character==41)
        assert(not pcall(require,'optional'))
        for _,name in ipairs({'syntax','execute','read','../escape'}) do
            assert(not pcall(include,name),name..' must still fail')
        end
        local a,b=include('good');assert(a==1 and b==37)
        a,b=include('good');assert(a==2 and b==37)
        mod:AddCallback(ModCallbacks.MC_POST_UPDATE,function()end)
    )lua";
    const auto result=LuaRuntime::InitializeManifestMod(entry,std::strlen(entry),
        "@rom:/isaac_mods/mods/Menu/main.lua","rom:/isaac_mods/mods/Menu",{});
    char error[1024]{};
    (void)LuaRuntime::CopyLastLuaErrorText(error,sizeof(error));
    std::printf("status=%u error=%s\n",unsigned(result),error);
    return result==LuaRuntime::LuaInitResult::Success?0:1;
}
'''


class LuaIncludeMissingTests(unittest.TestCase):
    def test_missing_optional_file_does_not_abort_character_registration(self):
        with tempfile.TemporaryDirectory(prefix="isaac-include-missing-") as temporary:
            flags = tuple(flag for flag in test_support.HARNESS_COMPILE_FLAGS
                          if not flag.startswith("-DEXL_DIAGNOSTIC_STAGE="))
            with patch.object(test_support, "HARNESS_COMPILE_FLAGS", flags):
                binary = build_lua_harness(source_root=SOURCE, workdir=Path(temporary),
                                           harness_source=HARNESS)
            result = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
