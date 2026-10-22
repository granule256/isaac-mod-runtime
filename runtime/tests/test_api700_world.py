"""当前PC版本坐标/种子/原生容器状态，经真实公开Lua表调用。"""
import unittest
from .test_api500_world import run_world as run_main
MAIN=r'''
#include "interfaces/lua/api700_world.hpp"
#include "interfaces/lua/api700_containers.guards.hpp"
#include "lua_object_handles.hpp"
#include "interfaces/lua/api700_world.guards.hpp"
#include "interfaces/lua/api700_string.hpp"
#include "interfaces/lua/api500_config.guards.hpp"
#include "interfaces/lua/rng_api.hpp"
#include "game_observer.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <cstdio>
#include <cstring>
#include <cassert>
#include <cstdlib>
using namespace isaac::runtime;using Vec=LuaRuntime::VectorHandle;
void* Api500WorldRoom(){return g_RoomBytes.data();}
void* Api500WorldPool(){return g_GameBytes.data()+0x242c0;}
static unsigned calls[6]{},allocs{},frees{},fontDestructions{},fortuneCalls{};
static bool FontLoaded(const void*p){assert(p==g_GameBytes.data()+0x24f9c8);return true;}
static void FontDestroyed(void*){++fontDestructions;}
static void Delete(void*p){++frees;std::free(p);}
static void* Assign(void*dest,const void*source){auto*d=static_cast<unsigned char*>(dest);const auto*s=static_cast<const unsigned char*>(source);std::uint64_t length{};const char*text{};std::memcpy(&length,s+8,8);std::memcpy(&text,s+16,8);std::memset(d,0,24);if(length<23){d[0]=static_cast<unsigned char>(length*2);std::memcpy(d+1,text,length);}else{auto*p=static_cast<char*>(std::malloc(length+1));++allocs;std::memcpy(p,text,length);p[length]=0;std::uint64_t cap=(length+1)|1;std::memcpy(d,&cap,8);std::memcpy(d+8,&length,8);std::memcpy(d+16,&p,8);}return dest;}
static Vec Wrap(const void*p,const Vec&v,float a,float b,float c,float d){assert(p==g_RoomBytes.data()&&v.x==10&&v.y==20&&a==3&&b==3&&c==3&&d==3);++calls[0];if(calls[0]==2)LuaRuntime::SetEngineModuleBase(0);return{4,5};}
static Vec End(const Vec&a,const Vec&b,const Vec&c,const void*p,float margin){assert(a.x==1&&b.y==4&&c.x==5&&margin==7);assert(!p||p==g_Entities[kPlayer].data());++calls[1];return{8,9};}
static std::int32_t Seed(const void*p){const auto*b=static_cast<const unsigned char*>(p);std::size_t size=b[0]>>1;const char*text=reinterpret_cast<const char*>(b+1);if(b[0]&1U){std::memcpy(&size,b+8,8);std::memcpy(&text,b+16,8);}++calls[2];return size==3&&!std::memcmp(text,"yes",3)?4:0;}
static std::int32_t Pill(void*p,std::int32_t effect){assert(p==g_GameBytes.data()+0x242c0&&effect==-7);++calls[3];return 25;}
static void Fortune(void*p,const char*name){assert(p==g_GameBytes.data()+0x25c30);assert(!std::strcmp(name,fortuneCalls==0?"Fortune_General":"Fortune_Rules"));++fortuneCalls;}
struct Desc{std::int32_t v[8];};
static Desc Area(const void*p){assert(p==g_RoomBytes.data());++calls[4];return{{1,2,3,4,5,6,7,8}};}
static Desc Tile(const void*p){assert(p==g_RoomBytes.data());++calls[5];return{{8,7,6,5,4,3,2,1}};}
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);CreateBlocks();g_GameBytes.resize(0x320000);FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
std::vector<unsigned char>bits(16);WriteWord(g_GameBytes,0x242c0+0x908,AddressOf(bits));WriteAt<std::uint64_t>(g_GameBytes,0x242c0+0x910,100);WriteAt<std::uint32_t>(g_GameBytes,0x21518,111);WriteAt<std::uint32_t>(g_GameBytes,0x21528,123);
for(const auto&g:api700_containers::kEntries)std::memcpy(g_ModuleBytes.data()+g.offset,g.guard,16);
for(const auto&g:api700_world::kGuards)std::memcpy(g_ModuleBytes.data()+g.offset,g.bytes.data(),16);
std::memcpy(g_ModuleBytes.data()+api500_config::kStringAssignOffset,api500_config::kStringAssignGuard.data(),16);
const std::uintptr_t native[]={engine_call::AddressOfFunction(&Wrap),engine_call::AddressOfFunction(&End),engine_call::AddressOfFunction(&Seed),engine_call::AddressOfFunction(&Pill),engine_call::AddressOfFunction(&Area),engine_call::AddressOfFunction(&Tile),engine_call::AddressOfFunction(&Fortune)};SetApi700WorldNativeTestBindings(native,7);
LuaRuntime::LuaSpriteBindings sprites{};sprites.gameOperatorDelete=Delete;LuaRuntime::SetSpriteBindings(sprites);SetApi700StringAssignForTesting(Assign);
LuaRuntime::LuaFontBindings fonts{};fonts.isLoaded=FontLoaded;fonts.destructor_=FontDestroyed;LuaRuntime::SetFontBindings(fonts);
const char*script=R"lua(
assert(type(getmetatable(EntityRef()).__class)=='table');local ref=EntityRef();ref.Position=Vector(2,3);ref.IsFriendly=true;ref.IsCharmed=true;assert(ref.Position.X==2 and ref.IsFriendly and ref.IsCharmed);local g=Game();local r=g:GetRoom();local v=r:ScreenWrapPosition(Vector(10,20),3);assert(v.X==4 and v.Y==5 and v:Length()>6)
local pos=EntityLaser.CalculateEndPoint(Vector(1,2),Vector(3,4),Vector(5,6),nil,7);assert(pos.X==8 and pos.Y==9)
assert(EntityLaser.CalculateEndPoint(Vector(1,2),Vector(3,4),Vector(5,6),Isaac.GetPlayer(0),7).Y==9)
assert(EntityLaser.CalculateEndPoint(Vector(1,2),Vector(3,4),Vector(5,6),false,7).Y==9)
assert(not pcall(function()EntityLaser.CalculateEndPoint({},Vector(3,4),Vector(5,6),nil,7)end));assert(not pcall(function()EntityLaser.CalculateEndPoint(Vector(1,2),Vector(3,4),Vector(5,6),{},7)end))
assert(Seeds.GetSeedEffect('yes')==4 and Seeds.GetSeedEffect('no')==0 and Seeds.IsSpecialSeed('yes') and not Seeds.IsSpecialSeed(string.rep('z',300)))
assert(not pcall(function()Seeds.GetSeedEffect({})end));assert(Isaac.AddPillEffectToPool(-7)==25)
assert(Isaac.WorldToScreenDistance(Vector(10,-20)).X==6.5 and Isaac.WorldToScreenDistance(Vector(10,-20)).Y==-13)
assert(not pcall(function()r:ScreenWrapPosition({},3)end));assert(not pcall(function()Isaac.AddPillEffectToPool(1.5)end));assert(not pcall(function()Isaac.WorldToScreenDistance({})end))
local list=r:GetEntities();assert(list.Size>0 and type(list:Get(0))=='userdata');local a=r:GetLRoomAreaDesc();local t=r:GetLRoomTileDesc();assert(type(a)=='userdata' and getmetatable(a).__type=='LRoomAreaDesc' and getmetatable(t).__type=='LRoomTileDesc');assert(not pcall(function()a.Unknown=5 end))
assert(select('#',g:ShowFortune())==0);assert(select('#',g:ShowRule())==0);local f=g:GetFont();assert(type(f)=='userdata' and f:IsLoaded());local dropped=g:GetFont();dropped=nil;collectgarbage('collect');heldGameFont=f
local ambush=g:GetAmbush();local overlay=g:GetItemOverlay();assert(getmetatable(ambush).__type=='Ambush' and getmetatable(overlay).__type=='ItemOverlay' and ambush.Unknown==nil);assert(not pcall(function()ambush.Unknown=2 end))
local pool=g:GetItemPool();assert(select('#',pool:AddRoomBlacklist(3))==0);pool:AddRoomBlacklist(66);assert(not pcall(function()pool:AddRoomBlacklist(100)end));assert(not pcall(function()pool:AddRoomBlacklist(-1)end))
local rng=g:GetLevel():GetDevilAngelRoomRNG();assert(type(rng)=='userdata' and rng:GetSeed()==123);heldLevelRng=rng
r:ScreenWrapPosition(Vector(10,20),3)
assert(not pcall(function()return f:IsLoaded()end));assert(not pcall(function()return rng:GetSeed()end));assert(not pcall(function()return ambush.Unknown end));assert(not pcall(function()return overlay.Unknown end))
)lua";
if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@api700-world.lua")!=LuaRuntime::LuaInitResult::Success){LuaRuntime::LuaErrorHistoryEntryView e[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(e,8);for(std::size_t i=0;i<n;++i)std::fprintf(stderr,"%s\n",e[i].text);return 1;}
assert(calls[0]==2&&calls[1]==3&&calls[2]==4&&calls[3]==1&&calls[4]==1&&calls[5]==1);assert(bits[0]==8&&bits[8]==4&&allocs==frees&&fontDestructions==0&&fortuneCalls==2);
return 0;}
'''
class WorldConsumer(unittest.TestCase):
 def test_public_world_contract(self):
  r=run_main(main=MAIN);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
