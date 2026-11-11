"""Stage selection uses the actual pre-SetStage boundary and validated pair returns."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_support
from .test_repentogon_callbacks import RUNTIME_DRIVER, SOURCE
from .test_repentogon_in_game import PREFIX

# Different return shapes are supplied as literal callback bodies; each gets a fresh VM.
RETURNS = {
    'normal_lower': ('{1,0}', False, True, 1, 0),
    'normal_alt_lower': ('{1,1}', False, True, 1, 1),
    'normal_alt_upper': ('{14,1}', False, True, 14, 1),
    'greed_lower': ('{1,2}', True, True, 1, 2),
    'normal_above_upper': ('{15,0}', False, False, 0, 0),
    'negative_type': ('{3,-1}', False, False, 0, 0),
    'above_type': ('{3,6}', False, False, 0, 0),
    'valid': ('{14,5}', False, True, 14, 5),
    'greed_valid': ('{7,4}', True, True, 7, 4),
    'greed_range': ('{8,0}', True, False, 0, 0),
    'bad_stage': ('{0,0}', False, False, 0, 0),
    'bad_type': ('{3,3}', False, False, 0, 0),
    'short': ('{3}', False, False, 0, 0),
    'long': ('{3,0,1}', False, False, 0, 0),
    'wrong': ('false', False, False, 0, 0),
    'custom_len_valid': ('setmetatable({4,2,1},{__len=function()return 2 end})', False, True, 4, 2),
    'custom_len_invalid': ('setmetatable({4,2},{__len=function()return 3 end})', False, False, 0, 0),
    'numeric_string': ('{"4","2"}', False, True, 4, 2),
}

class StageSelectTests(unittest.TestCase):
    def test_pair_return_validation(self):
        cases = ''
        checks = ''
        for mode, (value, greed, valid, first, second) in RETURNS.items():
            cases += f'''    if(mode=="{mode}") {{
 script+="m:AddCallback(1104,function(_,stage,kind)assert(stage==2 and kind==0);calls=calls+1;return {value.replace(chr(34), chr(92)+chr(34))} end)";
    }}else\n'''
            checks += f'''        if(mode=="{mode}") {{
 Event event{{}};event.id=1104;event.kind=EventKind::IntegerPair;event.first=2;event.second=0;event.low={'true' if greed else 'false'};
 const auto result=Dispatch(event);Check();assert(Number("calls")==1);
 assert(result.hasIntegerPair=={'true' if valid else 'false'});
 {'assert(result.first=='+str(first)+'&&result.second=='+str(second)+');' if valid else ''}
        }}else\n'''
        driver=RUNTIME_DRIVER.replace('    if(mode=="off"||mode=="none"){', cases+'    if(mode=="off"||mode=="none"){',1)
        driver=driver.replace('        if(mode=="catalog"){',checks+'        if(mode=="catalog"){',1)
        with tempfile.TemporaryDirectory(prefix='repentogon-stage-select-') as folder:
            binary=test_support.build_lua_harness(source_root=SOURCE,workdir=Path(folder),harness_source=driver)
            for mode in RETURNS:
                with self.subTest(mode=mode):
                    result=subprocess.run([str(binary),mode],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)

API_DRIVER = PREFIX + r'''
#include "interfaces/lua/repentogon_world_api.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "runtime_constants.hpp"
#include <vector>
static std::vector<unsigned char> moduleBytes,game;
static std::uintptr_t gamePointer;
static int called;
static constexpr std::uint8_t stageGuard[]={0xfd,0x7b,0xbd,0xa9,0xf6,0x57,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
static void Stage(void* self,std::int32_t stage,std::int32_t type){
 assert(self==game.data()&&stage==3&&type==4);++called;
}
static bool Installed(std::uintptr_t address,const std::uint8_t* bytes,std::size_t n,
 engine_call::ReadableCheck) noexcept {
 return address==reinterpret_cast<std::uintptr_t>(moduleBytes.data())+kLevelSetStageOffset&&
 n==sizeof(stageGuard)&&!std::memcmp(bytes,stageGuard,sizeof(stageGuard));
}
static int DamageGuard(lua_State*){moduleBytes[kLevelSetStageOffset+15]^=1;return 0;}
static int InstallGuard(lua_State*){
 std::memset(moduleBytes.data()+kLevelSetStageOffset,0,16);
 engine_call::SetInstalledEntryVerifier(Installed);return 0;
}
static void Extensions(lua_State* state) noexcept {
 lua_pushcfunction(state,DamageGuard);lua_setglobal(state,"_damageGuard");
 lua_pushcfunction(state,InstallGuard);lua_setglobal(state,"_installGuard");
}
int main(){
 moduleBytes.resize(kGameOwnerGlobalSlotOffset+8);game.resize(0x22000);
 gamePointer=reinterpret_cast<std::uintptr_t>(game.data());
 const auto owner=reinterpret_cast<std::uintptr_t>(&gamePointer);
 std::memcpy(moduleBytes.data()+kGameOwnerGlobalSlotOffset,&owner,8);
 LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(moduleBytes.data()));
 LuaRuntime::SetGameBindings(reinterpret_cast<std::uintptr_t>(moduleBytes.data())+kGameOwnerGlobalSlotOffset,0);
 LuaRuntime::ObserveGameThread();Files files(true);SetSessionSaveFilePort(&files);
 const repentogon::NativePort port{Ready,Ready};repentogon::SetNativePort(&port);
 std::memcpy(moduleBytes.data()+kLevelSetStageOffset,stageGuard,sizeof(stageGuard));
 engine_call::SetInstalledEntryVerifier(nullptr);
 LuaRuntime::SetRuntimeExtensionInstaller(Extensions);
 SetRepentogonLevelSetStageHost(Stage);
 const char* script=R"lua(
local level=Game():GetLevel()
level:SetStage(3,4)
_damageGuard();assert(not pcall(function()level:SetStage(3,4)end))
_installGuard();level:SetStage(3,4)
assert(not pcall(function()level:SetStage({},0)end))
)lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@stage-api.lua")!=LuaRuntime::LuaInitResult::Success){
 char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));std::fprintf(stderr,"%s\n",error);return 1;
 }
 assert(called==2);assert(LuaRuntime::ShutdownForModReload());
 engine_call::SetInstalledEntryVerifier(nullptr);SetRepentogonLevelSetStageHost(nullptr);
 LuaRuntime::SetRuntimeExtensionInstaller(nullptr);repentogon::SetNativePort(nullptr);SetSessionSaveFilePort(nullptr);
}
'''

class StageSelectApiTests(unittest.TestCase):
    def test_set_stage_remains_callable_after_native_entry_hook(self):
        with tempfile.TemporaryDirectory(prefix='repentogon-stage-api-') as folder:
            binary=test_support.build_lua_harness(source_root=SOURCE,workdir=Path(folder),harness_source=API_DRIVER)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
