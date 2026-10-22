"""真实Lua运行时的平台设置接口与MCM选项闭包，不改作者模组。"""
import subprocess
import unittest
from . import test_lua_api_gap_mcm as base

SCRIPT = r'''
local a,b,t=SwitchConsole.GetControls()
assert(a==4 and b==5 and t==8)
for _,args in ipairs({{-1,5,8},{4,14,8},{4,5,0},{4,5,51},{4,5,2.5},{4,5,8,9}}) do
 assert(not pcall(SwitchConsole.SetControls,table.unpack(args)))
end
assert(SwitchConsole.SetControls(6,7,2))
assert(select(3,SwitchConsole.GetControls())==2)
ModConfigMenu={OptionType={NUMBER=5,BOOLEAN=4},Options={}}
function ModConfigMenu.AddSetting(category,sub,option)
 assert(category=="Console" and sub=="Controls")
 table.insert(ModConfigMenu.Options,option)
end
'''
VERIFY = r'''
assert(ModConfigMenu.SwitchConsoleSettingsInstalled)
local o=ModConfigMenu.Options
assert(#o==4 and o[1].CurrentSetting()==3 and o[2].CurrentSetting()==4)
assert(o[1].Display()=="Open button 1: X" and o[2].Display()=="Open button 2: Y")
o[1].OnChange(5);o[2].OnChange(0);o[3].OnChange(50)
local a,b,t=SwitchConsole.GetControls();assert(a==8 and b==255 and t==50)
assert(o[1].Display()=="Open button 1: L" and o[2].Display()=="Open button 2: None")
assert(o[3].Display()=="Hold time: 5.0 s")
o[4].OnChange(true)
a,b,t=SwitchConsole.GetControls();assert(a==4 and b==5 and t==8)
assert(o[1].CurrentSetting()==1 and o[2].CurrentSetting()==2)
MCM_API_OK=1
'''

class ConsoleControlsLuaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        original=base.render_harness
        def render():
            text=original()
            text='#include "interfaces/lua/console_controls_menu.hpp"\n'+text
            start=text.index('const char* kScriptTemplate = R"lua(')
            end=text.index(')lua";',start)+len(')lua";')
            text=text[:start]+'const char* kScriptTemplate = R"lua('+SCRIPT+')lua";'+text[end:]
            text=text.replace('const std::string script =','std::string script =')
            at='    const auto result =\n        LuaRuntime::InitializeFromBuffer'
            text=text.replace(at,'    script += "\\n";script += kConsoleControlsMenuScript;script += R"lua('+VERIFY+')lua";\n'+at)
            return text
        base.render_harness=render
        try:
            base.LuaApiGapMcmTests.setUpClass.__func__(cls)
        finally:
            base.render_harness=original
    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()
    def test_menu_changes_real_native_controls(self):
        result=subprocess.run([str(self.binary),'no_base'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
