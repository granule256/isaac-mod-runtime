"""Character strings used while positioning a stat overlay reach native font measurement."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_support import build_lua_harness

ROOT = Path(__file__).resolve().parents[2]
MAIN = r'''
int main() {
    PublishFakeBindings();
    const char* script = R"lua(
local mod = RegisterMod('Character width', 1)
local font = Font()
assert(font:Load('font/luaminioutlined.fnt'))
mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function()
    -- A numeric string must measure the digit, not character code 3.
    assert(font:GetCharacterWidth('3') == font:GetCharacterWidth(51))
    assert(font:GetCharacterWidth('A') == 70)
    local width = 0
    for character in ('3.50'):gmatch('.') do
        width = width + font:GetCharacterWidth(character)
    end
    assert(width == 218)
    for _, invalid in ipairs({'', 'AB', string.char(128), 'é', -1, 128, 1.5, false, {}}) do
        assert(not pcall(font.GetCharacterWidth, font, invalid))
    end
end)
)lua";
    if (LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@character-width.lua") !=
            LuaRuntime::LuaInitResult::Success) return 1;
    for (int i = 0; i < 2; ++i) {
        LuaRuntime::DispatchPostUpdate();
        if (LuaRuntime::TakeCallbackError()) {
            char error[512]{};
            static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error)));
            std::fprintf(stderr, "%s\n", error);
            return 2;
        }
    }
    return 0;
}
'''


class FontCharacterWidthTests(unittest.TestCase):
    def test_stat_text_character_strings_and_argument_guards(self):
        fixture = (ROOT / 'runtime/tests/font_gc_pressure_harness.cpp').read_text()
        prefix = fixture[:fixture.index('[[maybe_unused]] const char* kUnavailableScript')]
        with tempfile.TemporaryDirectory(prefix='font-character-width-') as directory:
            binary = build_lua_harness(
                source_root=ROOT / 'runtime/source', workdir=Path(directory),
                harness_source=prefix + '\n}\n' + MAIN)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
