"""Entity minecart, slot downcast, and pickup cycle extension contracts."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_support
from .test_repentogon_in_game import PREFIX

SOURCE = Path(__file__).resolve().parents[1] / 'source'
DRIVER = PREFIX + r'''
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/repentogon_entity_api.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"
#include <vector>
static std::vector<unsigned char> moduleBytes,entity,minecart,slot,pickup,flipState;
static unsigned calls;
static std::uintptr_t Address(const std::vector<unsigned char>& bytes){return reinterpret_cast<std::uintptr_t>(bytes.data());}
static void SetIdentity(std::vector<unsigned char>& bytes,std::uintptr_t vtable,std::uint32_t type,std::uint32_t variant){
 std::memcpy(bytes.data(),&vtable,sizeof(vtable));std::memcpy(bytes.data()+kEntityTypeOffset,&type,4);std::memcpy(bytes.data()+kEntityVariantOffset,&variant,4);
}
static void* Give(void* self,const RepentogonEntityVector& position,const RepentogonEntityVector& velocity){
 assert(self==entity.data()&&position.x==3&&position.y==4&&velocity.x==5&&velocity.y==6);++calls;
 const auto value=Address(minecart);std::memcpy(static_cast<unsigned char*>(self)+0x3c8,&value,sizeof(value));
 return minecart.data();
}
static void InitFlip(void* self){assert(self==pickup.data());++calls;const auto value=Address(flipState);std::memcpy(static_cast<unsigned char*>(self)+0x610,&value,sizeof(value));}
static void Extensions(lua_State* state) noexcept{
 isaac::runtime::PushEntityCallbackArgument(state,Address(entity));lua_setglobal(state,"entity");
 isaac::runtime::PushEntityCallbackArgument(state,Address(slot));lua_setglobal(state,"slot");
 isaac::runtime::PushEntityCallbackArgument(state,Address(pickup));lua_setglobal(state,"pickup");
}
int main(){
 moduleBytes.assign(0x26b6c8+16,0);entity.assign(0x4000,0);minecart.assign(0x4000,0);slot.assign(0x4000,0);pickup.assign(0x4000,0);flipState.assign(0x100,0);
 const auto base=Address(moduleBytes);
 SetIdentity(entity,base+kEntityNpcVtableOffset,20,1);SetIdentity(minecart,base+kEntityNpcVtableOffset,20,965);SetIdentity(slot,base+kEntitySlotVtableOffset,6,1);SetIdentity(pickup,base+kEntityPickupVtableOffset,5,100);
 const unsigned char giveGuard[]={0xff,0x03,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf6,0x57,0x02,0xa9};
 const unsigned char initGuard[]={0xff,0x43,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf7,0x13,0x00,0xf9};
 std::memcpy(moduleBytes.data()+0x6745c,giveGuard,16);std::memcpy(moduleBytes.data()+0x26b6c8,initGuard,16);
 const std::uintptr_t minecartPointer=Address(minecart);std::memcpy(entity.data()+0x3c8,&minecartPointer,sizeof(minecartPointer));
 const std::int32_t prize=123;std::memcpy(slot.data()+0x570,&prize,sizeof(prize));
 const std::uint32_t count=3,list[]={10,11,12};std::memcpy(pickup.data()+0x604,&count,sizeof(count));std::memcpy(pickup.data()+0x5e4,list,sizeof(list));
 const std::int32_t subtype=321;std::memcpy(flipState.data()+8,&subtype,sizeof(subtype));const std::uintptr_t flipPointer=Address(flipState);std::memcpy(pickup.data()+0x610,&flipPointer,sizeof(flipPointer));
 LuaRuntime::SetEngineModuleBase(base);LuaRuntime::ObserveGameThread();
 Files files(true);SetSessionSaveFilePort(&files);const repentogon::NativePort port{Ready,Ready};repentogon::SetNativePort(&port);
 SetRepentogonEntityNativeTestBindings({Give,InitFlip});
 LuaRuntime::SetRuntimeExtensionInstaller(Extensions);
 const char* script=R"lua(
local car=entity:GiveMinecart(Vector(3,4),Vector(5,6));assert(car and car.Type==20 and car.Variant==965)
assert(entity:GetMinecart():ToNPC().Type==20)
assert(entity:ToSlot()==nil)
if slot.Type~=6 or slot.Variant~=1 then error('slot identity '..tostring(slot.Type)..':'..tostring(slot.Variant)) end
local s=slot:ToSlot();if type(s)~='userdata' then error('slot cast value='..tostring(s)) end
if s:GetPrizeCollectible()~=123 then error('prize='..tostring(s:GetPrizeCollectible())) end
local cycle=pickup:GetCollectibleCycle();if #cycle~=3 or cycle[1]~=10 or cycle[2]~=11 or cycle[3]~=12 then error('cycle='..#cycle..':'..tostring(cycle[1])..':'..tostring(cycle[2])..':'..tostring(cycle[3])) end
local flip=pickup:GetFlipCollectible();if flip~=321 then error('flip='..tostring(flip)) end
pickup:InitFlipState();assert(pickup:GetFlipCollectible()==321)
pickup:RemoveCollectibleCycle();assert(#pickup:GetCollectibleCycle()==0)
assert(not pcall(function()entity:GiveMinecart(Vector(3,4),nil)end))
assert(not pcall(function()s:GetPrizeCollectible(1)end))
assert(not pcall(function()pickup:InitFlipState(1)end))
)lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@entity-extension.lua")!=LuaRuntime::LuaInitResult::Success){
  char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));std::fprintf(stderr,"%s\n",error);return 1;
 }
 assert(calls==2);assert(LuaRuntime::ShutdownForModReload());
 SetRepentogonEntityNativeTestBindings({});repentogon::SetNativePort(nullptr);SetSessionSaveFilePort(nullptr);LuaRuntime::SetRuntimeExtensionInstaller(nullptr);
}
'''

class RepentogonEntityApiTests(unittest.TestCase):
    def test_minecart_slot_and_pickup_cycle(self):
        with tempfile.TemporaryDirectory(prefix='repentogon-entity-') as folder:
            binary=test_support.build_lua_harness(source_root=SOURCE,workdir=Path(folder),harness_source=DRIVER)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
