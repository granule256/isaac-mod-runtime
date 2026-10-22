"""实体/玩家/网格返回的RNG应引用原生状态，RNG()仍拥有独立状态。"""
import subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_batch343_get_color_and_lists as fixture
from .test_support import build_lua_harness
MAIN=r'''
std::vector<unsigned char> g_TestRoom,g_TestGrid,g_TestDoor;
GameRoomObservation ReadCurrentGameRoom(uintptr_t,void** out){*out=g_TestRoom.data();return GameRoomObservation::Success;}
void HostSetSeed(void* object,std::uint32_t seed,std::uint32_t shift){
 std::uint32_t fields[4]={seed,shift,shift+1,shift+2};std::memcpy(object,fields,sizeof(fields));
}
void HostNext(void* object){std::uint32_t seed=0;std::memcpy(&seed,object,4);++seed;std::memcpy(object,&seed,4);}
std::uint32_t Seed(const std::vector<unsigned char>& b,std::size_t o){std::uint32_t v;std::memcpy(&v,b.data()+o,4);return v;}
int main(){
 PublishFakeMemory();WriteAt<std::uint8_t>(g_PlayerBytes,kEntityExistsOffset,1);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 LuaRuntime::SetRngBindings(reinterpret_cast<std::uintptr_t>(&HostSetSeed),reinterpret_cast<std::uintptr_t>(&HostNext));
 std::array<std::vector<unsigned char>,4> vectors;
 std::uintptr_t offsets[]={kEntityPlayerCollectibleRngVectorOffset,kEntityPlayerTrinketRngVectorOffset,kEntityPlayerCardRngVectorOffset,kEntityPlayerPillRngVectorOffset};
 for(unsigned i=0;i<4;++i){vectors[i].assign(32,0);WriteAt<std::uint32_t>(vectors[i],16,100+i);
  WriteAt<std::uintptr_t>(g_PlayerBytes,offsets[i],AddressOf(vectors[i]));WriteAt<std::uintptr_t>(g_PlayerBytes,offsets[i]+8,AddressOf(vectors[i])+32);}
 WriteAt<std::uint32_t>(g_PlayerBytes,kEntityDropSeedOffset,104);
 g_TestRoom.assign(kRoomDoorObjectTableOffset+8*sizeof(std::uintptr_t)+32,0);g_TestGrid.assign(0x200,0);
 WriteAt<std::uint32_t>(g_TestRoom,kRoomGridWidthOffset,13);WriteAt<std::uint32_t>(g_TestRoom,kRoomGridHeightOffset,7);
 WriteAt<std::uintptr_t>(g_TestRoom,kRoomGridEntityTableOffset+5*sizeof(std::uintptr_t),AddressOf(g_TestGrid));
 WriteAt<std::int32_t>(g_TestGrid,kGridEntityGridIndexOffset,5);WriteAt<std::uint32_t>(g_TestGrid,kGridEntityRngOffset,105);
 g_TestDoor.assign(0x400,0);
 WriteAt<std::uintptr_t>(g_TestDoor,0,g_EngineBase+kGridEntity_DoorVtableOffset);
 WriteAt<std::int32_t>(g_TestDoor,kGridEntityGridIndexOffset,-1);
 WriteAt<std::uint32_t>(g_TestDoor,kGridEntityRngOffset,106);
 WriteAt<std::uintptr_t>(g_TestRoom,kRoomDoorObjectTableOffset+2*sizeof(std::uintptr_t),AddressOf(g_TestDoor));
 const char* script=R"lua(
 local m=RegisterMod('rng-references',1);local step=0;local saved,owned
 m:AddCallback(1,function()
  step=step+1;local p=Isaac.GetPlayer(0)
  local function rngs() return {p:GetCollectibleRNG(1),p:GetTrinketRNG(1),p:GetCardRNG(1),p:GetPillRNG(1),p:GetDropRNG(),Game():GetRoom():GetGridEntity(5):GetRNG(),Game():GetRoom():GetDoor(2):ToDoor():GetRNG()} end
  if step==1 then
   saved=rngs();local second=rngs();owned=RNG();owned:SetSeed(77,1)
   for i,r in ipairs(saved) do assert(r:GetSeed()==99+i);r:Next();assert(second[i]:GetSeed()==100+i);r:SetSeed(199+i,1) end
   assert(owned:GetSeed()==77)
  elseif step==2 then
   for i,r in ipairs(saved) do assert(r:GetSeed()==299+i) end
   assert(owned:GetSeed()==77)
  elseif step==3 then
   assert(not pcall(function() saved[1]:Next() end))
   assert(not pcall(function() saved[6]:Next() end))
   assert(not pcall(function() saved[7]:Next() end))
   assert(owned:Next()==78)
  elseif step==4 then
   for i=2,5 do
    assert(not pcall(function() saved[i]:GetSeed() end))
    assert(not pcall(function() saved[i]:SetSeed(42,1) end))
    assert(not pcall(function() saved[i]:Next() end))
   end
   assert(owned:Next()==79)
  end
 end)
 )lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@rng-references.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 auto run=[](){LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError()){LuaRuntime::LuaErrorHistoryEntryView e[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(e,8);for(std::size_t i=0;i<n;++i)std::printf("%s\n",e[i].text);return false;}return true;};
 if(!run())return 2;
 for(unsigned i=0;i<4;++i){if(Seed(vectors[i],16)!=200+i)return 3;WriteAt<std::uint32_t>(vectors[i],16,300+i);}
 if(Seed(g_PlayerBytes,kEntityDropSeedOffset)!=204||Seed(g_TestGrid,kGridEntityRngOffset)!=205||Seed(g_TestDoor,kGridEntityRngOffset)!=206)return 4;
 WriteAt<std::uint32_t>(g_PlayerBytes,kEntityDropSeedOffset,304);WriteAt<std::uint32_t>(g_TestGrid,kGridEntityRngOffset,305);WriteAt<std::uint32_t>(g_TestDoor,kGridEntityRngOffset,306);if(!run())return 5;
 std::vector<unsigned char> replacement=vectors[0];WriteAt<std::uintptr_t>(g_PlayerBytes,offsets[0],AddressOf(replacement));WriteAt<std::uintptr_t>(g_PlayerBytes,offsets[0]+8,AddressOf(replacement)+32);
 WriteAt<std::uintptr_t>(g_TestRoom,kRoomGridEntityTableOffset+5*sizeof(std::uintptr_t),0);WriteAt<std::uintptr_t>(g_TestRoom,kRoomDoorObjectTableOffset+2*sizeof(std::uintptr_t),0);if(!run())return 6;
 WriteAt<std::uint8_t>(g_PlayerBytes,kEntityExistsOffset,0);if(!run())return 7;
 if(Seed(g_PlayerBytes,kEntityDropSeedOffset)!=304)return 8;
 return 0;
}
'''
class RngReferenceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-rng-references-')
  source=fixture.HARNESS[:fixture.HARNESS.index('GameRoomObservation ReadCurrentGameRoom(')]+MAIN
  for name in ('CURRENT_TINT','CURRENT_SHIFT','DEFAULT_TINT','SPLAT_TINT'):
   for i,v in enumerate(getattr(fixture,name)):source=source.replace(f'{name}_{i}',repr(v))
  for name in ('COLLECTIBLE_COUNT','TRINKET_COUNT','ENTITY_DEFAULT_COLOR_OFFSET','ENTITY_SPLAT_COLOR_OFFSET'):source=source.replace(name,str(getattr(fixture,name)))
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_shared_native_state_and_expired_owners(self):
  r=subprocess.run([str(self.binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
