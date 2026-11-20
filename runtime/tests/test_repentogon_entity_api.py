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
#include "interfaces/lua/pickup_flip_api.hpp"
#include "interfaces/lua/repentogon_entity_api.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"
#include <cstdlib>
#include <vector>
static std::vector<unsigned char> moduleBytes,game,room,animation,entity,minecart,slot,pickup,flipState,ghost;
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
static bool CanReroll(const void* self){return self==pickup.data();}
static void* Allocate(std::size_t size){return std::calloc(1,size);}
static void Deallocate(void* value){std::free(value);}
static void Mutex(void*){}
static std::uint32_t NextSeed(std::uint32_t){return 123;}
static std::int32_t Seeded(void*,std::uint32_t){return 321;}
static void SetFlip(void* self,const isaac::runtime::pickup_flip::SaveStatePointer& value){
 assert(self==pickup.data());++calls;
 std::memcpy(static_cast<unsigned char*>(self)+0x610,&value.saveState,sizeof(value.saveState));
 std::memcpy(static_cast<unsigned char*>(self)+0x618,&value.reference,sizeof(value.reference));
}
static bool Decrement(void*){return true;}
static void Reset(void*){}
static void Copy(void*,const void*){}
static void Swap(void*,void*){}
static void Destroy(void*){}
static void Setup(void*,std::uint32_t,std::int32_t,std::uint32_t,bool){}
static void Load(void*){}
static void Play(void*,const char*,bool){}
static void Update(void*){}
static int SetGhost(lua_State* state){
 const int mode=luaL_checkinteger(state,1);
 const std::uintptr_t address=mode==1?Address(ghost):mode==2?Address(entity):0;
 std::memcpy(pickup.data()+0x5c8,&address,sizeof(address));return 0;
}
static void Extensions(lua_State* state) noexcept{
 isaac::runtime::PushEntityCallbackArgument(state,Address(entity));lua_setglobal(state,"entity");
 isaac::runtime::PushEntityCallbackArgument(state,Address(slot));lua_setglobal(state,"slot");
 isaac::runtime::PushEntityCallbackArgument(state,Address(pickup));lua_setglobal(state,"pickup");
 lua_pushcfunction(state,SetGhost);lua_setglobal(state,"_setGhost");
}
int main(){
 moduleBytes.assign(kGameOwnerGlobalSlotOffset+sizeof(std::uintptr_t),0);
 game.assign(0x22000,0);room.assign(0x100,0);animation.assign(0x150,0);
 entity.assign(0x4000,0);minecart.assign(0x4000,0);slot.assign(0x4000,0);pickup.assign(0x4000,0);flipState.assign(0x100,0);ghost.assign(0x4000,0);
 const auto base=Address(moduleBytes);
 const auto gameAddress=Address(game);const auto roomAddress=Address(room);
 std::memcpy(moduleBytes.data()+kGameOwnerGlobalSlotOffset,&gameAddress,sizeof(gameAddress));
 std::memcpy(game.data()+kGameRoomPointerOffset,&roomAddress,sizeof(roomAddress));
 SetIdentity(entity,base+kEntityNpcVtableOffset,20,1);SetIdentity(minecart,base+kEntityNpcVtableOffset,20,965);SetIdentity(slot,base+kEntitySlotVtableOffset,6,1);SetIdentity(pickup,base+kEntityPickupVtableOffset,5,100);
 SetIdentity(ghost,base+kEntityEffectVtableOffset,kEntityTypeEffect,191);
 const std::uint32_t initSeed=1234;std::memcpy(pickup.data()+kEntityInitSeedOffset,&initSeed,sizeof(initSeed));
 const auto animationAddress=Address(animation);std::memcpy(pickup.data()+kEntitySpriteOffset+kAnim2AnimationArrayOffset,&animationAddress,sizeof(animationAddress));
 const std::uint32_t animationCount=1;std::memcpy(pickup.data()+kEntitySpriteOffset+kAnim2AnimationCountOffset,&animationCount,sizeof(animationCount));
 animation[0]=8;std::memcpy(animation.data()+1,"Idle",4);
 const unsigned char giveGuard[]={0xff,0x03,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf6,0x57,0x02,0xa9};
 std::memcpy(moduleBytes.data()+0x6745c,giveGuard,16);
 const std::uintptr_t minecartPointer=Address(minecart);std::memcpy(entity.data()+0x3c8,&minecartPointer,sizeof(minecartPointer));
 const std::int32_t prize=123;std::memcpy(slot.data()+0x570,&prize,sizeof(prize));
 const std::uint32_t count=3,list[]={10,11,12};std::memcpy(pickup.data()+0x604,&count,sizeof(count));std::memcpy(pickup.data()+0x5e4,list,sizeof(list));
 const std::int32_t subtype=321;std::memcpy(flipState.data()+8,&subtype,sizeof(subtype));const std::uintptr_t flipPointer=Address(flipState);std::memcpy(pickup.data()+0x610,&flipPointer,sizeof(flipPointer));
 LuaRuntime::SetEngineModuleBase(base);LuaRuntime::ObserveGameThread();
 Files files(true);SetSessionSaveFilePort(&files);const repentogon::NativePort port{Ready,Ready};repentogon::SetNativePort(&port);
 SetRepentogonEntityNativeTestBindings({Give});
 isaac::runtime::pickup_flip::NativeBindings flip{};
 flip.canReroll=CanReroll;flip.allocate=Allocate;flip.deallocate=Deallocate;
 flip.mutexCtor=Mutex;flip.mutexInit=Mutex;flip.nextSeed=NextSeed;flip.seededCollectible=Seeded;
 flip.setFlipState=SetFlip;flip.decrementReference=Decrement;flip.resetAnm2=Reset;
 flip.copyAnm2=Copy;flip.swapAnm2=Swap;flip.destroyAnm2=Destroy;
 flip.setupCollectibleGraphics=Setup;flip.loadGraphics=Load;flip.play=Play;flip.update=Update;
 isaac::runtime::pickup_flip::SetNativeTestBindings(flip);
 LuaRuntime::SetRuntimeExtensionInstaller(Extensions);
 const char* script=R"lua(
entity:SetInvincible(true);assert(entity:IsInvincible())
entity:SetInvincible(false);assert(not entity:IsInvincible())
assert(not pcall(function() entity:SetInvincible(1) end))
local car=entity:GiveMinecart(Vector(3,4),Vector(5,6));assert(car and car.Type==20 and car.Variant==965)
assert(entity:GetMinecart():ToNPC().Type==20)
assert(entity:ToSlot()==nil)
if slot.Type~=6 or slot.Variant~=1 then error('slot identity '..tostring(slot.Type)..':'..tostring(slot.Variant)) end
local s=slot:ToSlot();if type(s)~='userdata' then error('slot cast value='..tostring(s)) end
if s:GetPrizeCollectible()~=123 then error('prize='..tostring(s:GetPrizeCollectible())) end
assert(pickup:GetPickupGhost()==nil)
_setGhost(1);local ghost=pickup:GetPickupGhost()
assert(ghost and ghost:ToEffect() and ghost.Type==1000 and ghost.Variant==191)
_setGhost(2);assert(pickup:GetPickupGhost()==nil) -- not an effect
_setGhost(0);assert(pickup:GetPickupGhost()==nil)
assert(not pcall(pickup.GetPickupGhost,entity))
local cycle=pickup:GetCollectibleCycle();if #cycle~=3 or cycle[1]~=10 or cycle[2]~=11 or cycle[3]~=12 then error('cycle='..#cycle..':'..tostring(cycle[1])..':'..tostring(cycle[2])..':'..tostring(cycle[3])) end
local flip=pickup:GetFlipCollectible();if flip~=321 then error('flip='..tostring(flip)) end
pickup:InitFlipState();assert(pickup:GetFlipCollectible()==321)
pickup:InitFlipState(654,false);assert(pickup:GetFlipCollectible()==654)
pickup:InitFlipState(0,true);assert(pickup:GetFlipCollectible()==321)
pickup:RemoveCollectibleCycle();assert(#pickup:GetCollectibleCycle()==0)
assert(not pcall(function()entity:GiveMinecart(Vector(3,4),nil)end))
assert(not pcall(function()s:GetPrizeCollectible(1)end))
assert(not pcall(function()pickup:InitFlipState('bad')end))
assert(not pcall(function()pickup:InitFlipState(1,true,2)end))
)lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@entity-extension.lua")!=LuaRuntime::LuaInitResult::Success){
  char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));std::fprintf(stderr,"%s\n",error);return 1;
 }
 if(calls!=4){std::fprintf(stderr,"native calls=%u\n",calls);return 1;}
 assert(LuaRuntime::ShutdownForModReload());
 isaac::runtime::pickup_flip::SetNativeTestBindings({});SetRepentogonEntityNativeTestBindings({});
 repentogon::SetNativePort(nullptr);SetSessionSaveFilePort(nullptr);LuaRuntime::SetRuntimeExtensionInstaller(nullptr);
}
'''

class RepentogonEntityApiTests(unittest.TestCase):
    def test_minecart_slot_and_pickup_cycle(self):
        with tempfile.TemporaryDirectory(prefix='repentogon-entity-') as folder:
            flip_source=SOURCE.parent/'src/interfaces/lua/pickup_flip_api.cpp'
            extra=() if flip_source in test_support.layered_lua_runtime_sources(SOURCE) else (flip_source,)
            binary=test_support.build_lua_harness(source_root=SOURCE,workdir=Path(folder),
                                                    harness_source=DRIVER,extra_sources=extra)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
