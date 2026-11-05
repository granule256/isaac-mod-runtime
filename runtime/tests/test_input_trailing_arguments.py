"""PC input bindings consume two arguments without rejecting compatibility tails."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from .test_support import build_lua_harness

ROOT = Path(__file__).resolve().parents[2]

DRIVER = r'''
#include "lua_runtime.hpp"
#include <cstdio>
#include <cstring>
#include <string>
bool Button(void*, unsigned, unsigned, void*) { return false; }
float Value(void*, unsigned, unsigned, void*) { return 0; }
int main(int argc, char** argv) {
    if (argc != 2) return 90;
    LuaRuntime::SetInputBindings(reinterpret_cast<std::uintptr_t>(&Button),
        reinterpret_cast<std::uintptr_t>(&Button), reinterpret_cast<std::uintptr_t>(&Value));
    LuaRuntime::SetInputButtonBindings(reinterpret_cast<std::uintptr_t>(&Button), 0);
    std::string script;
    if (!std::strcmp(argv[1], "api")) {
        script = R"lua(
for _, name in ipairs({'IsActionPressed','IsActionTriggered','GetActionValue',
                       'IsButtonPressed','IsButtonTriggered','GetButtonValue'}) do
    local query = Input[name]
    local baseline = query(13, 1)
    assert(query(13, 1, true) == baseline, name..' rejected a compatibility flag')
    assert(query(13, 1, false) == baseline)
    assert(query(13, 1, nil) == baseline)
    assert(query(13, 1, 0) == baseline)
    assert(query(13, 1, 'unused', {}, function() error('must not run') end) == baseline)
    assert(query('13', '1', true) == baseline)
    assert(not pcall(query, 13), name..' accepted a missing controller')
    assert(not pcall(query, {}, 1, true), name..' accepted an invalid input code')
    assert(not pcall(query, 13, 0.5, true), name..' accepted a fractional controller')
end
)lua";
    } else {
        script = "input_probe={early=0,bag=0,recipe=0,chance=0};";
        if (!std::strcmp(argv[1], "render-with-menu")) {
            script += R"lua(
local menu=RegisterMod('menu-before-recipe',1)
menu:AddCallback(ModCallbacks.MC_POST_RENDER,function()input_probe.early=input_probe.early+1 end)
)lua";
        }
        script += R"lua(
local bag=RegisterMod('recipe-input',1)
local chance=RegisterMod('chance-after-recipe',1)
local displayingRecipeList=false
bag:AddCallback(ModCallbacks.MC_POST_RENDER,function()
    input_probe.bag=input_probe.bag+1
    -- The recipe screen becomes active only after enough pickups accumulate.
    if input_probe.bag==3 then displayingRecipeList=true end
    if displayingRecipeList then
        local held=Input.IsActionPressed(ButtonAction.ACTION_MAP,1,true)
        if held then error('no native device is pressed in this fixture') end
        input_probe.recipe=input_probe.recipe+1
    end
end)
chance:AddCallback(ModCallbacks.MC_POST_RENDER,function()
    input_probe.chance=input_probe.chance+1
end)
)lua";
    }
    if (LuaRuntime::InitializeFromBuffer(script.data(), script.size(), "@input-tail.lua") !=
        LuaRuntime::LuaInitResult::Success) {
        char error[512]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
        std::fprintf(stderr,"initialization: %s\n",error);return 1;
    }
    if (!std::strcmp(argv[1], "api")) return 0;
    unsigned failures=0;
    for (unsigned frame=0;frame<6;++frame) {
        LuaRuntime::DispatchPostRender(1);
        failures+=LuaRuntime::TakeCallbackError()?1:0;
    }
    double bag=0,recipe=0,chance=0,early=0;
    if (LuaRuntime::ReadLuaTableNumber("input_probe","bag",&bag) ||
        LuaRuntime::ReadLuaTableNumber("input_probe","recipe",&recipe) ||
        LuaRuntime::ReadLuaTableNumber("input_probe","chance",&chance) ||
        LuaRuntime::ReadLuaTableNumber("input_probe","early",&early)) return 2;
    std::printf("bag=%.0f recipe=%.0f chance=%.0f early=%.0f failed_frames=%u\n",
                bag,recipe,chance,early,failures);
    if (failures || bag!=6 || recipe!=4 || chance!=6) {
        char error[512]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
        std::fprintf(stderr,"recipe input interrupted later render callbacks: %s\n",error);
        return 3;
    }
    return !std::strcmp(argv[1],"render-with-menu") && early!=6 ? 4 : 0;
}
'''


class InputTrailingArgumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='isaac-input-tail-')
        cls.binary = build_lua_harness(source_root=ROOT/'runtime/source',
            workdir=Path(cls.temporary.name), harness_source=DRIVER)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def check(self, scenario):
        result = subprocess.run([str(self.binary), scenario], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_input_family_ignores_tails_but_validates_required_arguments(self):
        self.check('api')

    def test_recipe_input_does_not_stop_later_mod_renderers(self):
        self.check('render')

    def test_menu_callback_is_not_required_for_recipe_input_failure(self):
        self.check('render-with-menu')
