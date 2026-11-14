"""Native REPENTOGON callback delivery through the production Lua callback table."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_support

SOURCE = Path(__file__).resolve().parents[1] / 'source'

# The small VM isolates the real shared-table runner from native installation.
POLICY_DRIVER = r'''
#include "program/callback_bootstrap.hpp"
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
#include <cassert>
#include <cstdio>
static int Invoke(lua_State* s) {
    const int n=lua_gettop(s);lua_getfield(s,2,"Function");lua_getfield(s,2,"Mod");
    for(int i=3;i<=n;++i)lua_pushvalue(s,i);lua_call(s,n-1,1);return 1;
}
static int Noop(lua_State*){return 0;}
static int Yes(lua_State* s){lua_pushboolean(s,1);return 1;}
static void Run(lua_State* s,const char* text){
    if(luaL_dostring(s,text)!=LUA_OK){std::fprintf(stderr,"%s\n",lua_tostring(s,-1));assert(false);}
}
int main() {
    auto* s=luaL_newstate();
    luaL_requiref(s,"_G",luaopen_base,1);lua_pop(s,1);
    luaL_requiref(s,"table",luaopen_table,1);lua_pop(s,1);
    luaL_requiref(s,"string",luaopen_string,1);lua_pop(s,1);
    Run(s,"debug={getinfo=function()return {name=\'test\'}end}");
    Run(s,"Isaac={SetBuiltInCallbackState=function()end};ModCallbacks={MC_PRE_MOD_UNLOAD=73}");
    assert(luaL_loadbuffer(s,isaac::runtime::kPcCallbackBootstrap,sizeof(isaac::runtime::kPcCallbackBootstrap)-1,"@callbacks.lua")==LUA_OK);
    lua_pushcfunction(s,Invoke);lua_pushcfunction(s,Noop);lua_pushcfunction(s,Yes);
    lua_pushcfunction(s,Invoke);lua_pushnil(s);lua_pushcfunction(s,Yes);lua_call(s,6,5);lua_pop(s,5);
    Run(s,R"lua(
local mt={};mt.__index=mt
mt.__add=function(a,b)return setmetatable({X=a.X+b.X,Y=a.Y+b.Y},mt)end
local function V(x,y)return setmetatable({X=x,Y=y},mt)end
local m={};local calls=0
Isaac.AddPriorityCallback(m,1080,0,function(_,entity,offset)
    calls=calls+1;assert(offset.X==10 and offset.Y==20);return V(2,3)
end,7)
Isaac.AddPriorityCallback(m,1080,1,function(_,entity,offset)
    calls=calls+1;assert(offset.X==12 and offset.Y==23);return V(-1,4)
end,7)
local result=Isaac.RunCallbackWithParam(1080,7,{},V(10,20))
assert(calls==2 and result.X==11 and result.Y==27,'render offsets must accumulate')
local inside=false
Isaac.AddPriorityCallback(m,1084,0,function(_,entity,offset)
 if not inside then
  inside=true;local nested=Isaac.RunCallbackWithParam(1084,7,{},V(100,200));inside=false
  assert(nested.X==103 and nested.Y==207)
 else assert(offset.X==100 and offset.Y==200) end
 return V(2,3)
end,7)
Isaac.AddPriorityCallback(m,1084,1,function(_,entity,offset)
 assert(offset.X==(inside and 102 or 12));return V(1,4)
end,7)
local outer=Isaac.RunCallbackWithParam(1084,7,{},V(10,20));assert(outer.X==13 and outer.Y==27)

)lua");
    lua_close(s);
}
'''

ALLOCATION_DRIVER = POLICY_DRIVER.replace('int main() {', r"""
struct Allocations {lua_Alloc original;void* context;std::size_t calls{};};
static void* CountAllocation(void* opaque,void* pointer,std::size_t oldSize,std::size_t newSize) {
 auto& meter=*static_cast<Allocations*>(opaque);
 if(newSize&&(!pointer||newSize>oldSize))++meter.calls;
 return meter.original(meter.context,pointer,oldSize,newSize);
}
int main() {
""").replace('lua_close(s);', r"""
    Run(s,"local m={};Isaac.AddPriorityCallback(m,1083,0,function()end,7);_perfEntity={};_perfOffset={X=1,Y=2}");
    const char* loop="for i=1,1000 do assert(Isaac.RunCallbackWithParam(1083,7,_perfEntity,_perfOffset)==_perfOffset)end";
    assert(luaL_loadstring(s,loop)==LUA_OK);lua_pushvalue(s,-1);assert(lua_pcall(s,0,0,0)==LUA_OK);
    lua_gc(s,LUA_GCSTOP,0);
    void* previous{};const auto original=lua_getallocf(s,&previous);Allocations meter{original,previous};
    lua_setallocf(s,CountAllocation,&meter);assert(lua_pcall(s,0,0,0)==LUA_OK);lua_setallocf(s,original,previous);
    std::fprintf(stderr,"render runner allocations: %zu\\n",meter.calls);assert(meter.calls==0);
    lua_close(s);
""")

RUNTIME_DRIVER = r'''

#include "lua_runtime.hpp"
#include "interfaces/lua/repentogon_environment.hpp"
#include "application/callback/extended_callback_runtime.hpp"
#include "ports/save_file_port.hpp"
#include "runtime_constants.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "interfaces/lua/callback_table_api.hpp"
#include "infrastructure/memory/engine_memory_guard.hpp"
extern "C" {
#include <lauxlib.h>
}
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
using namespace isaac::runtime;
using namespace isaac::runtime::repentogon;
struct Files final : ISaveFilePort {
    std::string value="isaac-repentogon 1\nenabled 1\n";
    Status Read(std::string_view,char* out,std::size_t cap,std::size_t* size) noexcept override {
        *size=value.size();assert(cap>=value.size());std::memcpy(out,value.data(),value.size());return Status::Ok();
    }
    Status Write(std::string_view,std::string_view) noexcept override {return Status::Ok();}
    Status Remove(std::string_view) noexcept override {return Status{StatusCode::Unsupported};}
    Status Exists(const char*,bool*) noexcept override {return Status{StatusCode::Unsupported};}
};
struct CleanupAllocator {lua_Alloc original;void* context;unsigned attempts{};};
static void* RejectCleanupAllocation(void* opaque,void* pointer,std::size_t oldSize,std::size_t newSize) {
 auto& meter=*static_cast<CleanupAllocator*>(opaque);
 if(newSize&&(!pointer||newSize>oldSize)){++meter.attempts;return nullptr;}
 return meter.original(meter.context,pointer,oldSize,newSize);
}
static bool ready=true, install=true;
static unsigned readyCalls{},installCalls{};
static bool Ready() noexcept {++readyCalls;return ready;}
static bool Install() noexcept {++installCalls;return install;}
static NativePort port{Ready,Install};
alignas(16) static unsigned char entity[0x2000]{},collider[0x2000]{},grid[0x500]{};
alignas(16) static unsigned char game[0x22000]{},room[0x8000]{},descriptor[0x100]{};
static std::vector<unsigned char> module(0xab1000);
static std::uintptr_t Address(void* p){return reinterpret_cast<std::uintptr_t>(p);}
static void Check(){if(LuaRuntime::TakeCallbackError()){char text[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(text,sizeof(text)));std::fprintf(stderr,"%s\n",text);assert(false);}}
static double Number(const char* key){double value{};assert(LuaRuntime::ReadLuaGlobalNumber(key,&value));return value;}
static int SpriteAlive(lua_State* state){lua_pushboolean(state,TryResolveSpriteArgument(state,1)!=nullptr);return 1;}
static int Reenter(lua_State* state){
    const auto epoch=EngineGuardDispatchEpoch().load();
    assert(LuaRuntime::InManagedCallbackScope()&&EngineGuardDispatchActive().load());
    Dispatch(Event{1021});
    assert(LuaRuntime::InManagedCallbackScope()&&EngineGuardDispatchActive().load()&&EngineGuardDispatchEpoch().load()==epoch);
    lua_pushboolean(state,1);return 1;
}
static void Extensions(lua_State* state) noexcept {
    lua_pushcfunction(state,SpriteAlive);lua_setglobal(state,"_spriteAlive");
    lua_pushcfunction(state,Reenter);lua_setglobal(state,"_reenter");
}
static const RepentogonCallbackBinding expected[]={
{1005,"MC_POST_ADD_COLLECTIBLE"},
    {1006,"MC_POST_ENTITY_TAKE_DMG"},
{1008,"MC_PRE_PLAYER_TAKE_DMG"},
{1069,"MC_PRE_PLAYER_TRIGGER_ROOM_CLEAR"},
{1073,"MC_PLAYER_GET_ACTIVE_MIN_USABLE_CHARGE"},
{1079,"MC_POST_PLAYERHUD_RENDER_ACTIVE_ITEM"},
{1216,"MC_PRE_COMPLETION_MARKS_RENDER"},
{1217,"MC_POST_COMPLETION_MARKS_RENDER"},
{1333,"MC_PRE_RENDER_CUSTOM_CHARACTER_MENU"},
{1271,"MC_POST_ROOM_TRANSITION_UPDATE"},
{1020,"MC_HUD_UPDATE"},
{1021,"MC_POST_HUD_UPDATE"},
{1022,"MC_HUD_RENDER"},
{1023,"MC_MAIN_MENU_RENDER"},
{1024,"MC_POST_HUD_RENDER"},
{1026,"MC_PRE_UPDATE"},
{1030,"MC_PRE_SFX_PLAY"},
{1031,"MC_POST_SFX_PLAY"},
{1060,"MC_PRE_LEVEL_INIT"},
{1061,"MC_PRE_CHANGE_ROOM"},
{1080,"MC_PRE_FAMILIAR_RENDER"},
{1081,"MC_PRE_NPC_RENDER"},
{1082,"MC_PRE_PLAYER_RENDER"},
{1083,"MC_PRE_PICKUP_RENDER"},
{1084,"MC_PRE_TEAR_RENDER"},
{1085,"MC_PRE_PROJECTILE_RENDER"},
{1086,"MC_PRE_KNIFE_RENDER"},
{1087,"MC_PRE_EFFECT_RENDER"},
{1088,"MC_PRE_BOMB_RENDER"},
{1089,"MC_PRE_SLOT_RENDER"},
{1090,"MC_POST_SLOT_RENDER"},
{1095,"MC_POST_TRIGGER_COLLECTIBLE_REMOVED"},
    {1099,"MC_POST_LEVEL_LAYOUT_GENERATED"},
    {1101,"MC_POST_GRID_ENTITY_SPAWN"},
{1102,"MC_POST_NIGHTMARE_SCENE_RENDER"},
{1104,"MC_PRE_LEVEL_SELECT"},
{1120,"MC_CONSOLE_AUTOCOMPLETE"},
{1121,"MC_POST_SLOT_INIT"},
{1122,"MC_POST_SLOT_UPDATE"},
{1133,"MC_POST_DEVIL_CALCULATE"},
    {1137,"MC_PRE_LEVEL_PLACE_ROOM"},
{1160,"MC_PRE_PLAYER_UPDATE"},
{1161,"MC_PRE_TEAR_UPDATE"},
{1162,"MC_PRE_FAMILIAR_UPDATE"},
{1163,"MC_PRE_BOMB_UPDATE"},
{1164,"MC_PRE_PICKUP_UPDATE"},
{1165,"MC_PRE_KNIFE_UPDATE"},
{1166,"MC_PRE_PROJECTILE_UPDATE"},
{1167,"MC_PRE_LASER_UPDATE"},
{1168,"MC_PRE_EFFECT_UPDATE"},
{1169,"MC_PRE_SLOT_UPDATE"},
{1200,"MC_PRE_NEW_ROOM"},
{1201,"MC_PRE_MEGA_SATAN_ENDING"},
{1210,"MC_POST_MODS_LOADED"},
{1218,"MC_PRE_PAUSE_SCREEN_RENDER"},
{1219,"MC_POST_PAUSE_SCREEN_RENDER"},
{1231,"MC_POST_PLAYER_COLLISION"},
{1233,"MC_POST_TEAR_COLLISION"},
{1235,"MC_POST_FAMILIAR_COLLISION"},
{1237,"MC_POST_BOMB_COLLISION"},
{1239,"MC_POST_PICKUP_COLLISION"},
{1270,"MC_POST_BOSS_INTRO_SHOW"},
{1280,"MC_PRE_BOSS_SELECT"},
    {1300,"MC_POST_GLOWING_HOURGLASS_SAVE"},
{1301,"MC_POST_GLOWING_HOURGLASS_LOAD"},
{1302,"MC_PRE_GLOWING_HOURGLASS_SAVE"},
{1303,"MC_PRE_GLOWING_HOURGLASS_LOAD"},
{1309,"MC_PRE_GAME_STATE_SAVE"},
{1310,"MC_POST_GAME_STATE_SAVE"},
{1311,"MC_PRE_GAME_STATE_RESTORE"},
{1312,"MC_POST_GAME_STATE_RESTORE"},
{1400,"MC_PRE_GRID_ENTITY_DECORATION_UPDATE"},
{1401,"MC_POST_GRID_ENTITY_DECORATION_UPDATE"},
{1402,"MC_PRE_GRID_ENTITY_DOOR_UPDATE"},
{1403,"MC_POST_GRID_ENTITY_DOOR_UPDATE"},
{1404,"MC_PRE_GRID_ENTITY_FIRE_UPDATE"},
{1405,"MC_POST_GRID_ENTITY_FIRE_UPDATE"},
{1406,"MC_PRE_GRID_ENTITY_GRAVITY_UPDATE"},
{1407,"MC_POST_GRID_ENTITY_GRAVITY_UPDATE"},
{1408,"MC_PRE_GRID_ENTITY_LOCK_UPDATE"},
{1409,"MC_POST_GRID_ENTITY_LOCK_UPDATE"},
{1410,"MC_PRE_GRID_ENTITY_PIT_UPDATE"},
{1411,"MC_POST_GRID_ENTITY_PIT_UPDATE"},
{1412,"MC_PRE_GRID_ENTITY_POOP_UPDATE"},
{1413,"MC_POST_GRID_ENTITY_POOP_UPDATE"},
{1414,"MC_PRE_GRID_ENTITY_PRESSUREPLATE_UPDATE"},
{1415,"MC_POST_GRID_ENTITY_PRESSUREPLATE_UPDATE"},
{1416,"MC_PRE_GRID_ENTITY_ROCK_UPDATE"},
{1417,"MC_POST_GRID_ENTITY_ROCK_UPDATE"},
{1418,"MC_PRE_GRID_ENTITY_SPIKES_UPDATE"},
{1419,"MC_POST_GRID_ENTITY_SPIKES_UPDATE"},
{1420,"MC_PRE_GRID_ENTITY_STAIRCASE_UPDATE"},
{1421,"MC_POST_GRID_ENTITY_STAIRCASE_UPDATE"},
{1422,"MC_PRE_GRID_ENTITY_STATUE_UPDATE"},
{1423,"MC_POST_GRID_ENTITY_STATUE_UPDATE"},
{1424,"MC_PRE_GRID_ENTITY_TELEPORTER_UPDATE"},
{1425,"MC_POST_GRID_ENTITY_TELEPORTER_UPDATE"},
{1426,"MC_PRE_GRID_ENTITY_TRAPDOOR_UPDATE"},
{1427,"MC_POST_GRID_ENTITY_TRAPDOOR_UPDATE"},
{1428,"MC_PRE_GRID_ENTITY_WEB_UPDATE"},
{1429,"MC_POST_GRID_ENTITY_WEB_UPDATE"},
{1430,"MC_PRE_GRID_ENTITY_TNT_UPDATE"},
{1431,"MC_POST_GRID_ENTITY_TNT_UPDATE"},
{1432,"MC_PRE_GRID_ENTITY_SPIKES_RENDER"},
{1433,"MC_POST_GRID_ENTITY_SPIKES_RENDER"},
{1434,"MC_PRE_GRID_ENTITY_WEB_RENDER"},
{1435,"MC_POST_GRID_ENTITY_WEB_RENDER"},
{1436,"MC_PRE_GRID_ENTITY_TNT_RENDER"},
{1437,"MC_POST_GRID_ENTITY_TNT_RENDER"},
{1438,"MC_PRE_GRID_ENTITY_TRAPDOOR_RENDER"},
{1439,"MC_POST_GRID_ENTITY_TRAPDOOR_RENDER"},
{1440,"MC_PRE_GRID_ENTITY_STAIRCASE_RENDER"},
{1441,"MC_POST_GRID_ENTITY_STAIRCASE_RENDER"},
{1444,"MC_PRE_GRID_ENTITY_DECORATION_RENDER"},
{1445,"MC_POST_GRID_ENTITY_DECORATION_RENDER"},
{1446,"MC_PRE_GRID_ENTITY_DOOR_RENDER"},
{1447,"MC_POST_GRID_ENTITY_DOOR_RENDER"},
{1448,"MC_PRE_GRID_ENTITY_FIRE_RENDER"},
{1449,"MC_POST_GRID_ENTITY_FIRE_RENDER"},
{1450,"MC_PRE_GRID_ENTITY_LOCK_RENDER"},
{1451,"MC_POST_GRID_ENTITY_LOCK_RENDER"},
{1452,"MC_PRE_GRID_ENTITY_TELEPORTER_RENDER"},
{1453,"MC_POST_GRID_ENTITY_TELEPORTER_RENDER"},
{1454,"MC_PRE_GRID_ENTITY_PIT_RENDER"},
{1455,"MC_POST_GRID_ENTITY_PIT_RENDER"},
{1456,"MC_PRE_GRID_ENTITY_POOP_RENDER"},
{1457,"MC_POST_GRID_ENTITY_POOP_RENDER"},
{1458,"MC_PRE_GRID_ENTITY_ROCK_RENDER"},
{1459,"MC_POST_GRID_ENTITY_ROCK_RENDER"},
{1460,"MC_PRE_GRID_ENTITY_PRESSUREPLATE_RENDER"},
{1461,"MC_POST_GRID_ENTITY_PRESSUREPLATE_RENDER"},
{1462,"MC_PRE_GRID_ENTITY_WALL_RENDER"},
{1463,"MC_POST_GRID_ENTITY_WALL_RENDER"},
{1464,"MC_MENU_INPUT_ACTION"},
{1470,"MC_POST_SAVESLOT_LOAD"},
{1103,"MC_POST_NIGHTMARE_SCENE_SHOW"},
{1255,"MC_POST_FIRE_BRIMSTONE"},
{1258,"MC_POST_FIRE_SWORD"},
{1259,"MC_POST_FIRE_TECH_LASER"},
{1260,"MC_POST_FIRE_TECH_X_LASER"},

};
int main(int argc,char** argv){
    assert(argc==2);const std::string mode=argv[1];
    if(mode=="sprite_cleanup") {
        auto* state=luaL_newstate();const auto ref=BeginCallbackSpriteScope(state);
        void* originalContext{};const auto original=lua_getallocf(state,&originalContext);
        CleanupAllocator meter{original,originalContext};lua_setallocf(state,RejectCleanupAllocation,&meter);
        EndCallbackSpriteScope(state,ref);lua_setallocf(state,original,originalContext);
        assert(meter.attempts==0);lua_close(state);return 0;
    }
    Files files;if(mode=="off")files.value="isaac-repentogon 1\nenabled 0\n";
    SetSessionSaveFilePort(&files);LuaRuntime::ObserveGameThread();LuaRuntime::SetRuntimeExtensionInstaller(Extensions);
    LuaRuntime::SetEngineModuleBase(Address(module.data()));
    SetNativePort(mode=="none"?nullptr:&port);
    ready=mode!="ready_fail";install=mode!="install_fail";
    const char* detection=(mode=="off"||mode=="none")?"assert(REPENTOGON==nil)":"assert(REPENTOGON and REPENTOGON.FullCompatibility==false)";
    std::string script=std::string(detection)+";local m=RegisterMod('callback102',1);calls=0;order=''\n";
    if(mode=="off"||mode=="none"){
        script+="assert(ModCallbacks.MC_PRE_GRID_ENTITY_DECORATION_UPDATE==nil);assert(EntityConfig==nil and MenuManager==nil and RoomTransition==nil and BlendMode==nil and StbType==nil and MainMenuType==nil and Dimension==nil)";
    }else if(mode=="catalog"){
        script+="assert(type(EntityConfig.GetEntity)=='function' and type(MenuManager.GetActiveMenu)=='function' and type(RoomTransition.GetVersusScreenSprite)=='function');assert(type(Isaac.GetGiantBookIdByName)=='function')\n";
        script+=R"lua(
local names={'SPECIAL_ROOMS','BASEMENT','CELLAR','BURNING_BASEMENT','CAVES','CATACOMBS','FLOODED_CAVES','DEPTHS','NECROPOLIS','DANK_DEPTHS','WOMB','UTERO','SCARRED_WOMB','BLUE_WOMB','SHEOL','CATHEDRAL','DARK_ROOM','CHEST'}
local menus={'TITLE','SAVES','GAME','DAILYRUN','CHARACTER','SPECIALSEEDS','CHALLENGE','COLLECTION','STATS','OPTIONS','CONTROLS','KEYCONFIG','ENDINGS','BESTIARY','MODCHALLENGES','MODS','SEED'}
for i,name in ipairs(menus) do assert(MainMenuType[name]==i, name) end
for i,name in ipairs(names) do assert(StbType[name]==i-1, name) end
assert(StbType.THE_VOID==26 and StbType.VOID==26)
for i,name in ipairs({'DOWNPOUR','DROSS','MINES','ASHPIT','MAUSOLEUM','GEHENNA','CORPSE','MORTIS','HOME','ASCENT'}) do assert(StbType[name]==i+26, name) end
local achievements={BLUE_MAP=134,STORE_UPGRADE_LV1=151,THERES_OPTIONS=135,STORE_UPGRADE_LV2=152,BLACK_CANDLE=136,STORE_UPGRADE_LV3=153,RED_CANDLE=137,STORE_UPGRADE_LV4=154,BLUE_CANDLE=59,STOP_WATCH=138,LUCKY_PENNIES=242,SPECIAL_HANGING_SHOPKEEPERS=243,WOODEN_NICKEL=244,CAIN_HOLDS_PAPERCLIP=245,EVERYTHING_IS_TERRIBLE_2=246,SPECIAL_SHOPKEEPERS=247,EVE_HOLDS_RAZOR_BLADE=248,GREEDIER=341,STORE_KEY=249,LOST_HOLDS_HOLY_MANTLE=250,GENEROSITY=275,KEEPER=251}
for name,value in pairs(achievements) do assert(Achievement[name]==value, name) end
assert(EventCounter.DONATION_MACHINE_COUNTER==20 and EventCounter.GREED_DONATION_MACHINE_COUNTER==115)
assert(Dimension.CURRENT==-1 and Dimension.NORMAL==0)
assert(Dimension.KNIFE_PUZZLE==1 and Dimension.MIRROR==1 and Dimension.MINESHAFT==1 and Dimension.DEATH_CERTIFICATE==2)
)lua";
        for(const auto& c:expected)script+="assert(ModCallbacks."+std::string(c.name)+"=="+std::to_string(c.id)+");m:AddCallback("+std::to_string(c.id)+",function()calls=calls+1 end)\n";
    }else if(mode=="reverie"){
        script+=R"lua(
m:AddCallback(1069,function(_,p)assert(p);return false end,7)
m:AddCallback(1069,function()error('wrong room-clear filter')end,8)
m:AddCallback(1073,function(_,slot,p,normal)assert(slot==1 and p and normal==6);return -5 end,123)
m:AddCallback(1073,function()error('wrong active-item filter')end,124)
m:AddCallback(1079,function(_,p,slot,pos,alpha,size,charge)
 assert(p and slot==1 and pos.X==10 and pos.Y==20 and alpha==0.5 and size==0.25 and charge.X==9 and charge.Y==8)
 calls=calls+1
end,123)
)lua";
    }else if(mode=="render"){
        script+=R"lua(
m:AddPriorityCallback(1080,-1,function(_,e,v)assert(e and v.X==10 and v.Y==20);order=order..'A';return Vector(2,3)end,7)
m:AddPriorityCallback(1080,1,function(_,e,v)assert(v.X==12 and v.Y==23);order=order..'B';return Vector(-1,4)end,7)
m:AddCallback(1080,function()error('wrong variant')end,99)
)lua";
    }else if(mode=="booleans"){
        script+=R"lua(
m:AddCallback(1400,function()return false end,4)
m:AddCallback(1402,function()return true end,4)
m:AddCallback(1404,function()return nil end,4)
m:AddCallback(1160,function()return false end,7)
m:AddCallback(1161,function()return true end,7)
m:AddCallback(1162,function()return nil end,7)
m:AddCallback(1080,function()return false end,7)
m:AddCallback(1081,function()return true end,20)
m:AddCallback(1218,function()return false end)
m:AddCallback(1121,function()return true end,7)
)lua";
    }else if(mode=="filter"){
        script+=R"lua(
for _,id in ipairs({1081,1082,1086,1160,1165,1231,1233,1235,1237,1239,1444,1445})do
 local wanted=7;if id==1081 then wanted=20 elseif id==1165 then wanted=9 elseif id>=1400 then wanted=4 end
 m:AddCallback(id,function(_,a,b,low)
  assert(a);if id>=1231 and id<=1239 then assert(b and low==true) end
  if id==1444 then assert(b.X==10);return Vector(4,5) end
  if id==1445 then assert(b==nil) end
  calls=calls+1
 end,wanted)
 m:AddCallback(id,function()error('wrong filter '..id)end,999)
end
)lua";
    }else if(mode=="post_fire"){
        script+=R"lua(
m:AddCallback(1103,function(_,value)assert(type(value)=='boolean' and value);calls=calls+1 end)
for _,id in ipairs({1255,1258,1259,1260})do
 m:AddCallback(id,function(_,...)assert(select('#',...)==1);local entity=...;assert(type(entity)=='userdata');calls=calls+1;return false end)
end
m:AddCallback(1259,function()error('post-fire has no variant filter')end,7)
)lua";
    }else if(mode=="sound"){
        script+=R"lua(
m:AddCallback(1030,function(_,id,volume,delay,loop,pitch,pan)
 assert(id==5 and volume==0.5 and delay==2 and loop==false and pitch==1 and pan==0)
 calls=calls+1;return {8,0.25,3,true,1.5,-0.5}
end,5)
m:AddCallback(1030,function()error('must stop at returned table')end,5)
m:AddCallback(1031,function(_,id,volume,delay,loop,pitch,pan)
 assert(id==8 and volume==0.25 and delay==3 and loop==true and pitch==1.5 and pan==-0.5);calls=calls+1;return false
end,8)
)lua";
    }else if(mode=="sound_error"){
        script+=R"lua(
m:AddCallback(1030,function()return {9,0.25,4,'bad loop',1.5,0}end,5)
)lua";
    }else if(mode=="level_boss"){
        script+=R"lua(
m:AddCallback(1060,function(...)
    assert(select('#',...) == 1)
    calls=calls+1
    return true
end)
m:AddCallback(1270,function(...)
    assert(select('#',...) == 3)
    local _, boss1, boss2 = ...
    assert(boss1 == 55 and boss2 == -1)
    calls=calls+1
    return false
end)
)lua";
    }else if(mode=="remaining_phases"){
        script+=R"lua(
m:AddCallback(1133,function(_,chance)
 assert(chance==0.375 or chance==0.5);calls=calls+1
 if chance==0.375 then return '0.75' end
end)
m:AddCallback(1201,function(...)assert(select('#',...)==1);calls=calls+1;return true end)
m:AddCallback(1099,function(_,g)assert(#g:GetAllRooms()==0);calls=calls+1 end)
m:AddCallback(1137,function(_,slot,cfg,seed)
 assert(slot:Shape()==0 and type(cfg)=='userdata' and seed==-1)
 calls=calls+1;return cfg
end)
m:AddCallback(1280,function(_,boss,pool,stage,stageType)
 assert(boss==12 and pool:GetWeight()==0 and stage==7 and stageType==1)
 calls=calls+1;return 38
end,12)
m:AddCallback(1280,function()error('wrong boss filter')end,3)
m:AddCallback(1095,function(_,player,item,removeForm,wispOrInnate)
 assert(player and item==42 and removeForm==false and wispOrInnate==true)
 calls=calls+1
end,42)
m:AddCallback(1095,function()error('wrong removed collectible filter')end,99)
)lua";
    }else if(mode=="bulk_callbacks"){
        script+=R"lua(
m:AddCallback(1061,function(_,target,dimension)
 assert(target==5 and dimension==0)
 calls=calls+1
 return {'42',1.0}
end)
m:AddCallback(1200,function(_,roomValue,descriptorValue)
 assert(type(roomValue)=='userdata' and type(descriptorValue)=='userdata')
 assert(descriptorValue:GetDimension()==1)
 assert(descriptorValue:GetTaintedKeeperCoinSpawns()==10)
 calls=calls+1
end)
m:AddCallback(1102,function(...)
 assert(select('#',...) == 1)
 calls=calls+1
end)
)lua";
    }else if(mode=="change_room_invalid"){
        script+=R"lua(
m:AddCallback(1061,function(_,target,dimension)
 assert(target==5 and dimension==0)
 calls=calls+1
 return {42}
end)
)lua";
    }else if(mode=="change_room_non_integer"){
        script+=R"lua(
m:AddCallback(1061,function(_,target,dimension)
 assert(target==5 and dimension==0)
 calls=calls+1
 return {42.5,1}
end)
)lua";
    }else if(mode=="nested"){
        script+=R"lua(
local once=true;local removed
removed=function()error('removed callback ran')end
m:AddPriorityCallback(1020,-1,function()
 order=order..'A';m:RemoveCallback(1020,removed)
 assert(_reenter());assert(Isaac.GetBuiltInCallbackState(1020));order=order..'C'
end)
m:AddCallback(1020,removed)
m:AddCallback(1021,function()order=order..'B';return nil end)
)lua";
    }else if(mode=="error"){
        script+=R"lua(
m:AddCallback(1020,function()Isaac.RunCallback(1021)end)
local n=RegisterMod('nested-error-owner',1)
n:AddCallback(1021,function()error('owned nested RGON error')end)
)lua";
    }else if(mode=="pause"||mode=="pause_error"){
        script+=R"lua(
m:AddCallback(1218,function(_,main,stats)
 assert(main and stats and _spriteAlive(main) and _spriteAlive(stats));savedMain=main;savedStats=stats
 if FAIL_PAUSE then error('pause scope error') end
 return false
end)
m:AddCallback(1020,function()
 assert(not _spriteAlive(savedMain) and not _spriteAlive(savedStats));savedMain=nil;savedStats=nil
 collectgarbage('collect');calls=calls+1
end)
)lua";
        const auto marker=script.find("FAIL_PAUSE");script.replace(marker,10,mode=="pause_error"?"true":"false");
    }else if(mode=="remove_all"){
        script+=R"lua(
local f;f=function()m:RemoveCallback(1400,f);calls=calls+1 end;m:AddCallback(1400,f,4)
)lua";
    }else if(mode=="reset"){
        script+="m:AddCallback(1400,function()end,4);Isaac.SetBuiltInCallbackState(1400,true)";
    }else if(mode=="bad_vector"){
        script+="m:AddCallback(1444,function()return RNG()end,4)";
    }else if(mode=="empty"){
        script+="assert(not Isaac.GetBuiltInCallbackState(1400))";
    }
    const auto init=LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@callback102.lua");
    if(mode=="ready_fail"||mode=="install_fail"){
        assert(init!=LuaRuntime::LuaInitResult::Success);assert(!Listening(1020));
        assert(readyCalls==1&&installCalls==(mode=="ready_fail"?0:1));return 0;
    }
    if(init!=LuaRuntime::LuaInitResult::Success){char text[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(text,sizeof(text)));std::fprintf(stderr,"%s\n",text);assert(false);}
    if(mode=="off"||mode=="none"){
        assert(!Listening(1400));assert(installCalls==0&&readyCalls==0);assert(ExtendedCallbackCount()==0);
    }else{
        assert(installCalls==1&&readyCalls==1&&ExtendedCallbackCount()==140);
        unsigned type=20,variant=7,subtype=9,gridType=4;
        std::memcpy(entity+kEntityTypeOffset,&type,4);std::memcpy(entity+kEntityVariantOffset,&variant,4);
        std::memcpy(entity+kEntitySubTypeOffset,&subtype,4);std::memcpy(grid+kGridEntityTypeOffset,&gridType,4);
        Vector offset{10,20};Sound sound{5,0.5f,2,false,1,0};
        auto send=[&](unsigned id,EventKind kind=EventKind::Global){return Dispatch(Event{id,kind,kind==EventKind::Grid||kind==EventKind::GridRender?Address(grid):Address(entity),Address(collider),&offset,true,&sound});};
        if(mode=="catalog"){
            assert(sizeof(expected)/sizeof(expected[0])==140);
            for(const auto& c:expected){assert(Listening(c.id));send(c.id);}
            Check();assert(Number("calls")==140&&g_ExtendedCallbackEnabledCount==140);
        }else if(mode=="reverie"){
            const auto clear=send(1069,EventKind::Entity);Check();assert(clear.hasBoolean&&!clear.boolean);
            Event charge{};charge.id=1073;charge.kind=EventKind::PlayerActiveMinUsableCharge;
            charge.object=Address(entity);charge.first=1;charge.second=6;charge.third=123;
            const auto value=Dispatch(charge);Check();assert(value.hasInteger&&value.integer==-5);
            Vector chargePos{9,8};Event hud{};hud.id=1079;hud.kind=EventKind::PlayerHudActive;
            hud.object=Address(entity);hud.first=1;hud.second=123;hud.offset=&offset;
            hud.number=0.5F;hud.scale=0.25F;hud.chargeBar=&chargePos;
            static_cast<void>(Dispatch(hud));Check();assert(Number("calls")==1);
        }else if(mode=="render"){
            auto result=send(1080,EventKind::EntityRender);Check();assert(result.hasOffset&&result.offset.x==11&&result.offset.y==27);
        }else if(mode=="booleans"){
            auto r=send(1400,EventKind::Grid);assert(r.hasBoolean&&!r.boolean);
            r=send(1402,EventKind::Grid);assert(r.hasBoolean&&r.boolean);
            r=send(1404,EventKind::Grid);assert(!r.hasBoolean);
            r=send(1160,EventKind::Entity);assert(r.hasBoolean&&!r.boolean);
            r=send(1161,EventKind::Entity);assert(r.hasBoolean&&r.boolean);
            r=send(1162,EventKind::Entity);assert(!r.hasBoolean);
            r=send(1080,EventKind::EntityRender);assert(r.hasBoolean&&!r.boolean);
            r=send(1081,EventKind::EntityRender);assert(!r.hasBoolean&&r.hasOffset);
            r=send(1218);assert(r.hasBoolean&&!r.boolean);
            r=send(1121,EventKind::Entity);assert(!r.hasBoolean&&!r.hasOffset);Check();
        }else if(mode=="filter"){
            for(unsigned id:{1081,1082,1086,1160,1165})send(id,id<1100?EventKind::EntityRender:EventKind::Entity);
            for(unsigned id:{1231,1233,1235,1237,1239})send(id,EventKind::Collision);
            auto r=send(1444,EventKind::GridRender);assert(r.hasOffset&&r.offset.x==4&&r.offset.y==5);
            send(1445,EventKind::GridRender);Check();assert(Number("calls")==11);
        }else if(mode=="post_fire"){
            send(1103,EventKind::Boolean);Check();
            for(auto id:{1255,1258,1259,1260})send(id,EventKind::FiredEntity);
            Check();assert(Number("calls")==5);
        }else if(mode=="sound"){
            send(1030,EventKind::Sound);Check();assert(sound.id==8&&sound.loop&&sound.pan==-0.5f);
            send(1031,EventKind::Sound);Check();assert(Number("calls")==2);
        }else if(mode=="sound_error"){
            send(1030,EventKind::Sound);assert(LuaRuntime::TakeCallbackError());
            assert(sound.id==5&&sound.volume==0.5f&&sound.delay==2&&!sound.loop&&sound.pitch==1&&sound.pan==0);
            LuaRuntime::LuaErrorHistoryEntryView errors[8]{};
            const auto n=LuaRuntime::CopyLuaErrorHistory(errors,8);assert(n==1&&errors[0].owner!=0&&errors[0].callbackId==1030);
        }else if(mode=="level_boss"){
            auto result=Dispatch(Event{1060});
            assert(!result.hasBoolean&&!result.hasOffset);
            Event boss{};
            boss.id=1270;boss.kind=EventKind::IntegerPair;boss.first=55;boss.second=-1;
            result=Dispatch(boss);
            assert(!result.hasBoolean&&!result.hasOffset);
            Check();assert(Number("calls")==2);
        }else if(mode=="remaining_phases"){
            Event event{};event.id=1133;event.kind=EventKind::Number;event.number=.375f;
            auto result=Dispatch(event);Check();assert(result.hasNumber&&result.number==.75f);
            event.number=.5f;result=Dispatch(event);Check();assert(result.hasNumber&&result.number==0);
            result=Dispatch({1201});Check();assert(result.hasBoolean&&result.boolean);
            event={};event.id=1099;event.kind=EventKind::LevelGenerator;event.object=Address(room);
            Dispatch(event);Check();
            event={};event.id=1137;event.kind=EventKind::LevelGeneratorRoom;
            event.object=Address(room);event.collider=Address(collider);event.first=-1;
            result=Dispatch(event);Check();assert(result.hasObject&&result.object==Address(collider));
            event={};event.id=1280;event.kind=EventKind::BossPool;event.object=Address(room);
            event.first=12;event.second=7;event.third=1;
            result=Dispatch(event);Check();assert(result.hasIntegerPair&&result.first==38);
            event={};event.id=1095;event.kind=EventKind::CollectibleRemoved;
            event.object=Address(entity);event.first=42;event.low=false;event.second=1;
            Dispatch(event);Check();assert(Number("calls")==7);
        }else if(mode=="bulk_callbacks"){
            static std::uintptr_t gameOwner{};
            gameOwner=Address(game);
            LuaRuntime::SetGameBindings(Address(&gameOwner),0x2222);
            const auto gameAddress=Address(game);
            std::memcpy(game,&gameAddress,sizeof(gameAddress));
            const auto roomAddress=Address(room);
            std::memcpy(game+kGameRoomPointerOffset,&roomAddress,sizeof(roomAddress));
            const std::int32_t gridIndex=77;
            std::memcpy(descriptor,&gridIndex,sizeof(gridIndex));
            const std::int32_t dimension=1;
            std::memcpy(descriptor+0x0C,&dimension,sizeof(dimension));
            const std::int16_t coins=10;
            std::memcpy(descriptor+0x5E,&coins,sizeof(coins));
            Event change{};
            change.id=1061;change.kind=EventKind::IntegerPair;change.first=5;change.second=0;
            auto result=Dispatch(change);
            assert(result.hasIntegerPair&&result.first==42&&result.second==1);
            Event roomInit{};
            roomInit.id=1200;roomInit.kind=EventKind::RoomDescriptor;
            roomInit.object=Address(room);roomInit.collider=Address(descriptor);
            auto wrongRoom=roomInit;
            wrongRoom.object=Address(entity);
            result=Dispatch(wrongRoom);
            Check();assert(Number("calls")==1);
            result=Dispatch(roomInit);
            assert(!result.hasBoolean&&!result.hasOffset&&!result.hasIntegerPair);
            result=send(1102);
            assert(!result.hasBoolean&&!result.hasOffset&&!result.hasIntegerPair);
            Check();assert(Number("calls")==3);
        }else if(mode=="change_room_invalid"){
            Event change{};
            change.id=1061;change.kind=EventKind::IntegerPair;change.first=5;change.second=0;
            const auto result=Dispatch(change);
            assert(!result.hasIntegerPair);
            Check();assert(Number("calls")==1);
        }else if(mode=="change_room_non_integer"){
            Event change{};
            change.id=1061;change.kind=EventKind::IntegerPair;change.first=5;change.second=0;
            const auto result=Dispatch(change);
            assert(!result.hasIntegerPair&&LuaRuntime::TakeCallbackError());
            char text[2048]{};
            static_cast<void>(LuaRuntime::CopyLastLuaErrorText(text,sizeof(text)));
            assert(std::strstr(text,"number has no integer representation"));
            LuaRuntime::LuaErrorHistoryEntryView errors[8]{};
            const auto n=LuaRuntime::CopyLuaErrorHistory(errors,8);
            assert(n==1&&errors[0].owner!=0&&errors[0].callbackId==1061);
        }else if(mode=="nested"){
            send(1020);Check();
        }else if(mode=="error"){
            send(1020);assert(LuaRuntime::TakeCallbackError());char text[2048]{};
            static_cast<void>(LuaRuntime::CopyLastLuaErrorText(text,sizeof(text)));
            assert(std::strstr(text,"owned nested RGON error"));
            LuaRuntime::LuaErrorHistoryEntryView errors[8]{};
            const auto n=LuaRuntime::CopyLuaErrorHistory(errors,8);assert(n==1&&errors[0].owner!=0&&errors[0].callbackId==1021);
        }else if(mode=="pause"||mode=="pause_error"){
            auto r=send(1218);assert(mode=="pause_error"?!r.hasBoolean:(r.hasBoolean&&!r.boolean));
            assert(LuaRuntime::TakeCallbackError()==(mode=="pause_error"));send(1020);Check();assert(Number("calls")==1);
        }else if(mode=="bad_vector"){
            auto r=send(1444,EventKind::GridRender);assert(!r.hasBoolean&&!r.hasOffset&&LuaRuntime::TakeCallbackError());
            LuaRuntime::LuaErrorHistoryEntryView errors[8]{};
            const auto n=LuaRuntime::CopyLuaErrorHistory(errors,8);assert(n==1&&errors[0].owner!=0&&errors[0].callbackId==1444);
        }else if(mode=="remove_all"||mode=="reset"){
            assert(g_ExtendedCallbackEnabledCount==1);
            if(mode=="remove_all"){send(1400,EventKind::Grid);Check();assert(Number("calls")==1);}
            else ResetCallbackRuntimeState();
            assert(!Listening(1400)&&g_ExtendedCallbackEnabledCount==0);
            Dispatch(Event{1400,EventKind::Grid,1});Check();
        }else if(mode=="empty"){
            Event boss{};
            boss.id=1270;boss.kind=EventKind::IntegerPair;boss.first=55;boss.second=-1;
            for(unsigned i=0;i<10000;++i){
                assert(!Listening(1444));assert(!Listening(1060));assert(!Listening(1270));
                Dispatch(Event{1444,EventKind::GridRender,1,1,reinterpret_cast<Vector*>(1),true,reinterpret_cast<Sound*>(1)});
                Dispatch(Event{1060});
                Dispatch(boss);
            }
            assert(ExtendedCallbackDispatchCount(1444)==0);
            assert(ExtendedCallbackDispatchCount(1060)==0);
            assert(ExtendedCallbackDispatchCount(1270)==0);
            assert(g_ExtendedCallbackEnabledCount==0);Check();
        }
    }
    assert(LuaRuntime::ShutdownForModReload());assert(!Listening(1400)&&g_ExtendedCallbackEnabledCount==0&&ExtendedCallbackCount()==0);
    assert(LuaRuntime::InitializeFromBuffer(detection,std::strlen(detection),"@reload.lua")==LuaRuntime::LuaInitResult::Success);
    assert(LuaRuntime::ShutdownForModReload());SetNativePort(nullptr);SetSessionSaveFilePort(nullptr);
    LuaRuntime::SetGameBindings(0,0);LuaRuntime::SetEngineModuleBase(0);
}
'''

class RepentogonCallbackTests(unittest.TestCase):
    def test_reverie_callback_exports(self):
        source = (SOURCE.parent / 'src/interfaces/lua/repentogon_callbacks.cpp').read_text()
        for name in ('MC_PRE_PLAYER_TRIGGER_ROOM_CLEAR', 'MC_PLAYER_GET_ACTIVE_MIN_USABLE_CHARGE', 'MC_POST_PLAYERHUD_RENDER_ACTIVE_ITEM'):
            self.assertTrue(name in source, name)

    def _run_policy_driver(self, driver_text):
        with tempfile.TemporaryDirectory(prefix='repentogon-policy-') as tmp:
            work=test_support.prepare_harness_directory(Path(tmp))
            driver=work/'policy.cpp';driver.write_text(driver_text)
            lua_root=SOURCE/test_support.LUA_SOURCE_RELATIVE
            binary=work/'policy'
            build=subprocess.run(['c++','-std=c++17','-I'+str(SOURCE),'-I'+str(lua_root),str(driver),
                *(str(p) for p in test_support.lua_harness_objects(SOURCE,work)),'-lm','-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stdout+build.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_active_min_charge_chains_third_argument(self):
        driver = POLICY_DRIVER.replace('local outer=Isaac.RunCallbackWithParam', """local chargeMod={};local order=0
Isaac.AddPriorityCallback(chargeMod,1073,0,function(_,slot,p,current)
 assert(slot==1 and p and current==6);order=order+1;return -5
end,123)
Isaac.AddPriorityCallback(chargeMod,1073,1,function(_,slot,p,current)
 assert(current==-5);order=order+1;return 'pass-through'
end,123)
Isaac.AddPriorityCallback(chargeMod,1073,2,function(_,slot,p,current)
 assert(current=='pass-through');order=order+1;return 3
end,123)
assert(Isaac.RunCallbackWithParam(1073,123,1,{},6)==3 and order==3)
local outer=Isaac.RunCallbackWithParam""")
        self._run_policy_driver(driver)

    def test_pre_render_runner_accumulates_offsets(self):
        self._run_policy_driver(POLICY_DRIVER)

    def test_pre_render_runner_reuses_functions_without_allocating(self):
        self._run_policy_driver(ALLOCATION_DRIVER)

    def test_native_catalog_delivery_and_lifecycle(self):
        with tempfile.TemporaryDirectory(prefix='repentogon-native-') as tmp:
            binary=test_support.build_lua_harness(source_root=SOURCE,workdir=Path(tmp),harness_source=RUNTIME_DRIVER)
            for mode in ('sprite_cleanup','off','none','ready_fail','install_fail','catalog','reverie','render','booleans','filter','post_fire','sound','sound_error','level_boss','bulk_callbacks','remaining_phases','change_room_invalid','change_room_non_integer','nested','error','pause','pause_error','bad_vector','remove_all','reset','empty'):
                with self.subTest(mode=mode):
                    result=subprocess.run([str(binary),mode],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_ordinary_ids_do_not_read_extended_storage(self):
        driver=r'''
#include "application/callback/extended_callback_runtime.hpp"
#include <cassert>
using namespace isaac::runtime;
int main(){
 g_ExtendedCallbacks=reinterpret_cast<ExtendedCallbackState*>(1);g_ExtendedCallbackCount=110;
 for(unsigned id=0;id<1000;++id)assert(FindExtendedCallback(id)==nullptr);
 g_ExtendedCallbackDelivery=false;g_ExtendedCallbackEnabledCount=100;
 assert(!ExtendedCallbackEnabled(1400));
 g_ExtendedCallbackDelivery=true;g_ExtendedCallbackEnabledCount=0;
 assert(!ExtendedCallbackEnabled(1400));
}
'''
        with tempfile.TemporaryDirectory(prefix='repentogon-fast-gate-') as tmp:
            tmp=Path(tmp);source=tmp/'gate.cpp';source.write_text(driver);binary=tmp/'gate'
            build=subprocess.run(['c++','-std=c++17','-I'+str(SOURCE.parent/'src'),str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stdout+build.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
