"""真实 Lua 5.3.3：完整模组关闭、错误保留、重入拒绝及同进程新 VM。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from . import test_support

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'runtime/source'
BRIDGE = r'''
namespace LuaRuntime {
// 红检的弱默认定义在测试驱动中；生产实现必须覆盖它。
bool ShutdownForModReload() noexcept;

extern "C" bool ReloadStateAbsent() { return g_LuaState == nullptr && !IsReady(); }
extern "C" bool ReloadGenerationReset() {
 return !g_LuaState && g_CallbackRegistry.Count()==0 && !g_ModRegistered &&
  g_ModRegisteredCount.load()==0 && g_NextModOwnerIndex.load()==2 &&
  g_RequireCacheRef==LUA_NOREF && g_ModObjectRef==LUA_NOREF &&
  !g_RequireAvailable && g_Stage13RequireDepth==0 && !g_LoadingModRoot[0] &&
  g_PendingGameStarted.load()==0 && g_FrameEventState.seenPlayerCount==0 &&
  g_CurrentCallbackManager.load()==0 && g_ActiveCallbackBatch==nullptr;
}
int ReloadRequest(lua_State* state) {lua_pushboolean(state,ShutdownForModReload());return 1;}
int ReloadEntityData(lua_State* state) {return isaac::runtime::PushEntityLifetimeData(state,0x1234500);}
int ReloadCreate(lua_State* state) {lua_pushboolean(state,EnsureRuntimeWithMenu()==LuaInitResult::Success);return 1;}
extern "C" void ReloadInstall(lua_CFunction event) {
 lua_pushcfunction(g_LuaState,event);lua_setglobal(g_LuaState,"record");
 lua_pushcfunction(g_LuaState,ReloadRequest);lua_setglobal(g_LuaState,"requestClose");
 lua_pushcfunction(g_LuaState,ReloadEntityData);lua_setglobal(g_LuaState,"dataForEntity");
 lua_pushcfunction(g_LuaState,ReloadCreate);lua_setglobal(g_LuaState,"requestCreate");
}
extern "C" bool ReloadDispatch() {
 LuaCallbackInvoker invoker{0,false,false};
 isaac::runtime::CallbackDispatcher dispatcher{g_CallbackRegistry,invoker};
 const auto result=dispatcher.Dispatch(1,isaac::runtime::ThreadAffinity::Any);
 return result.failed==0;
}
extern "C" void ReloadSeedTransientState() {
 g_PendingGameStarted.store(2);g_FrameEventState.seenPlayerCount=3;
}
}
'''
DRIVER = r'''
#include "lua_runtime.hpp"
#include "interfaces/lua/callback_table_api.hpp"
#include "interfaces/lua/font_api.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <thread>
extern "C" {
#include <lua.h>
#include <lauxlib.h>
}
namespace LuaRuntime { __attribute__((weak)) bool ShutdownForModReload() noexcept {return false;} }
extern "C" bool ReloadStateAbsent();
extern "C" bool ReloadGenerationReset();
extern "C" void ReloadInstall(lua_CFunction);
extern "C" bool ReloadDispatch();
extern "C" void ReloadSeedTransientState();
std::string events;
unsigned reads{}, fontDestroyed{},spriteDestroyed{};
int Event(lua_State* state){events+=luaL_checkstring(state,1);return 0;}
void Ctor(void*){}
void FontDestroy(void*){++fontDestroyed;}
void SpriteDestroy(void*){++spriteDestroyed;}
namespace GameFileReader {
TextReadResult ReadTextFile(const Bindings&,const char* path,u8* out,std::size_t cap,std::size_t* n) {
 if(std::strcmp(path,"rom:/isaac_mods/mods/A/value.lua"))return TextReadResult::OpenFailed;
 ++reads;const std::string value="return {generation="+std::to_string(reads)+"}";
 *n=value.size();if(*n>cap)return TextReadResult::LengthOutOfRange;
 std::memcpy(out,value.data(),*n);return TextReadResult::Success;
}
}
void Eval(const char* source) {
 const auto result=LuaRuntime::InitializeFromBuffer(source,std::strlen(source),"@reload-check.lua");
 if(result!=LuaRuntime::LuaInitResult::Success){char error[256]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));std::fprintf(stderr,"Lua error: %s\n",error);}
 assert(result==LuaRuntime::LuaInitResult::Success);
}
void Fresh() {
 assert(LuaRuntime::EnsureRuntimeWithMenu()==LuaRuntime::LuaInitResult::Success);
 ReloadInstall(Event);
}
void Close() {
 assert(LuaRuntime::ShutdownForModReload());assert(ReloadGenerationReset());
 assert(!isaac::runtime::BuiltinCallbackEnabled(1));assert(LuaRuntime::RegisteredCallbackKindMaskLow()==0&&LuaRuntime::RegisteredCallbackKindMaskHigh()==0&&LuaRuntime::DispatchableCallbackRegistrationCount()==0&&LuaRuntime::UnhookedCallbackRegistrationCount()==0);
}
int main(int argc,char** argv) {
 assert(argc==2);const int mode=std::stoi(argv[1]);
 if(mode==5){Fresh();assert(!LuaRuntime::ShutdownForModReload());assert(LuaRuntime::IsReady());LuaRuntime::ObserveGameThread();Close();return 0;}
 LuaRuntime::ObserveGameThread();assert(LuaRuntime::ShutdownForModReload());Fresh();
 if(mode==0){
  for(unsigned i=1;i<=3;++i){
   const char* entry="assert(oldGlobal==nil and package.loaded.value==nil);assert(dataForEntity().old==nil);dataForEntity().old=true;oldGlobal={};local v=require('value');assert(require('value')==v);generation=v.generation;local a=RegisterMod('A',1);a:AddCallback(1,function()record('u')end)";
   assert(LuaRuntime::InitializeManifestMod(entry,std::strlen(entry),"@rom:/isaac_mods/mods/A/main.lua","rom:/isaac_mods/mods/A",{})==LuaRuntime::LuaInitResult::Success);
   double value{};assert(LuaRuntime::ReadLuaGlobalNumber("generation",&value)&&value==i);
   assert(LuaRuntime::RegisteredCallbackCount(1)==1);assert(ReloadDispatch());
   ReloadSeedTransientState();Close();assert(LuaRuntime::ShutdownForModReload());Fresh();
  }
  assert(events=="uuu"&&reads==3);Close();
 }else if(mode==1){
  Eval("a=RegisterMod('A',1);b=RegisterMod('B',1);a:AddCallback(1,function()end);b:AddCallback(1,function()end);b:AddCallback(73,function(_,m) if m==a then assert(#Isaac.GetCallbacks(1)==2);record('a') else assert(m==b and #Isaac.GetCallbacks(1)==1);record('b') end end);held=setmetatable({},{__gc=function()assert(not requestClose());assert(not requestCreate());record('g')end})");
  Close();assert(events=="abg");
 }else if(mode==2){
  Eval("a=RegisterMod('A',1);a:AddCallback(1,function()record('u')end);a:AddCallback(73,function()record('e');if not retried then retried=true;error('unload-preserved')end end);held=setmetatable({},{__gc=function()assert(not requestClose());assert(not requestCreate());record('g')end})");
  assert(!LuaRuntime::ShutdownForModReload());assert(LuaRuntime::IsReady());assert(events=="e");
  char error[256]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));assert(std::strstr(error,"unload-preserved"));
  assert(LuaRuntime::TakeCallbackError());assert(ReloadDispatch());assert(events=="eu");
  Close();assert(events=="eueg");Fresh();Close();
 }else if(mode==3){
  Eval("assert(not requestClose());a=RegisterMod('A',1);a:AddCallback(1,function()assert(not requestClose());record('u')end);a:AddCallback(73,function()assert(not requestClose());record('e')end)");
  assert(ReloadDispatch());assert(events=="u");assert(LuaRuntime::IsReady());Close();assert(events=="ue");
 }else if(mode==4){
  LuaRuntime::LuaFontBindings font{};font.ctor=Ctor;font.destructor_=FontDestroy;LuaRuntime::SetFontBindings(font);
  LuaRuntime::LuaSpriteBindings sprite{};sprite.ctor=Ctor;sprite.destructor_=SpriteDestroy;LuaRuntime::SetSpriteBindings(sprite);
  Eval("f=Font();s=Sprite();held=setmetatable({},{__gc=function()assert(not requestClose());assert(not requestCreate());assert(not pcall(Font));assert(not pcall(Sprite));record('g')end})");
  Close();assert(fontDestroyed==1&&spriteDestroyed==1&&events=="g");
  // 入口绑定在关闭后仍可用于新一代正常构造/析构。
  Fresh();Eval("f=Font();s=Sprite()");Close();assert(fontDestroyed==2&&spriteDestroyed==2);
 }else if(mode==6){
  Eval("a=RegisterMod('A',1);a:AddCallback(1,function()end)");
  bool accepted=true;std::thread worker([&]{accepted=LuaRuntime::ShutdownForModReload();});worker.join();
  assert(!accepted&&LuaRuntime::IsReady());Close();
 }else if(mode==7){
  Eval("a=RegisterMod('A',1);a:AddCallback(1,function()end)");Close();Fresh();
  Eval("assert(#Isaac.GetCallbacks(1)==0);assert(a==nil)");Close();
 }else return 99;
 assert(ReloadStateAbsent());return 0;
}
'''


class PressurePinCloseTests(unittest.TestCase):
    def test_close_finalizer_restores_only_live_unchanged_borrow(self):
        import re
        from . import test_api700_grid as grid
        from . import test_lua_entity_query as fixture
        extra = r'''extern "C" void ReloadAdoptState(lua_State*);
static const char originalAnimation[]="OriginalGreed";
static const char writerAnimation[]="NativeGreed";
static bool finalizerRejected{};
static int FinalizerResult(lua_State* L){finalizerRejected=!lua_toboolean(L,1);return 0;}
'''
        main = grid.MAIN.replace('int main(){', extra + '\nint main(int argc,char**argv){assert(argc==2);const int mode=std::stoi(argv[1]);')
        replacement = r'''WriteWord(plateGrid,0x2f8,reinterpret_cast<std::uintptr_t>(originalAnimation));
assert(luaL_dostring(L,"plate.NextGreedAnimation=string.rep('ExistingBorrow',20)")==LUA_OK);
if(mode==1)WriteWord(plateGrid,0x2f8,reinterpret_cast<std::uintptr_t>(writerAnimation));
if(mode==2)WriteWord(g_RoomBytes,8,0xdeadbeef);
if(mode==3){
 lua_pushcfunction(L,FinalizerResult);lua_setglobal(L,"closeResult");
 assert(luaL_dostring(L,"late=setmetatable({},{__gc=function() closeResult(pcall(function() plate.NextGreedAnimation=string.rep('LateBorrow',20) end)) end})")==LUA_OK);
 LuaRuntime::ObserveGameThread();ReloadAdoptState(L);assert(LuaRuntime::ShutdownForModReload());
 assert(finalizerRejected);
}else lua_close(L);
std::uintptr_t finalPointer{};std::memcpy(&finalPointer,plateGrid.data()+0x2f8,8);
if(mode==2)assert(finalPointer!=reinterpret_cast<std::uintptr_t>(originalAnimation));
else assert(finalPointer==reinterpret_cast<std::uintptr_t>(mode==1?writerAnimation:originalAnimation));
assert(!HasPressurePlateAnimationPins());assert(ownedDestructors==0);'''
        main = main.replace('lua_close(L);assert(ownedDestructors==0);', replacement)
        prefix = fixture.HARNESS[:fixture.HARNESS.index('int main(')]
        prefix = re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '', prefix, count=1)
        prefix = prefix.replace('GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {\n    return GameRoomObservation::RoomUnreadable;\n}',
                                'void*GridTestRoom();\nGameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {*room=GridTestRoom();return GameRoomObservation::Success;}')
        with tempfile.TemporaryDirectory(prefix='reload-pins-close-') as directory:
            directory = Path(directory)
            copied = directory / 'instrumented_runtime.cpp'
            copied.write_text((SOURCE/'lua_runtime.cpp').read_text() + '\nnamespace LuaRuntime {extern "C" void ReloadAdoptState(lua_State* state){g_LuaState=state;g_Ready.store(true);}}\n')
            sources = tuple(copied if p==SOURCE/'lua_runtime.cpp' else p for p in test_support.layered_lua_runtime_sources(SOURCE))
            with patch.object(test_support, 'layered_lua_runtime_sources', return_value=sources):
                binary = test_support.build_lua_harness(source_root=SOURCE,workdir=directory,
                    harness_source=prefix+'\n#define API700_GRID_LOCAL\n'+main)
            for mode in range(4):
                with self.subTest(mode=mode):
                    result = subprocess.run([str(binary),str(mode)],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)


class LuaRuntimeReloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='isaac-runtime-reload-')
        directory = Path(cls.tmp.name)
        copied = directory / 'instrumented_runtime.cpp'
        copied.write_text((SOURCE / 'lua_runtime.cpp').read_text() + BRIDGE)
        sources = tuple(copied if p == SOURCE / 'lua_runtime.cpp' else p
                        for p in test_support.layered_lua_runtime_sources(SOURCE))
        flags = tuple(f for f in test_support.HARNESS_COMPILE_FLAGS
                      if not f.startswith('-DEXL_DIAGNOSTIC_STAGE='))
        with patch.object(test_support, 'layered_lua_runtime_sources', return_value=sources), \
             patch.object(test_support, 'HARNESS_COMPILE_FLAGS', flags):
            cls.binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=directory, harness_source=DRIVER)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_mode(self, mode):
        result = subprocess.run([str(self.binary), str(mode)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_globals_require_and_callbacks_do_not_cross_vm(self): self.run_mode(0)
    def test_unload_73_precedes_callback_removal_and_close(self): self.run_mode(1)
    def test_unload_error_preserves_vm_and_allows_retry(self): self.run_mode(2)
    def test_lua_callback_and_unload_reentry_are_rejected(self): self.run_mode(3)
    def test_native_userdata_finalizers_and_bindings_survive_reload(self): self.run_mode(4)
    def test_unobserved_game_thread_cannot_close_active_vm(self): self.run_mode(5)
    def test_foreign_thread_cannot_close_active_vm(self): self.run_mode(6)
    def test_all_disabled_rebuilds_empty_callback_runtime(self): self.run_mode(7)


if __name__ == '__main__':
    unittest.main()
