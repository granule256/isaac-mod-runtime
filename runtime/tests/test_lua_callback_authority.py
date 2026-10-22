"""共享PC回调表的真实Lua对照；运行完整PC启动原件与项目实现。"""
import unittest
from . import test_pc_bootstrap_callback_parity as pc

BASE = "_order='';_mode=0;local m=RegisterMod('authority',1);m:AddCallback(1,function() end)\n"
CASES = {
    'diagnostic_hook_ignores_overridden_global_pcall': (BASE + "local saved=pcall;pcall=function() error('unexpected-diagnostic-pcall') end;local fn=function() _order=_order..'P' end;m:AddCallback('private-diagnostic',fn);pcall=saved;Isaac.RunCallback('private-diagnostic');assert(_order=='P');pcall=function() error('unexpected-diagnostic-pcall') end;m:RemoveCallback('private-diagnostic',fn);pcall=saved;_order='';Isaac.RunCallback('private-diagnostic');assert(_order=='')",21,0,'nil'),
    'numeric_false_param': (BASE + "m:AddCallback(20,function() _order=_order..'A' end,false)", 20, 0, '7'),
    'numeric_arbitrary_param': (BASE + "local p={};m:AddCallback(20,function() end,p);assert(Isaac.GetCallbacks(20)[1].Param==p)",20,0,'nil'),
    'named_false_wildcard': (BASE + "m:AddCallback('named',function() _order=_order..'A' end,false);Isaac.RunCallbackWithParam('named',7)",20,0,'nil'),
    'named_minus_one_wildcard': (BASE + "m:AddCallback('named',function() _order=_order..'A' end,-1);Isaac.RunCallbackWithParam('named','text')",20,0,'nil'),
    'named_param_shape': (BASE + "local p={};m:AddCallback('named',function() end,p);assert(Isaac.GetCallbacks('named')[1].Param==p)",20,0,'nil'),
    'create_shared_missing_table': (BASE + "local t=Isaac.GetCallbacks('created',true);assert(t==Isaac.GetCallbacks('created'));assert(type(getmetatable(t).__matchParams)=='function')",20,0,'nil'),
    'numeric_shared_table': (BASE + "m:AddCallback(20,function() end);assert(Isaac.GetCallbacks(20)==Isaac.GetCallbacks(20))",20,0,'nil'),
    'named_custom_matcher': (BASE + "m:AddCallback('named',function() _order=_order..'A' end,8);setmetatable(Isaac.GetCallbacks('named'),{__matchParams=function(sent,declared) assert(sent==7 and declared==8);return true end});Isaac.RunCallbackWithParam('named',7)",20,0,'nil'),
    'numeric_run_self_return': (BASE + "m:AddCallback(20,function(self,value) assert(self==m and value==42);_order=_order..'A';return 'result' end);assert(Isaac.RunCallback(20,42)=='result');_order=''",21,0,'nil'),
    'numeric_live_entry_mutation': (BASE.replace('_mode=0','_mode=2') + "m:AddCallback(20,function() _order=_order..'A' end);Isaac.GetCallbacks(20)[1].Function=function() _order=_order..'Z' end",20,2,'nil'),
    'remove_named': (BASE + "local fn=function() _order=_order..'A' end;m:AddCallback('named',fn);m:RemoveCallback('named',fn);Isaac.RunCallback('named')",20,0,'nil'),
    'remove_function_across_mods': (BASE + "local other=RegisterMod('other',1);local fn=function() _order=_order..'A' end;m:AddCallback(20,fn);other:AddCallback(20,fn);m:RemoveCallback(20,fn)",20,0,'nil'),
    'native_append_during_dispatch': (BASE.replace('_mode=0','_mode=2') + "local added=false;m:AddCallback(20,function() _order=_order..'A';if not added then added=true;m:AddCallback(20,function() _order=_order..'B' end) end end)",20,2,'nil'),
    'named_error_nesting_restored': (BASE + "m:AddCallback('named',function() error('authority-error') end);for i=1,32 do local ok,err=pcall(Isaac.RunCallback,'named');assert(not ok and err:find('authority-error',1,true)) end",20,0,'nil'),
    'builtin_state_contract': (BASE + """
assert(type(Isaac.GetBuiltInCallbackState(0))=='boolean')
assert(not Isaac.GetBuiltInCallbackState(0))
assert(select('#',Isaac.SetBuiltInCallbackState('0',0))==0)
assert(Isaac.GetBuiltInCallbackState(4294967296))
Isaac.SetBuiltInCallbackState(0);assert(not Isaac.GetBuiltInCallbackState(0))
Isaac.SetBuiltInCallbackState(73,{});assert(Isaac.GetBuiltInCallbackState(73))
Isaac.SetBuiltInCallbackState(74,true);assert(not Isaac.GetBuiltInCallbackState(74))
assert(not Isaac.GetBuiltInCallbackState(-1))
for _,bad in ipairs({false,{},1.5}) do assert(not pcall(Isaac.GetBuiltInCallbackState,bad)) end
local fn=function() end;m:AddCallback(20,fn);assert(Isaac.GetBuiltInCallbackState(20))
m:RemoveCallback(20,fn);assert(not Isaac.GetBuiltInCallbackState(20))
""",21,0,'nil'),
    'direct_table_disabled_native': (BASE.replace('_mode=0','_mode=2') + "local t=Isaac.GetCallbacks(20,true);t[1]={Mod=m,Function=function() _order=_order..'A' end};assert(not Isaac.GetBuiltInCallbackState(20));Isaac.RunCallback(20);assert(_order=='A');_order=''",20,2,'nil'),
    'direct_table_enabled_native': (BASE.replace('_mode=0','_mode=2') + "Isaac.GetCallbacks(20,true)[1]={Mod=m,Function=function() _order=_order..'A' end};Isaac.SetBuiltInCallbackState(20,true)",20,2,'nil'),
    'native_nil_hole': (BASE.replace('_mode=0','_mode=2') + "m:AddCallback(20,function() _order=_order..'A' end);m:AddCallback(20,function() _order=_order..'B' end);m:AddCallback(20,function() _order=_order..'C' end);Isaac.GetCallbacks(20)[2]=nil",20,2,'nil'),
    'native_entry_metatable': (BASE.replace('_mode=0','_mode=2') + "m:AddCallback(20,function() end);Isaac.GetCallbacks(20)[1]=setmetatable({},{__index=function(_,key) if key=='Mod' then return m elseif key=='Function' then return function() _order=_order..'M' end end end})",20,2,'nil'),
    'native_matcher_error': (BASE.replace('_mode=0','_mode=2') + "m:AddCallback(20,function() _order=_order..'A' end);setmetatable(Isaac.GetCallbacks(20),{__matchParams=function() error('matcher-error') end})",20,2,'nil'),
    'native_remove_during_dispatch': (BASE.replace('_mode=0','_mode=2') + "local first;first=function() _order=_order..'A';m:RemoveCallback(20,first) end;m:AddCallback(20,first);m:AddCallback(20,function() _order=_order..'B' end);m:AddCallback(20,function() _order=_order..'C' end)",20,2,'nil'),
    'greater_than_diagnostic_capacity': (BASE.replace('_mode=0','_mode=2') + "for i=1,300 do m:AddCallback(20,function() _order=_order..'A' end) end;assert(#Isaac.GetCallbacks(20)==300)",20,2,'nil'),
    'manual_integer_callback_preserves_raw_return': (BASE + "m:AddCallback(62,function() return 'raw-result' end);assert(Isaac.RunCallback(62)=='raw-result');m:AddCallback('named-raw',function() return false end);assert(Isaac.RunCallback('named-raw')==false)",21,0,'nil'),
    'manual_hundred_arguments': (BASE + "local args={};for i=1,100 do args[i]=i end;m:AddCallback('hundred',function(self,...) assert(self==m and select('#',...)==100);for i=1,100 do assert(select(i,...)==i) end;return 'hundred-ok' end);assert(Isaac.RunCallback('hundred',table.unpack(args))=='hundred-ok')",21,0,'nil'),
    'public_isaac_callbacks': (BASE + "local fn=function(self) assert(self==m);_order=_order..'L' end;Isaac.AddCallback(m,'public',fn);Isaac.AddPriorityCallback(m,'public',-0.5,function() _order=_order..'E' end);Isaac.RunCallback('public');assert(_order=='EL');Isaac.RemoveCallback(m,'public',fn);_order='';Isaac.RunCallback('public');assert(_order=='E');_order=''",21,0,'nil'),
}


class LuaCallbackAuthorityTests(pc.PcBootstrapCallbackParityTests):
    pass


for name, (source, callback_id, mode, sent) in CASES.items():
    def test(self, name=name, source=source, callback_id=callback_id, mode=mode, sent=sent):
        self.compare_script(name, source, callback_id, mode, sent)
    setattr(LuaCallbackAuthorityTests, 'test_authority_' + name, test)

if __name__ == '__main__':
    unittest.main()
