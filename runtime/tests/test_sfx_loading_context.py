"""SFX preload is allowed on the game thread while author modules initialize."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_support
from .test_repentogon_in_game import PREFIX
SOURCE=Path(__file__).resolve().parents[1]/'source'
DRIVER=PREFIX.replace('static bool Ready()', '[[maybe_unused]] static bool Ready()')+r'''
#include "runtime_constants.hpp"
#include <vector>
#include <thread>
#include <cstdio>
static std::vector<unsigned char> manager(0x40000);
static unsigned calls;
static std::uintptr_t Manager(){return reinterpret_cast<std::uintptr_t>(manager.data());}
static void Preload(void* self,int id){assert(reinterpret_cast<std::uintptr_t>(self)==Manager()+kManagerSoundEffectsOffset);assert(id==23);++calls;}
int main(){
 LuaRuntime::ObserveGameThread();
 LuaRuntime::SetFrameManagerProvider(Manager);
 LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(&Preload)-kSoundEffectsPreloadOffset);
 Files files(false);SetSessionSaveFilePort(&files);
 const char* script="SFXManager():Preload(23)";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@sfx-loading.lua")!=LuaRuntime::LuaInitResult::Success){
  char error[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));std::fprintf(stderr,"%s\n",error);return 1;
 }
 assert(calls==1);
 std::vector<unsigned char> module(kGameManagerGlobalSlotOffset+8);
 std::uintptr_t managerPointer=Manager();const auto slot=reinterpret_cast<std::uintptr_t>(&managerPointer);
 std::memcpy(module.data()+kGameManagerGlobalSlotOffset,&slot,8);
 LuaRuntime::SetFrameManagerProvider(nullptr);
 LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(module.data()));
 std::uintptr_t fallback{};
 assert(LuaRuntime::ResolveSoundEffectsMethodForCall(reinterpret_cast<std::uintptr_t>(&Preload),kSoundEffectsPreloadExpectedBytes.data(),16,&fallback));
 assert(fallback==Manager()+kManagerSoundEffectsOffset);

 bool workerAccepted=true;
 std::thread worker([&]{std::uintptr_t out{};workerAccepted=LuaRuntime::ResolveSoundEffectsMethodForCall(reinterpret_cast<std::uintptr_t>(&Preload),kSoundEffectsPreloadExpectedBytes.data(),16,&out);});worker.join();
 assert(!workerAccepted&&calls==1);
 std::uintptr_t out{};assert(!LuaRuntime::ResolveSoundEffectsMethodForCall(0,kSoundEffectsPreloadExpectedBytes.data(),16,&out));
 managerPointer=0;
 assert(!LuaRuntime::ResolveSoundEffectsMethodForCall(reinterpret_cast<std::uintptr_t>(&Preload),kSoundEffectsPreloadExpectedBytes.data(),16,&out));
 assert(LuaRuntime::ShutdownForModReload());LuaRuntime::SetFrameManagerProvider(nullptr);SetSessionSaveFilePort(nullptr);
}
'''
class SfxLoadingContextTests(unittest.TestCase):
 def test_loading_on_game_thread_and_worker_rejection(self):
  with tempfile.TemporaryDirectory(prefix='sfx-loading-')as tmp:
   binary=test_support.build_lua_harness(source_root=SOURCE,workdir=Path(tmp),harness_source=DRIVER)
   p=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
