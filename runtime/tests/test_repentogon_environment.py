"""Exercise batch composition and native callback state in a real Lua VM."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_support

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'runtime/source'

DRIVER = r'''
#include "interfaces/lua/repentogon_environment.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "interfaces/lua/callback_table_api.hpp"
#include "application/callback/extended_callback_runtime.hpp"
#include "application/callback/callback_dispatcher.hpp"
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
#include <cassert>
#include <cstdio>
#include <cstring>
using namespace isaac::runtime;
static int initialized{}, released{};
static bool ready=true;
static int Answer(lua_State* s) {lua_pushinteger(s,42);return 1;}
static int Base(lua_State* s) {lua_pushinteger(s,7);return 1;}
static int Initialize(lua_State* s) {++initialized;lua_pushboolean(s,1);lua_setglobal(s,"batchReady");return 0;}
static int Fail(lua_State* s) {++initialized;return luaL_error(s,"batch failed");}
static int OverwriteBase(lua_State* s) {
    lua_getglobal(s,"Isaac");lua_pushcfunction(s,Base);lua_setfield(s,-2,"Base");lua_pop(s,1);return 0;
}
static void Reset() noexcept {++released;}
static bool Ready() noexcept {return ready;}
static const RepentogonApiBinding apis[] = {
    {{0x0E020001,ApiDomain::Isaac,"Isaac","BatchAnswer",{},0,ThreadAffinity::Any,ApiMaturity::Experimental},Answer},
};
static const RepentogonEnumBinding enums[]={{"BatchEnums","VALUE",17}};
static const RepentogonCallbackBinding callbacks[]={{1415,"MC_BATCH_LAST"},{1030,"MC_BATCH_FIRST"}};
static const RepentogonBatch batches[]={{"example",apis,1,enums,1,callbacks,2,Initialize,Reset,Ready}};
static RepentogonCatalog catalog{batches,1,"1.0.0"};
static bool requested;
static const RepentogonCatalog* selected;
static int Invoke(lua_State* s) {
    const int count=lua_gettop(s);
    lua_getfield(s,2,"Function");lua_getfield(s,2,"Mod");
    for(int i=3;i<=count;++i)lua_pushvalue(s,i);
    lua_call(s,count-1,1);return 1;
}
static void Run(lua_State* s,const char* script) {
    if(luaL_dostring(s,script)!=LUA_OK){std::fprintf(stderr,"%s\n",lua_tostring(s,-1));assert(false);}
}
static int Prepare(lua_State* s) {
    BeginRepentogonEnvironment(s,requested,*selected);
    lua_newtable(s);lua_pushcfunction(s,Base);lua_setfield(s,-2,"Base");
    static_cast<void>(AttachOwnerMethods(s,"Isaac",nullptr,0));
    // Families may compose more than one registration table for the same owner.
    static_cast<void>(AttachOwnerMethods(s,"Isaac",nullptr,0));
    lua_pushcfunction(s,GetBuiltInCallbackState);lua_setfield(s,-2,"GetBuiltInCallbackState");
    lua_pushcfunction(s,SetBuiltInCallbackState);lua_setfield(s,-2,"SetBuiltInCallbackState");
    lua_setglobal(s,"Isaac");
    Run(s,"ModCallbacks={MC_PRE_MOD_UNLOAD=73};CallbackPriority={DEFAULT=0}");
    RegisterCallbackBootstrap(s,Invoke);
    CompleteRepentogonEnvironment(s);
    return 0;
}
static lua_State* Start(bool enabled,const RepentogonCatalog& c,bool success=true) {
    lua_State* s=luaL_newstate();
    luaL_requiref(s,"_G",luaopen_base,1);lua_pop(s,1);
    luaL_requiref(s,"table",luaopen_table,1);lua_pop(s,1);
    luaL_requiref(s,"string",luaopen_string,1);lua_pop(s,1);
    Run(s,"debug={getinfo=function()return {name='test'}end}");
    requested=enabled;selected=&c;
    lua_pushcfunction(s,Prepare);
    const bool ok=lua_pcall(s,0,0,0)==LUA_OK;
    if(ok!=success){std::fprintf(stderr,"prepare: %s\n",lua_tostring(s,-1));assert(false);}
    return s;
}
static void Close(lua_State* s) {
    SuspendRepentogonEnvironment(s);
    assert(!RepentogonEnvironmentActive()&&!ExtendedCallbackEnabled(1030));
    lua_close(s);EndRepentogonEnvironment(s);
    assert(ExtendedCallbackCount()==0);
}
int main() {
    auto* s=Start(false,catalog);
    Run(s,"assert(REPENTOGON==nil and Isaac.BatchAnswer==nil and BatchEnums==nil);assert(Isaac.Base()==7)");
    assert(initialized==0);Close(s);assert(released==0);
    s=Start(true,catalog);
    Run(s,R"lua(
assert(REPENTOGON.Name=='REPENTOGON' and REPENTOGON.Version=='1.0.0')
assert(REPENTOGON.MeetsVersion('1.0.0') and not REPENTOGON.MeetsVersion('1.0.1'))
assert(Isaac.Base()==7 and Isaac.BatchAnswer()==42 and BatchEnums.VALUE==17 and batchReady)
assert(ModCallbacks.MC_BATCH_FIRST==1030 and ModCallbacks.MC_BATCH_LAST==1415)
assert(not Isaac.GetBuiltInCallbackState(1030))
local mod={};local order=''
local first=function()order=order..'A';return false end
Isaac.AddPriorityCallback(mod,1030,1,function()order=order..'B'end,9)
Isaac.AddPriorityCallback(mod,1030,-1,first,9)
assert(Isaac.GetBuiltInCallbackState(1030))
assert(Isaac.RunCallbackWithParam(1030,9)==false and order=='A')
Isaac.RemoveCallback(mod,1030,first);Isaac.RunCallbackWithParam(1030,9);assert(order=='AB')
Isaac.SetBuiltInCallbackState(1415,true);assert(Isaac.GetBuiltInCallbackState(1415))
Isaac.SetBuiltInCallbackState(999999999,true);assert(not Isaac.GetBuiltInCallbackState(999999999))
)lua");
    assert(ExtendedCallbackCount()==2&&ExtendedCallbackAt(0)==1030&&ExtendedCallbackAt(1)==1415);
    assert(ExtendedCallbackRegistrationCount(1030)==2);
    // Exercise the same dispatch recorder used by production native events.
    CallbackRegistry registry;
    struct Invoker final : ICallbackInvoker {
        Status Invoke(const CallbackDescriptor&) noexcept override {return Status::Ok();}
        Status InvokeCollecting(const CallbackDescriptor&,CallbackReturn*) noexcept override {return Status::Ok();}
    } invoker;
    CallbackDispatcher dispatcher{registry,invoker};
    static_cast<void>(dispatcher.Dispatch(1030,ThreadAffinity::Any));
    static_cast<void>(dispatcher.Dispatch(1415,ThreadAffinity::Any));
    assert(ExtendedCallbackDispatchCount(1030)==1&&ExtendedCallbackDispatchCount(1415)==1);
    ResetCallbackDispatchCounters();assert(ExtendedCallbackDispatchCount(1030)==0);
    Close(s);assert(initialized==1&&released==1);
    s=Start(false,catalog);Run(s,"assert(REPENTOGON==nil and Isaac.BatchAnswer==nil)");Close(s);
    ready=false;s=Start(true,catalog,false);Close(s);ready=true;assert(initialized==1);
    auto bad=batches[0];bad.initialize=Fail;
    RepentogonCatalog failing{&bad,1,"1.0.0"};s=Start(true,failing,false);
    Run(s,"assert(REPENTOGON==nil)");Close(s);assert(initialized==2&&released==2);
    auto missingApi=apis[0];missingApi.descriptor.owner="UnregisteredOwner";
    bad=batches[0];bad.apis=&missingApi;bad.initialize=nullptr;
    RepentogonCatalog missing{&bad,1,"1.0.0"};s=Start(true,missing,false);Close(s);
    RepentogonBatch duplicates[]={batches[0],batches[0]};
    RepentogonCatalog duplicate{duplicates,2,"1.0.0"};s=Start(true,duplicate,false);Close(s);
    auto otherApi=apis[0];otherApi.descriptor.id=0x0E020002;otherApi.descriptor.name="BatchOther";
    const RepentogonCallbackBinding distant[]={{1000000000,"MC_DISTANT"}};
    RepentogonBatch more[]={batches[0],{"second",&otherApi,1,nullptr,0,distant,1}};
    RepentogonCatalog combined{more,2,"1.0.0"};s=Start(true,combined);
    Run(s,"assert(Isaac.BatchAnswer()==42 and Isaac.BatchOther()==42);Isaac.SetBuiltInCallbackState(1000000000,true);assert(Isaac.GetBuiltInCallbackState(1000000000))");
    assert(ExtendedCallbackCount()==3);Close(s);
    auto overrideApi=apis[0];overrideApi.descriptor.name="Base";overrideApi.replaceExisting=true;
    bad=batches[0];bad.apis=&overrideApi;bad.initialize=OverwriteBase;
    RepentogonCatalog overriding{&bad,1,"1.0.0"};s=Start(true,overriding);
    Run(s,"assert(Isaac.Base()==42)");Close(s);
    const FieldApiRow field{0x0E020003,0,0,FieldKind::U32,FieldMissing::Zero,FieldReceipt::Level,0xFF};
    const EngineMethodRow method{0x0E020004,0,0,FieldReceipt::Room,EngineCallShape::Int0,0,0xFF};
    const RepentogonApiBinding rows[]={
        {{0x0E020003,ApiDomain::Isaac,"Isaac","BatchField",{},0,ThreadAffinity::Any,ApiMaturity::Experimental},nullptr,&field},
        {{0x0E020004,ApiDomain::Isaac,"Isaac","BatchMethod",{},0,ThreadAffinity::Any,ApiMaturity::Experimental},nullptr,nullptr,&method},
    };
    RepentogonBatch rowBatch{"rows",rows,2};RepentogonCatalog rowCatalog{&rowBatch,1,nullptr};
    s=Start(true,rowCatalog);
    Run(s,R"lua(
assert(REPENTOGON==nil)
local ok,e=pcall(Isaac.BatchField);assert(not ok and e:find('Isaac:BatchField',1,true))
ok,e=pcall(Isaac.BatchMethod,{},1,2);assert(not ok and e:find('Isaac:BatchMethod',1,true))
)lua");
    Close(s);
    s=Start(true,DefaultRepentogonCatalog());
    Run(s,"assert(REPENTOGON==nil and Isaac.BatchAnswer==nil)");assert(!RepentogonEnvironmentActive());Close(s);
}
'''

STARTUP_DRIVER = r'''
#include "lua_runtime.hpp"
#include "ports/save_file_port.hpp"
#include <cassert>
#include <cstring>
#include <string>
using namespace isaac::runtime;
struct Files final : ISaveFilePort {
    std::string value="isaac-repentogon 1\nenabled 1\n";
    Status Read(std::string_view,char* out,std::size_t cap,std::size_t* size) noexcept override {
        *size=value.size();assert(cap>=value.size());std::memcpy(out,value.data(),value.size());return Status::Ok();
    }
    Status Write(std::string_view,std::string_view bytes) noexcept override {value=bytes;return Status::Ok();}
    Status Remove(std::string_view) noexcept override {return Status{StatusCode::Unsupported};}
    Status Exists(const char*,bool*) noexcept override {return Status{StatusCode::Unsupported};}
};
static void Run(const char* text) {
    assert(LuaRuntime::InitializeFromBuffer(text,std::strlen(text),"@switch.lua")==LuaRuntime::LuaInitResult::Success);
}
int main() {
    Files files;SetSessionSaveFilePort(&files);LuaRuntime::ObserveGameThread();
    Run(R"lua(
local s=RuntimeMods.GetRepentogonState()
assert(s.Requested and s.StartupEnabled and not s.Active and not s.NeedsRestart)
assert(REPENTOGON==nil)
assert(RuntimeMods.SetRepentogonEnabled(false))
assert(RuntimeMods.GetRepentogonState().NeedsRestart)
local m=RegisterMod('ordinary',1);m:AddCallback(1,function()end)
)lua");
    assert(LuaRuntime::ShutdownForModReload());
    Run(R"lua(
local s=RuntimeMods.GetRepentogonState()
assert(not s.Requested and s.StartupEnabled and s.NeedsRestart and not s.Active)
assert(REPENTOGON==nil)
assert(not pcall(RuntimeMods.SetRepentogonEnabled,1))
local m=RegisterMod('ordinary again',1);m:AddCallback(1,function()end)
)lua");
    assert(LuaRuntime::ShutdownForModReload());SetSessionSaveFilePort(nullptr);
}
'''


class RepentogonEnvironmentTests(unittest.TestCase):
    def test_batches_switch_lifecycle_and_sparse_native_callbacks(self):
        with tempfile.TemporaryDirectory(prefix='repentogon-environment-') as tmp:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(tmp), harness_source=DRIVER)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_real_runtime_startup_and_lua_reload_preserve_switch_snapshot(self):
        with tempfile.TemporaryDirectory(prefix='repentogon-startup-') as tmp:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(tmp), harness_source=STARTUP_DRIVER)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
