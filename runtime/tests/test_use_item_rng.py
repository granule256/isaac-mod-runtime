"""3/23传同一颗原生道具RNG；模组推进回写，借用在RNG容器重分配后拒绝。"""
import subprocess,tempfile,unittest
from pathlib import Path
from .test_support import build_lua_harness
from . import test_lua_rng_owner_lifetime as owner

fixture=owner.fixture
MAIN=r'''
static std::uint32_t Seed(const std::vector<unsigned char>& bytes) {
 std::uint32_t seed{};
 std::memcpy(&seed,bytes.data()+kEntityPlayerRngVectorStride,sizeof(seed));
 return seed;
}
int main(){
 static_cast<void>(&WriteIsInvincible);
 static_cast<void>(&ReadIsInvincible);
 static_cast<void>(&WriteMaxDistance);
 static_cast<void>(&ReadMaxDistance);
 PublishFakeGame(0);
 WriteAt<std::uint8_t>(g_PlayerBytes,kEntityExistsOffset,1);
 LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 LuaRuntime::SetRngBindings(reinterpret_cast<std::uintptr_t>(&HostSetSeed),reinterpret_cast<std::uintptr_t>(&HostNext));
 LuaRuntime::ObserveGameThread();
 std::vector<unsigned char> vector(2*kEntityPlayerRngVectorStride);
 WriteAt<std::uint32_t>(vector,kEntityPlayerRngVectorStride,123);
 WriteAt<std::uintptr_t>(g_PlayerBytes,kEntityPlayerCollectibleRngVectorOffset,AddressOf(vector));
 WriteAt<std::uintptr_t>(g_PlayerBytes,kEntityPlayerCollectibleRngVectorOffset+8,AddressOf(vector)+vector.size());
 const char* source=R"lua(local m=RegisterMod('use-rng',1)
 m:AddCallback(1,function()end)
 m:AddCallback(23,function(_,id,r,p,flags,slot,var)
  assert(id==1 and type(r)=='userdata' and flags==4 and slot==0 and var==77)
  assert(r:GetSeed()==123 and p:GetCollectibleRNG(id):GetSeed()==123)
  r:Next();assert(p:GetCollectibleRNG(id):GetSeed()==124);savedUseRng=r
 end)
 m:AddCallback(3,function(_,id,r,p)
  assert(type(r)=='userdata' and r:GetSeed()==124);r:Next();assert(savedUseRng:GetSeed()==125)
 end))lua";
 if(LuaRuntime::InitializeFromBuffer(source,strlen(source),"@use-rng.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 if(LuaRuntime::DispatchPreUseItem(AddressOf(g_PlayerBytes),1,4,0,77))return 2;
 LuaRuntime::DispatchUseItem(AddressOf(g_PlayerBytes),1,4,0,77);
 if(LuaRuntime::TakeCallbackError()){LuaRuntime::LuaErrorHistoryEntryView e[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(e,8);for(std::size_t i=0;i<n;++i)std::printf("%s\n",e[i].text);return 3;}
 if(Seed(vector)!=125)return 4;
 // Entity::Remove clears Exists before MC_POST_ENTITY_REMOVE; the player's
 // RNG vector remains owned and valid until that object is destroyed.
 WriteAt<std::uint8_t>(g_PlayerBytes,kEntityExistsOffset,0);
 source="assert(savedUseRng:GetSeed()==125);savedUseRng:Next();assert(savedUseRng:GetSeed()==126)";
 if(LuaRuntime::InitializeFromBuffer(source,strlen(source),"@use-rng-expired.lua")!=LuaRuntime::LuaInitResult::Success)return 5;
 if(Seed(vector)!=126)return 6;
 std::vector<unsigned char> replacement=vector;
 WriteAt<std::uintptr_t>(g_PlayerBytes,kEntityPlayerCollectibleRngVectorOffset,AddressOf(replacement));
 WriteAt<std::uintptr_t>(g_PlayerBytes,kEntityPlayerCollectibleRngVectorOffset+8,AddressOf(replacement)+replacement.size());
 source="assert(not pcall(function()savedUseRng:Next()end))";
 if(LuaRuntime::InitializeFromBuffer(source,strlen(source),"@use-rng-reallocated.lua")!=LuaRuntime::LuaInitResult::Success)return 7;
 if(Seed(vector)!=126 || Seed(replacement)!=126)return 8;
}
'''
class UseItemRngTests(unittest.TestCase):
 def test_native_collectible_rng_and_lifetime(self):
  base=fixture.HARNESS[:fixture.HARNESS.index('GameRoomObservation ReadCurrentGameRoom(')]
  base+=owner.MAIN[:owner.MAIN.index('int main(')]+MAIN
  with tempfile.TemporaryDirectory(prefix='use-item-rng-')as tmp:
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(tmp),harness_source=base)
   r=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
