"""Room water setters write the verified native fields and reject lost receivers."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX

SOURCE = Path(__file__).resolve().parents[1] / 'source'
DRIVER = PREFIX + r'''
#include "game_observer.hpp"
#include "runtime_constants.hpp"
#include <vector>
static std::vector<unsigned char> moduleBytes,room;
static bool available=true;
GameRoomObservation ReadCurrentGameRoom(std::uintptr_t,void** out){
 *out=available?room.data():nullptr;
 return available?GameRoomObservation::Success:GameRoomObservation::GameUnreadable;
}
static int Water(lua_State* state){
 float value{};std::memcpy(&value,room.data()+0x7914,sizeof(value));
 lua_pushnumber(state,value);return 1;
}
static int Expire(lua_State*){available=false;return 0;}
static void Extensions(lua_State* state) noexcept{
 lua_pushcfunction(state,Water);lua_setglobal(state,"_water");
 lua_pushcfunction(state,Expire);lua_setglobal(state,"_expire");
}
int main(){
 moduleBytes.resize(kGameManagerGlobalSlotOffset+sizeof(std::uintptr_t));
 room.resize(0x8200);
 constexpr unsigned char guard[]={0x88,0x22,0x8f,0x52,0x00,0x68,0x68,0xbc,0x08,0x20,0x20,0x1e,0xe0,0xd7,0x9f,0x1a};
 std::memcpy(moduleBytes.data()+0x487fa0,guard,sizeof(guard));
 constexpr unsigned char currentGuard[]={0x08,0x8f,0x8f,0x52,0x14,0x00,0x08,0x8b,0xf3,0x03,0x00,0xaa,0xe0,0x03,0x14,0xaa};
 std::memcpy(moduleBytes.data()+0x4714b4,currentGuard,sizeof(currentGuard));
 const float unrelated=17;std::memcpy(room.data()+0x7894,&unrelated,sizeof(unrelated));
 LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(moduleBytes.data()));
 Files files(true);SetSessionSaveFilePort(&files);LuaRuntime::ObserveGameThread();
 const repentogon::NativePort port{Ready,Ready};repentogon::SetNativePort(&port);
 LuaRuntime::SetRuntimeExtensionInstaller(Extensions);
 const char* script=R"lua(
local r=Game():GetRoom()
r:SetWaterAmount(0.5);assert(_water()==0.5)
r:SetWaterAmount(-0.25);assert(_water()==-0.25) -- PC setter does not clamp.
r:SetWaterCurrent(Vector(3,-4))
local v=r:GetWaterCurrent();assert(v.X==3 and v.Y==-4)
assert(not pcall(function()r:SetWaterAmount('not-a-number')end));assert(_water()==-0.25)
assert(not pcall(function()r:SetWaterCurrent({X=8,Y=9})end))
v=r:GetWaterCurrent();assert(v.X==3 and v.Y==-4)
_expire()
assert(not pcall(function()r:SetWaterAmount(1)end))
assert(not pcall(function()r:SetWaterCurrent(Vector(1,2))end))
)lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@room-water.lua")!=LuaRuntime::LuaInitResult::Success){
  char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
  std::fprintf(stderr,"%s\n",error);return 1;
 }
 float value{};std::memcpy(&value,room.data()+0x7894,sizeof(value));assert(value==unrelated);
 assert(LuaRuntime::ShutdownForModReload());LuaRuntime::SetRuntimeExtensionInstaller(nullptr);
 repentogon::SetNativePort(nullptr);SetSessionSaveFilePort(nullptr);
}
'''


class RepentogonWaterTests(unittest.TestCase):
    def test_native_water_fields_invalid_arguments_and_lost_room(self):
        with tempfile.TemporaryDirectory(prefix='repentogon-water-') as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=DRIVER)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
