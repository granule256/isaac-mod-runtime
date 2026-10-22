"""第七批玩家方法：真实Lua参数/原生传递、失效引用、跨base校验。"""
import re,subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness,layered_lua_runtime_sources
MAIN=r'''
#include "interfaces/lua/api700_player.hpp"
#include "lua_object_handles.hpp"
#include "interfaces/lua/api700_string.hpp"
#include "interfaces/lua/api500_config.guards.hpp"
#include "interfaces/lua/vector_api.hpp"
#include <cstdlib>
#include "interfaces/lua/api700_player.guards.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "interfaces/lua/entity_ref_api.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <cstdio>
#include <cassert>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
static unsigned calls[6]{},allocated{},released{};
static void Delete(void*p){++released;std::free(p);}
static void* Assign(void*dest,const void*source){auto*d=static_cast<unsigned char*>(dest);const auto*s=static_cast<const unsigned char*>(source);std::uint64_t length{};const char*text{};std::memcpy(&length,s+8,8);std::memcpy(&text,s+16,8);if(d[0]&1U){void*p{};std::memcpy(&p,d+16,8);Delete(p);}std::memset(d,0,24);if(length<23){d[0]=static_cast<unsigned char>(length*2);std::memcpy(d+1,text,length);}else{auto*p=static_cast<char*>(std::malloc(length+1));++allocated;std::memcpy(p,text,length);p[length]=0;std::uint64_t cap=(length+1)|1;std::memcpy(d,&cap,8);std::memcpy(d+8,&length,8);std::memcpy(d+16,&p,8);}return dest;}
static void Text(const void*p,const char*expected){const auto*b=static_cast<const unsigned char*>(p);std::size_t size=b[0]>>1;const char*data=reinterpret_cast<const char*>(b+1);if(b[0]&1U){std::memcpy(&size,b+8,8);std::memcpy(&data,b+16,8);}assert(size==std::strlen(expected)&&!std::memcmp(data,expected,size));}
static LuaRuntime::VectorHandle Costume(const void*p,const void*t,bool head,const LuaRuntime::VectorHandle&v){assert(p==g_Entities[kPlayer].data()&&head&&v.x==3&&v.y==4);Text(t,"ThisIsALongNullFrameNameForTest");++calls[4];return{7,8};}
static void Replace(void*p,const void*item,const void*t,std::int32_t priority){assert(p==g_Entities[kPlayer].data()&&!item&&priority==-3);Text(t,"resources/aVeryLongCostumePath.png");++calls[5];}

static int CheckRef(lua_State*L){void*p=EntityRefBufferAt(L,1);assert(p==g_Entities[kPlayer].data()+0x1a70);std::uint32_t value{};std::memcpy(&value,p,4);assert(value==20);return 0;}
static int Advance(lua_State*){WriteAt<std::uint32_t>(g_Entities[kPlayer],0x1a70,20);return 0;}
static int StringErrorConsumer(lua_State*L,const void*,void*){return luaL_error(L,"deliberate native string consumer error");}
static int StringError(lua_State*L){return WithApi700NativeString(L,1,StringErrorConsumer,nullptr);}
static void Pill(void*p,std::int32_t id,const char*a){assert(p==g_Entities[kPlayer].data()&&id==-7);assert(a&&!std::strcmp(a,calls[0]<2?"Pickup":"Lift"));++calls[0];}
static void Trinket(void*p,std::int32_t id,const char*a,const char*b){assert(p==g_Entities[kPlayer].data()&&id==1);assert(a&&b&&!std::strcmp(a,calls[1]<2?"Pickup":"Lift")&&!std::strcmp(b,calls[1]<2?"PlayerPickupSparkle":"Spark"));++calls[1];}
static void Swap(void*p){assert(p==g_Entities[kPlayer].data());++calls[2];}
static void Remove(void*p,std::int32_t id,bool keep){assert(p==g_Entities[kPlayer].data()&&id==9);assert(keep==(calls[3]!=0));++calls[3];}
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
WriteAt<std::uint32_t>(g_Entities[kPlayer],0x1a70,7);WriteAt<std::uint32_t>(g_Entities[kPlayer],0x1a74,9);WriteAt<std::int32_t>(g_Entities[kPlayer],0x1a78,-2);WriteAt<std::uint32_t>(g_Entities[kPlayer],0x1a7c,0xf0000000);WriteWord(g_Entities[kPlayer],0x1a98,AddressOf(g_Entities[kEnemyA]));
namespace G=api700_player;for(unsigned i=0;i<6;++i)std::memcpy(g_ModuleBytes.data()+G::kEntries[i].offset,G::kEntries[i].guard,16);
std::memcpy(g_ModuleBytes.data()+G::kLastDamageEntry.offset,G::kLastDamageEntry.guard,16);std::memcpy(g_ModuleBytes.data()+G::kPocketEntry.offset,G::kPocketEntry.guard,16);std::memcpy(g_ModuleBytes.data()+G::kQueueEntry.offset,G::kQueueEntry.guard,16);std::memcpy(g_ModuleBytes.data()+api500_config::kStringAssignOffset,api500_config::kStringAssignGuard.data(),16);
LuaRuntime::LuaSpriteBindings sprite{};sprite.gameOperatorDelete=Delete;LuaRuntime::SetSpriteBindings(sprite);SetApi700StringAssignForTesting(Assign);
SetApi700PlayerNativeTestBindings({{engine_call::AddressOfFunction(&Pill),engine_call::AddressOfFunction(&Trinket),engine_call::AddressOfFunction(&Swap),engine_call::AddressOfFunction(&Remove),engine_call::AddressOfFunction(&Costume),engine_call::AddressOfFunction(&Replace)}});
auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));luaL_newmetatable(L,LuaRuntime::kEntityRefMetatable);lua_pushcfunction(L,EntityRefIndex);lua_setfield(L,-2,"__index");lua_getfield(L,-1,"__class");const bool missingClass=lua_isnil(L,-1);lua_pop(L,1);if(missingClass){lua_pushvalue(L,-1);lua_setfield(L,-2,"__class");}lua_pop(L,1);lua_pushcfunction(L,CreateEntityRefHandle);lua_setglobal(L,"EntityRef");RegisterApi700PlayerTypes(L);lua_pushcfunction(L,CheckRef);lua_setglobal(L,"checkRef");lua_pushcfunction(L,Advance);lua_setglobal(L,"advance");lua_pushcfunction(L,StringError);lua_setglobal(L,"stringError");PushEntityCallbackArgument(L,AddressOf(g_Entities[kPlayer]));lua_setglobal(L,"p");
// 接线前仍能运行同一Lua消费，错误由缺失公开方法产生；接线后不覆盖生产表。
#ifdef API700_LOCAL_WIRING
luaL_getmetatable(L,LuaRuntime::kEntityPlayerMetatable);lua_getfield(L,-1,"__methods");
#define B(n) lua_pushcfunction(L,Api700EntityPlayer##n);lua_setfield(L,-2,#n)
B(AnimatePill);B(AnimateTrinket);B(SwapActiveItems);B(TryRemoveCollectibleCostume);B(GetCostumeNullPos);B(ReplaceCostumeSprite);B(QueueExtraAnimation);B(GetLastDamageSource);B(GetPocketItem);
#undef B
lua_pop(L,2);
#endif
RegisterVectorReferenceMetatable(L);luaL_newmetatable(L,LuaRuntime::kVectorMetatable);lua_pushcfunction(L,VectorIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,VectorNewIndex);lua_setfield(L,-2,"__newindex");lua_newtable(L);static_cast<void>(AttachVectorMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);lua_pushcfunction(L,CreateVectorHandle);lua_setglobal(L,"Vector");
const char*script=R"lua(
source=p:GetLastDamageSource();assert(source.Type==7 and source.Variant==9 and source.SpawnerType==-2 and source.SpawnerVariant==0xf0000000 and source.Entity.Type==20);assert(getmetatable(source).__class==getmetatable(EntityRef()).__class);assert(not pcall(function()source.Type=8 end));advance();assert(source.Type==20);checkRef(source)
pocket=p:GetPocketItem(0);assert(getmetatable(pocket).__type=='PlayerPocketItem' and pocket.Unknown==nil);assert(not pcall(function()pocket.Unknown=3 end));assert(not pcall(function()p:GetPocketItem(-1)end));assert(not pcall(function()p:GetPocketItem(4)end))
local v=p:GetCostumeNullPos('ThisIsALongNullFrameNameForTest',0,Vector(3,4));assert(v.X==7 and v.Y==8)
assert(select('#',p:ReplaceCostumeSprite(nil,'resources/aVeryLongCostumePath.png',-3))==0)
assert(select('#',p:QueueExtraAnimation('Lift'))==0);p:QueueExtraAnimation('ThisIsALongQueuedAnimationNameForTest');p:QueueExtraAnimation('')
assert(not pcall(function()p:GetCostumeNullPos('Name',true,{})end));assert(not pcall(function()p:ReplaceCostumeSprite({},'path',0)end));assert(not pcall(function()p:QueueExtraAnimation({})end))
assert(type(p.AnimatePill)=='function');assert(select('#',p:AnimatePill(-7))==0);p:AnimatePill(-7,false);p:AnimatePill(-7,'Lift')
p:AnimateTrinket(0x100000001);p:AnimateTrinket(1,false,false);p:AnimateTrinket(1,'Lift','Spark');assert(select('#',p:SwapActiveItems())==0)
p:TryRemoveCollectibleCostume(9);p:TryRemoveCollectibleCostume(9,0);p:TryRemoveCollectibleCostume(9,true)
assert(not pcall(function()p:AnimatePill(1.5)end));assert(not pcall(function()p:AnimateTrinket(1,{})end));assert(not pcall(function()p:TryRemoveCollectibleCostume({})end));assert(not pcall(function()p.AnimatePill({},1)end))
)lua";
if(luaL_dostring(L,script)){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 1;}assert(calls[0]==3&&calls[1]==3&&calls[2]==1&&calls[3]==3&&calls[4]==1&&calls[5]==1);assert(allocated==released);
assert(luaL_dostring(L,"assert(not pcall(stringError,'ThisIsALongStringToExerciseGCOnError'));collectgarbage('collect')")==LUA_OK);assert(allocated==released);
std::vector<unsigned char>other=g_ModuleBytes;for(unsigned i=0;i<4;++i)other[G::kEntries[i].offset]^=1;auto base=AddressOf(other);WriteWord(g_Entities[kPlayer],0,base+kEntityPlayerVtableOffset);LuaRuntime::SetEngineModuleBase(base);assert(luaL_dostring(L,"assert(not pcall(function()return source.Type end));assert(not pcall(function()return pocket.Unknown end));assert(not pcall(checkRef,source))")==LUA_OK);
if(luaL_dostring(L,"for _,n in ipairs({'AnimatePill','AnimateTrinket','SwapActiveItems','TryRemoveCollectibleCostume'})do local ok,e=pcall(p[n],p,9);assert(not ok and string.find(e,'guard'),tostring(e))end")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 2;}
LuaRuntime::SetEngineModuleBase(g_EngineBase);WriteWord(g_Entities[kPlayer],0,g_EngineBase+kEntityPlayerVtableOffset);RetireEntityLifetime(AddressOf(g_Entities[kPlayer]));
if(luaL_dostring(L,"for _,n in ipairs({'AnimatePill','AnimateTrinket','SwapActiveItems','TryRemoveCollectibleCostume'})do local ok,e=pcall(p[n],p,9);assert(not ok and string.find(e,'reference'),tostring(e))end")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 3;}assert(luaL_dostring(L,"assert(not pcall(function()return source.Type end));assert(not pcall(function()return pocket.Unknown end));assert(not pcall(checkRef,source))")==LUA_OK);lua_close(L);assert(allocated==released);return 0;}
'''
def run(local=False,main=MAIN):
 prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')]
 prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
 source=fixture.SOURCE.parent/'src/interfaces/lua/api700_player.cpp'
 extra=tuple(f for f in (source,source.with_name("api700_string.cpp")) if f not in layered_lua_runtime_sources(fixture.SOURCE))
 with tempfile.TemporaryDirectory(prefix='api700-player-')as d:
  binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=prefix+ ('\n#define API700_LOCAL_WIRING\n' if local else '')+main,extra_sources=extra)
  return subprocess.run([str(binary)],capture_output=True,text=True)
class PlayerConsumer(unittest.TestCase):
 def test_player_native_contract(self):
  r=run();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
