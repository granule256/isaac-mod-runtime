"""完整固定PC bootstrap与真实项目派发的行为比较；不以摘录替代最终Lua规则。"""
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from . import test_support

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'runtime/source'
EVIDENCE = ROOT / 'docs/PC完整启动脚本回调契约证据-20261009'
EXPECTED_SHA = {
    'main.lua': 'ae0efa082e0ea8844a6e7a5ab55e4a96a8dc87a8fa046483e590c0677c40cfdf',
    'enums.lua': 'dce1892f51e4e645d66ac8ffb31d217e8c36a32457c1005dd128978141103dc5',
}
# 引擎类仅为完整脚本顶层提供原生入口；回调实现、登记排序和匹配均来自完整原脚本。
PC_STUBS = r"""
local function noop() end
Isaac = setmetatable({}, {__index=function() return noop end})
debug = {getinfo=function() return {name='native-stub'} end}
local function nativeClass()
  local class = setmetatable({__index=function() return noop end}, {__index=function() return noop end})
  return setmetatable({}, {__class=class, __call=function() return setmetatable({}, class) end})
end
for _, name in ipairs({'Vector','Color','KColor','Font','ItemPool','SFXManager','HUD',
 'TemporaryEffects','Room','MusicManager','Game','Level','Sprite','EntityTear','EntityBomb',
 'EntityKnife','EntityLaser','EntityProjectile','EntityFamiliar','EntityNPC','EntityPickup','EntityPlayer',
 'ItemConfig','RoomDescriptor'}) do
  _G[name] = nativeClass()
end
Game_0 = function() return {} end
"""
PC_DRIVER = r''' 
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
struct Bits {std::uint64_t l,h;};
static int BitsIndex(lua_State* s){auto* b=static_cast<Bits*>(luaL_checkudata(s,1,"pc.Bits"));const char* k=luaL_checkstring(s,2);if(!std::strcmp(k,"l"))lua_pushinteger(s,static_cast<lua_Integer>(b->l));else if(!std::strcmp(k,"h"))lua_pushinteger(s,static_cast<lua_Integer>(b->h));else lua_pushnil(s);return 1;}
static void PushBits(lua_State* s,std::uint64_t l,std::uint64_t h){auto* b=static_cast<Bits*>(lua_newuserdata(s,sizeof(Bits)));b->l=l;b->h=h;luaL_setmetatable(s,"pc.Bits");}
static int BitsCtor(lua_State* s){const auto l=luaL_checkinteger(s,2),h=luaL_checkinteger(s,3);PushBits(s,l,h);return 1;}
static int BitsShift(lua_State* s){auto* b=static_cast<Bits*>(luaL_checkudata(s,1,"pc.Bits"));const auto n=luaL_checkinteger(s,2);std::uint64_t l=0,h=0;if(n>=0&&n<64){l=b->l<<n;h=(b->h<<n)|(n?b->l>>(64-n):0);}else if(n>=64&&n<128)h=b->l<<(n-64);PushBits(s,l,h);return 1;}
static int runRef=0;
static std::uint32_t builtin[3]{};
static bool Enabled(std::uint32_t id){return id<=73&&(builtin[id>>5]&(std::uint32_t{1}<<(id&31)))!=0;}
static int GetBuiltin(lua_State* s){lua_pushboolean(s,Enabled(static_cast<std::uint32_t>(luaL_checkinteger(s,1))));return 1;}
static int SetBuiltin(lua_State* s){const bool enabled=lua_toboolean(s,2);const auto id=static_cast<std::uint32_t>(luaL_checkinteger(s,1));if(id<=73){const auto bit=std::uint32_t{1}<<(id&31);if(enabled)builtin[id>>5]|=bit;else builtin[id>>5]&=~bit;}return 0;}
static int CallCaptured(lua_State* s){const int id=static_cast<int>(luaL_checkinteger(s,1));const int mode=static_cast<int>(luaL_checkinteger(s,2));if(!Enabled(static_cast<std::uint32_t>(id))){if(mode==0)return 0;lua_pushnil(s);return 1;}lua_rawgeti(s,LUA_REGISTRYINDEX,runRef);lua_pushinteger(s,id);lua_pushvalue(s,3);lua_call(s,2,mode==0?0:1);if(mode==0)return 0;if(mode==1&&!lua_isnil(s,-1)){const auto value=luaL_checkinteger(s,-1);lua_pop(s,1);lua_pushinteger(s,value);}return 1;}
static bool Run(lua_State* s,const std::string& text,const char* name){if(luaL_loadbuffer(s,text.data(),text.size(),name)||lua_pcall(s,0,0,0)){std::fprintf(stderr,"%s: %s\n",name,lua_tostring(s,-1));return false;}return true;}
static std::string Read(const char* p){std::ifstream in(p,std::ios::binary);return {std::istreambuf_iterator<char>(in),{}};}
int main(int argc,char** argv){
 if(argc!=6)return 90;
 lua_State* s=luaL_newstate();
 luaL_requiref(s,"_G",luaopen_base,1);lua_pop(s,1);luaL_requiref(s,"table",luaopen_table,1);lua_pop(s,1);luaL_requiref(s,"string",luaopen_string,1);lua_pop(s,1);luaL_requiref(s,"math",luaopen_math,1);lua_pop(s,1);
 luaL_newmetatable(s,"pc.Bits");lua_pushcfunction(s,BitsIndex);lua_setfield(s,-2,"__index");lua_pushcfunction(s,BitsShift);lua_setfield(s,-2,"__shl");lua_pop(s,1);
 lua_newtable(s);lua_newtable(s);luaL_getmetatable(s,"pc.Bits");lua_setfield(s,-2,"__class");lua_pushcfunction(s,BitsCtor);lua_setfield(s,-2,"__call");lua_setmetatable(s,-2);lua_setglobal(s,"BitSet128");
 if(!Run(s,Read(argv[1]),"@native_stubs.lua"))return 91;
 // 已核PE getter/setter closure契约模型：checkinteger低32位、truthiness、0..73。
 lua_getglobal(s,"Isaac");lua_pushcfunction(s,GetBuiltin);lua_setfield(s,-2,"GetBuiltInCallbackState");lua_pushcfunction(s,SetBuiltin);lua_setfield(s,-2,"SetBuiltInCallbackState");lua_pop(s,1);
 if(!Run(s,Read(argv[2]),"@pc/enums.lua")||!Run(s,Read(argv[3]),"@pc/main.lua"))return 91;
 lua_getglobal(s,"_RunCallback");runRef=luaL_ref(s,LUA_REGISTRYINDEX);lua_pushnil(s);lua_setglobal(s,"_RunCallback");
 if(!Run(s,"assert(Game_0==nil and debug==nil and loadfile==nil and _RunCallback==nil)","@full_bootstrap_finished"))return 92;
 if(!Run(s,Read(argv[4]),"@callbacks.lua"))return 93;
 const int id=std::stoi(argv[5]);lua_getglobal(s,"_mode");const int mode=static_cast<int>(lua_tointeger(s,-1));lua_pop(s,1);
 lua_pushcfunction(s,CallCaptured);lua_pushinteger(s,id);lua_pushinteger(s,mode);lua_getglobal(s,"_filter");const int failure=lua_pcall(s,3,mode==0?0:1,0)!=LUA_OK;
 int nonNil=0,truthy=0,table=0,hasInt=0;long long integer=0;
 if(!failure&&mode!=0){nonNil=!lua_isnil(s,-1);truthy=lua_toboolean(s,-1);table=lua_istable(s,-1);hasInt=lua_isinteger(s,-1);integer=hasInt?static_cast<long long>(lua_tointeger(s,-1)):0;}
 lua_getglobal(s,"_order");const char* order=lua_tostring(s,-1);
 std::printf("%s|%d|%d|%d|%d|%d|%lld\n",order?order:"",failure,nonNil,truthy,table,hasInt,integer);lua_close(s);return 0;
}
'''
RUNTIME_BRIDGE = r''' 
namespace LuaRuntime {
extern "C" void ProbeBootstrapParity(int id,int mode,std::int64_t filter){
 const int oldTop=lua_gettop(g_LuaState);
 LuaCallbackInvoker invoker{0,false,false};
 isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry,invoker};
 isaac::runtime::CallbackDispatchOutcome outcome{};
 if(mode==0){const auto report=dispatcher.DispatchFiltered(static_cast<isaac::runtime::CallbackId>(id),isaac::runtime::ThreadAffinity::Any,filter);outcome.failed=report.failed;}
 else outcome=dispatcher.DispatchModifying(static_cast<isaac::runtime::CallbackId>(id),isaac::runtime::ThreadAffinity::Any,filter);
 lua_getglobal(g_LuaState,"_order");const char* order=lua_tostring(g_LuaState,-1);
 // PC的保护边界失败时没有结果；项目必须同样丢弃本次结果且停止后续回调。
 const bool ok=outcome.failed==0;
 std::printf("%s|%d|%d|%d|%d|%d|%lld\n",order?order:"",!ok,ok&&outcome.anyNonNil,ok&&outcome.anyTruthy,ok&&outcome.hasTable,ok&&outcome.hasInteger,ok&&outcome.hasInteger?static_cast<long long>(outcome.integer):0);
 if(lua_gettop(g_LuaState)!=oldTop+1)std::fprintf(stderr,"stack leak\n");lua_settop(g_LuaState,oldTop);
}
}
'''
RUNTIME_DRIVER = r''' 
#include "lua_runtime.hpp"
#include "application/callback/callback_registry.hpp"
#include <cstdint>
#include <fstream>
#include <iterator>
#include <string>
extern "C" void ProbeBootstrapParity(int,int,std::int64_t);
int main(int argc,char** argv){if(argc!=5)return 90;std::ifstream in(argv[1],std::ios::binary);std::string script{std::istreambuf_iterator<char>(in),{}};if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@callbacks.lua")!=LuaRuntime::LuaInitResult::Success)return 91;const auto filter=std::string(argv[4])=="nil"?isaac::runtime::CallbackRegistry::kNoCallbackFilter:std::stoll(argv[4]);ProbeBootstrapParity(std::stoi(argv[2]),std::stoi(argv[3]),filter);return 0;}
'''

def scenario(callback_id, mode, values, *, priorities=None, declared=None, sent='nil'):
    priorities = priorities or [0] * len(values)
    declared = declared or ['nil'] * len(values)
    lines = ["_order='';_mode=%d;_filter=%s;local m=RegisterMod('parity',1)" % (mode, sent)]
    for i, (value, priority, param) in enumerate(zip(values, priorities, declared)):
        label = chr(ord('A') + i)
        statement = "error('first-error')" if value == 'error' else 'return ' + value
        lines.append("m:AddPriorityCallback(%d,%s,function() _order=_order..'%s';%s end,%s)" % (callback_id, priority, label, statement, param))
    return '\n'.join(lines)


class PcBootstrapCallbackParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='isaac-full-pc-bootstrap-')
        cls.work = Path(cls.directory.name)
        for name, expected in EXPECTED_SHA.items():
            actual = hashlib.sha256((EVIDENCE / name).read_bytes()).hexdigest()
            if actual != expected:
                raise AssertionError('完整PC原脚本身份不符：' + name)
        cls.stubs = cls.work / 'native_stubs.lua'
        cls.stubs.write_text(PC_STUBS)
        pc = cls.work / 'pc.cpp'
        pc.write_text(PC_DRIVER)
        cls.pc = cls.work / 'pc'
        objects = test_support.lua_harness_objects(SOURCE, cls.work)
        lua = SOURCE / test_support.LUA_SOURCE_RELATIVE
        build = subprocess.run(['c++','-std=c++20','-I',str(lua),str(pc),*[str(p) for p in objects],'-o',str(cls.pc)],capture_output=True,text=True)
        if build.returncode:
            raise AssertionError(build.stdout + build.stderr)
        instrumented = cls.work / 'instrumented_runtime.cpp'
        instrumented.write_text((SOURCE / 'lua_runtime.cpp').read_text() + RUNTIME_BRIDGE)
        sources = tuple(instrumented if p == SOURCE / 'lua_runtime.cpp' else p for p in test_support.layered_lua_runtime_sources(SOURCE))
        with mock.patch.object(test_support, 'layered_lua_runtime_sources', return_value=sources):
            cls.runtime = test_support.build_lua_harness(source_root=SOURCE,workdir=cls.work,harness_source=RUNTIME_DRIVER)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def compare(self, name, callback_id, mode, values, **options):
        self.compare_script(name, scenario(callback_id, mode, values, **options), callback_id,
                            mode, options.get('sent', 'nil'))

    def compare_script(self, name, source, callback_id=20, mode=0, sent='nil'):
        script = self.work / (name + '.lua')
        script.write_text(source)
        pc = subprocess.run([str(self.pc),str(self.stubs),str(EVIDENCE / 'enums.lua'),str(EVIDENCE / 'main.lua'),str(script),str(callback_id)],capture_output=True,text=True)
        self.assertEqual(pc.returncode,0,'PC完整脚本执行失败：' + pc.stdout + pc.stderr)
        actual = subprocess.run([str(self.runtime),str(script),str(callback_id),str(mode),sent],capture_output=True,text=True)
        self.assertEqual(actual.returncode,0,'项目Lua执行失败：' + actual.stdout + actual.stderr)
        print(name + ': PC=' + pc.stdout.strip() + ' project=' + actual.stdout.strip())
        self.assertEqual(actual.stdout,pc.stdout,name + '：完整PC与项目派发不一致')

    def test_nil_continues_and_first_non_nil_stops(self):
        for callback_id in (20,62,63,64,65,69):
            with self.subTest(callback_id=callback_id):
                self.compare('first_integer_' + str(callback_id),callback_id,1,['nil','100','300'])

    def test_table_and_scalar_short_circuit(self):
        for callback_id in (24,71):
            for value in ('{}','false','0'):
                with self.subTest(callback_id=callback_id,value=value):
                    self.compare('table_%d_%s' % (callback_id,value.replace('{}','empty')),callback_id,2,[value,'{}'])

    def test_error_aborts_remaining_callbacks(self):
        for callback_id,mode in ((20,1),(71,2),(1,0),(13,2)):
            with self.subTest(callback_id=callback_id):
                self.compare('error_' + str(callback_id),callback_id,mode,['error','100'])

    def test_priority_is_stable(self):
        self.compare('stable_priority',20,1,['nil'] * 4,priorities=[0,-1,0,-1])

    def test_priority_preserves_complete_pc_number_contract(self):
        for name, priorities in (
            ('fractional', ['0.75', '-0.25', '0.75', '0.125']),
            ('large', ['4294967296', '0', '-4294967297', '2147483648']),
            ('infinite', ['math.huge', '0', '-math.huge', 'math.huge']),
            ('nan', ['0', '(0/0)', '1', '-1']),
        ):
            with self.subTest(name=name):
                self.compare('priority_' + name,20,1,['nil'] * 4,priorities=priorities)

    def test_priority_preserves_integer_precision_and_mixed_lua_comparisons(self):
        cases = (
            ('positive_neighbors', ['9007199254740993', '9007199254740992']),
            ('negative_neighbors', ['-9007199254740992', '-9007199254740993']),
            ('maximum_neighbors', ['math.maxinteger', 'math.maxinteger-1']),
            ('minimum_neighbors', ['math.mininteger+1', 'math.mininteger']),
            ('mixed_positive', ['9007199254740993', '9007199254740992.0', '9007199254740992']),
            ('mixed_negative', ['-9007199254740992.0', '-9007199254740993', '-9007199254740992']),
            ('mixed_nan_limits', ['math.maxinteger', '9223372036854775808.0', '(0/0)', 'math.mininteger', '-9223372036854775808.0']),
        )
        base = "_order='';_mode=0;local m=RegisterMod('number-priority',1);m:AddCallback(1,function() end)\n"
        for name, priorities in cases:
            with self.subTest(name=name, path='numeric'):
                self.compare('exact_priority_' + name,20,1,['nil'] * len(priorities),priorities=priorities)
            source = base + "local original={}\n"
            for index, priority in enumerate(priorities):
                label = chr(65 + index)
                source += "do local p=%s;local fn=function() _order=_order..'%s' end;original[fn]=p;m:AddPriorityCallback('exact',p,fn) end\n" % (priority,label)
            source += "for _,entry in ipairs(Isaac.GetCallbacks('exact')) do local p=original[entry.Function];assert(math.type(entry.Priority)==math.type(p));assert(entry.Priority==p or (p~=p and entry.Priority~=entry.Priority)) end;Isaac.RunCallback('exact')"
            with self.subTest(name=name, path='named'):
                self.compare_script('named_exact_priority_' + name, source)

    def test_nan_order_survives_filtering_and_removal(self):
        self.compare('nan_filtered',20,1,['nil'] * 4,
                     priorities=['0', '1', '(0/0)', '0'],
                     declared=['8','7','7','7'], sent='7')
        source = scenario(20,1,['nil'] * 4,priorities=['0','1','(0/0)','0'])
        source = source.replace("m:AddPriorityCallback(20,0,function() _order=_order..'A';return nil end,nil)",
                                "local first=function() _order=_order..'A' end; m:AddPriorityCallback(20,0,first)")
        self.compare_script('nan_removed', source + '\nm:RemoveCallback(20,first)', 20, 1)

    def test_named_priority_and_strict_number_type_match_pc(self):
        base = "_order='';_mode=0;local m=RegisterMod('named-priority',1);m:AddCallback(1,function() end)\n"
        for name, priorities in (
            ('fractional', ['0.75', '-0.25', '0.75', '0.125']),
            ('large', ['4294967296', '0', '-4294967297', '2147483648']),
            ('infinite', ['math.huge', '0', '-math.huge', 'math.huge']),
            ('nan', ['0', '1', '(0/0)', '0']),
        ):
            source = base
            for index, priority in enumerate(priorities):
                label = chr(65 + index)
                source += "m:AddPriorityCallback('named',%s,function() _order=_order..'%s' end)\n" % (priority,label)
            source += "local callbacks=Isaac.GetCallbacks('named');for _,entry in ipairs(callbacks) do assert(type(entry.Priority)=='number') end;Isaac.RunCallback('named')"
            with self.subTest(name=name):
                self.compare_script('named_priority_' + name, source)
        for callback_id in ('20', "'named'"):
            source = base + "assert(not pcall(function() m:AddPriorityCallback(%s,'0',function() end) end));_order='rejected'" % callback_id
            with self.subTest(callback_id=callback_id):
                self.compare_script('strict_priority_' + callback_id.replace("'",''), source)
        source = base + """
local nested=false
m:AddPriorityCallback('nested',0.75,function(self,value)
 assert(self==m);_order=_order..'A'..value
 if not nested then nested=true;Isaac.RunCallback('nested','inner') end
end)
m:AddPriorityCallback('nested',-0.25,function(self,value) assert(self==m);_order=_order..'B'..value end)
Isaac.RunCallback('nested','outer')
"""
        self.compare_script('named_priority_nested', source)

    def test_nil_and_minus_one_are_wildcards(self):
        for declared,sent in ((['-1','7'],'7'),(['7','9'],'-1'),(['7','9'],'nil'),(['nil','7'],'9')):
            with self.subTest(declared=declared,sent=sent):
                self.compare('wildcard_%s_%s' % ('_'.join(declared),sent),20,1,['nil','nil'],declared=declared,sent=sent)

    def test_notification_discard_does_not_change_short_circuit(self):
        for value in ('false','0','{}'):
            with self.subTest(value=value):
                self.compare('notification_' + value.replace('{}','empty'),1,0,[value,'nil'])

    def test_input_action_uses_same_captured_callback_function(self):
        self.compare('input_first',13,2,['false','true'])

    def test_protected_integer_conversion(self):
        for value in ('1.0',"'42'",'false','1.5'):
            with self.subTest(value=value):
                self.compare('integer_' + value.replace("'",''),64,1,[value,'99'])

if __name__ == '__main__':
    unittest.main()
