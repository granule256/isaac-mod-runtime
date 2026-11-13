"""Pickup override state follows native reroll decisions and entity lifetimes."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_support
from .test_repentogon_entity_api import DRIVER, SOURCE

HELPERS = r'''
static int InspectOverride(lua_State* state) {
    bool value{};
    const bool exists=TryPickupRerollOverride(Address(pickup),&value);
    assert(exists==static_cast<bool>(lua_toboolean(state,1)));
    if(exists)assert(value==static_cast<bool>(lua_toboolean(state,2)));
    return 0;
}
static int Lifecycle(lua_State* state) {
    switch(luaL_checkinteger(state,1)) {
    case 0: ClearEntityLifetimeData(Address(pickup));break;
    case 1: ReinitializeEntityLifetime(Address(pickup));break;
    case 2: RetireEntityLifetime(Address(pickup));break;
    case 3: PushEntityCallbackArgument(state,Address(pickup));return 1;
    case 4: ResetEntityLifetimeState();break;
    }
    return 0;
}
'''
SCRIPT = r'''
assert(pickup:GetCanRerollOverride() == nil)
_inspect(false)
pickup:SetCanRerollOverride(false)
assert(pickup:GetCanRerollOverride() == false)
_inspect(true,false)
_lifecycle(0);_inspect(true,false)
pickup:SetCanRerollOverride(true)
assert(pickup:GetCanRerollOverride() == true)
_inspect(true,true)
assert(not pcall(function() pickup:SetCanRerollOverride(nil) end))
for _,value in ipairs({1,0,"",{}}) do
  pickup:SetCanRerollOverride(value);assert(pickup:GetCanRerollOverride()==true)
end
pickup:SetCanRerollOverride();assert(pickup:GetCanRerollOverride()==false)
pickup:ClearCanRerollOverride()
assert(pickup:GetCanRerollOverride() == nil)
_inspect(false)
pickup:SetCanRerollOverride(true);_lifecycle(1);_inspect(false)
assert(pickup:GetCanRerollOverride() == nil)
pickup:SetCanRerollOverride(false);_lifecycle(2);_inspect(false)
assert(not pcall(function() pickup:GetCanRerollOverride() end))
pickup = _lifecycle(3)
assert(pickup:GetCanRerollOverride() == nil)
pickup:SetCanRerollOverride(true)
_lifecycle(4)
pickup:SetCanRerollOverride(false)
_inspect(true,false)
pickup:ClearCanRerollOverride();_inspect(false)

'''

class RerollOverrideTests(unittest.TestCase):
    def test_pickup_override_registration_and_optional_boolean(self):
        driver = '#include "interfaces/lua/entity_lifetime.hpp"\n' + DRIVER
        driver = driver.replace('static void Extensions(', HELPERS + '\nstatic void Extensions(')
        driver = driver.replace('static void Extensions(lua_State* state) noexcept{',
            'static void Extensions(lua_State* state) noexcept{' +
            'lua_pushcfunction(state,InspectOverride);lua_setglobal(state,"_inspect");' +
            'lua_pushcfunction(state,Lifecycle);lua_setglobal(state,"_lifecycle");')
        driver = driver.replace("local car=entity:", SCRIPT + "\nlocal car=entity:")
        with tempfile.TemporaryDirectory(prefix="reroll-override-") as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=driver)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

if __name__ == "__main__":
    unittest.main()
