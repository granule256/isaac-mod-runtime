"""Pickup state extensions use live native fields and current ItemConfig entries."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX

SOURCE = Path(__file__).resolve().parents[1] / 'source'
DRIVER = PREFIX + r'''
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "interfaces/lua/repentogon_entity_api.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"
#include <array>
#include <thread>
#include <vector>
static std::vector<unsigned char> moduleBytes,pickup,manager,game;
static std::uintptr_t managerSlot,gameSlot,gameOwner;
static std::array<std::uintptr_t,4> entries{};
static std::array<std::uintptr_t,1> generated{};
static std::uintptr_t wrapper;
static std::array<unsigned char,0xf8> item{};
template<class T>static void Put(std::vector<unsigned char>& b,unsigned offset,T v){std::memcpy(b.data()+offset,&v,sizeof(v));}
template<class T>static T At(const std::vector<unsigned char>& b,unsigned offset){T v{};std::memcpy(&v,b.data()+offset,sizeof(v));return v;}
static std::uintptr_t Address(const std::vector<unsigned char>& b){return reinterpret_cast<std::uintptr_t>(b.data());}
static int Native(lua_State* L){
 const auto op=luaL_checkinteger(L,1);
 if(op==1)entries[2]=entries[1];
 if(op==2)entries[2]=0;
 if(op==3){Put(pickup,0x604,std::uint32_t{9});}
 if(op==4){Put(pickup,0x604,std::uint32_t{0});}
 if(op==5)Put(pickup,kEntityTypeOffset,std::uint32_t{6});
 if(op==6)Put(pickup,kEntityTypeOffset,std::uint32_t{5});
 if(op==7)RetireEntityLifetime(Address(pickup));
 if(op==8){
  assert(At<std::uint32_t>(pickup,0x5dc)==0x12345678);
  assert(At<std::uint32_t>(pickup,0x608)==0x76543210);
 }
 if(op==9){Put(manager,kManagerItemConfigOffset+8,reinterpret_cast<std::uintptr_t>(entries.data()));}
 if(op==10){Put(manager,kManagerItemConfigOffset+8,reinterpret_cast<std::uintptr_t>(entries.data()+entries.size()));}
 if(op==11)wrapper=0;
 if(op==12)wrapper=entries[1];
 if(op==13){
  bool rejected=true;
  std::thread worker([&]{
   auto* other=luaL_newstate();
   for(auto fn:{RepentogonEntityPickupGetVarData,RepentogonEntityPickupSetVarData,
                 RepentogonEntityPickupAddCollectibleCycle}){
    lua_pushcfunction(other,fn);lua_pushnil(other);lua_pushinteger(other,1);
    const auto result=lua_pcall(other,2,1,0);
    const char* message=lua_tostring(other,-1);
    rejected=rejected&&result!=LUA_OK&&message&&std::strstr(message,"game thread");
    lua_pop(other,1);
   }
   lua_close(other);
  });
  worker.join();assert(rejected);
 }
 if(op==14)assert(At<std::uint32_t>(pickup,0x604)==9);
 return 0;
}
static void Extensions(lua_State* L) noexcept{
 PushEntityCallbackArgument(L,Address(pickup));lua_setglobal(L,"pickup");
 lua_pushcfunction(L,Native);lua_setglobal(L,"native");
 auto* shortHandle=lua_newuserdata(L,1);static_cast<void>(shortHandle);
 luaL_getmetatable(L,LuaRuntime::kEntityPickupMetatable);lua_setmetatable(L,-2);lua_setglobal(L,"shortPickup");
}
int main(int argc,char** argv){
 const bool enabled=argc==1||std::strcmp(argv[1],"disabled");
 moduleBytes.assign(kGameManagerGlobalSlotOffset+0x100,0);pickup.assign(0x1000,0);
 manager.assign(kManagerItemConfigOffset+0x40,0);game.assign(0x345f40,0);
 managerSlot=Address(manager);gameSlot=Address(game);gameOwner=reinterpret_cast<std::uintptr_t>(&gameSlot);
 const auto base=Address(moduleBytes);
 Put(moduleBytes,kGameManagerGlobalSlotOffset,reinterpret_cast<std::uintptr_t>(&managerSlot));
 Put(moduleBytes,kGameOwnerGlobalSlotOffset,reinterpret_cast<std::uintptr_t>(&gameSlot));
 Put(pickup,0,base+kEntityPickupVtableOffset);Put(pickup,kEntityTypeOffset,std::uint32_t{5});
 Put(pickup,kEntityVariantOffset,std::uint32_t{100});
 Put(pickup,0x5dc,std::uint32_t{0x12345678});Put(pickup,0x608,std::uint32_t{0x76543210});
 entries[1]=reinterpret_cast<std::uintptr_t>(item.data());entries[3]=entries[1];
 Put(manager,kManagerItemConfigOffset,reinterpret_cast<std::uintptr_t>(entries.data()));
 Put(manager,kManagerItemConfigOffset+8,reinterpret_cast<std::uintptr_t>(entries.data()+entries.size()));
 wrapper=entries[1];generated[0]=reinterpret_cast<std::uintptr_t>(&wrapper);
 Put(game,0x345f18,reinterpret_cast<std::uintptr_t>(generated.data()));
 Put(game,0x345f20,reinterpret_cast<std::uintptr_t>(generated.data()+generated.size()));
 LuaRuntime::SetEngineModuleBase(base);LuaRuntime::SetGameBindings(reinterpret_cast<std::uintptr_t>(&gameOwner),0);
 Files files(enabled);SetSessionSaveFilePort(&files);LuaRuntime::ObserveGameThread();
 const repentogon::NativePort port{Ready,Ready};repentogon::SetNativePort(&port);
 LuaRuntime::SetRuntimeExtensionInstaller(Extensions);
 const char* script=enabled?R"lua(
assert(REPENTOGON and REPENTOGON.FullCompatibility==false)
assert(type(pickup.AddCollectibleCycle)=='function','missing AddCollectibleCycle')
assert(type(pickup.GetVarData)=='function','missing GetVarData')
assert(type(pickup.SetVarData)=='function','missing SetVarData')
assert(pickup:GetVarData()==0)
for _,v in ipairs({-2147483648,2147483647,-1,4294967297,'25',1.0}) do
 pickup:SetVarData(v);local n=math.tointeger(v)&0xffffffff
 if n>=2147483648 then n=n-4294967296 end
 assert(pickup:GetVarData()==n)
end
local before=pickup:GetVarData()
for _,v in ipairs({1.5,{},false,'bad'}) do
 assert(not pcall(pickup.SetVarData,pickup,v));assert(pickup:GetVarData()==before)
 assert(not pcall(pickup.AddCollectibleCycle,pickup,v))
end
assert(not pcall(pickup.SetVarData,pickup))
assert(not pcall(pickup.AddCollectibleCycle,pickup,0))
assert(not pcall(pickup.AddCollectibleCycle,pickup,4))
native(9);assert(not pcall(pickup.AddCollectibleCycle,pickup,1));native(10)
assert(#pickup:GetCollectibleCycle()==0)
assert(pickup:AddCollectibleCycle(1)==true)
assert(pickup:AddCollectibleCycle('3')==true)
local ok,err=pcall(pickup.AddCollectibleCycle,pickup,4294967298)
assert(not ok and err:find('Invalid collectible ID 2',1,true))
native(1);assert(pickup:AddCollectibleCycle(2)==true)
native(2);assert(not pcall(pickup.AddCollectibleCycle,pickup,2))
assert(pickup:AddCollectibleCycle(-1)==true) -- Current procedural entry, not a fixed positive range.
native(11);assert(not pcall(pickup.AddCollectibleCycle,pickup,-1));native(12)
assert(not pcall(pickup.AddCollectibleCycle,pickup,-2))
assert(pickup:AddCollectibleCycle(4294967297)==true) -- Upstream casts to int32 before lookup.
for i=6,8 do assert(pickup:AddCollectibleCycle(1)==true) end
local cycle=pickup:GetCollectibleCycle();assert(#cycle==8)
assert(cycle[1]==1 and cycle[2]==3 and cycle[3]==2 and cycle[4]==-1 and cycle[5]==1)
assert(pickup:AddCollectibleCycle(3)==false)
assert(not pcall(pickup.AddCollectibleCycle,pickup,2)) -- Validate even when full.
assert(#pickup:GetCollectibleCycle()==8);native(8)
native(13);assert(#pickup:GetCollectibleCycle()==8 and pickup:GetVarData()==before)
native(3);assert(pickup:AddCollectibleCycle(1)==false);native(14)
local ok,err=pcall(pickup.AddCollectibleCycle,pickup,2)
assert(not ok and err:find('Invalid collectible ID 2',1,true));native(14);native(4)
local methods={pickup.GetVarData,pickup.SetVarData,pickup.AddCollectibleCycle}
native(5)
for _,fn in ipairs(methods) do
 assert(not pcall(fn,pickup,1));assert(not pcall(fn,{},1));assert(not pcall(fn,shortPickup,1))
end
native(6);native(8)
native(7)
for _,fn in ipairs(methods) do assert(not pcall(fn,pickup,1)) end
)lua":R"lua(
assert(pickup.GetVarData==nil and pickup.SetVarData==nil and pickup.AddCollectibleCycle==nil)
)lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@pickup-state.lua")!=LuaRuntime::LuaInitResult::Success){
  char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
  std::fprintf(stderr,"%s\n",error);return 1;
 }
 assert(LuaRuntime::ShutdownForModReload());
 LuaRuntime::SetRuntimeExtensionInstaller(nullptr);repentogon::SetNativePort(nullptr);SetSessionSaveFilePort(nullptr);
}
'''


class PickupStateTests(unittest.TestCase):
    def test_live_fields_cycle_bounds_and_extension_scope(self):
        with tempfile.TemporaryDirectory(prefix='pickup-state-') as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE,
                workdir=Path(folder),
                harness_source=DRIVER,
                extra_sources=() if (SOURCE.parent / 'src/interfaces/lua/pickup_flip_api.cpp')
                in test_support.layered_lua_runtime_sources(SOURCE) else
                (SOURCE.parent / 'src/interfaces/lua/pickup_flip_api.cpp',),
            )
            for mode in ('enabled', 'disabled'):
                with self.subTest(mode=mode):
                    result = subprocess.run([str(binary), mode], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
