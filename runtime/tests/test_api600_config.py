"""第六批配置容器与两项静态判定，真实公共Lua链。"""
import unittest
from .test_api400_params import run_main
MAIN=r'''
#include "lua_object_handles.hpp"
#include "interfaces/lua/api500_config.guards.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
using namespace isaac::runtime;
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
std::vector<unsigned char> manager(kManagerItemConfigOffset+0x100),slot(8),item(0x200),card(0x80),pill(0x80),nullitem(0x200),items(16),cards(16),pills(16),nulls(16);
WriteWord(slot,0,AddressOf(manager));WriteWord(g_ModuleBytes,kGameManagerGlobalSlotOffset,AddressOf(slot));
auto publish=[&](auto&v,auto&o,std::size_t off){WriteWord(v,8,AddressOf(o));WriteWord(manager,kManagerItemConfigOffset+off,AddressOf(v));WriteWord(manager,kManagerItemConfigOffset+off+8,AddressOf(v)+16);};
publish(items,item,0);publish(cards,card,0x48);publish(pills,pill,0x60);publish(nulls,nullitem,0x30);
WriteAt<std::int32_t>(item,0,1);WriteAt<std::int32_t>(item,4,1);WriteAt<std::int32_t>(card,0,1);WriteAt<std::int32_t>(pill,0,1);WriteAt<std::int32_t>(nullitem,0,0);WriteAt<std::int32_t>(nullitem,4,1);item[0xb6]=1;
for(const auto&g:api500_config::kGuards)std::memcpy(g_ModuleBytes.data()+g.offset,g.bytes.data(),16);
const char*script=R"lua(
local c=Isaac.GetItemConfig();local cards=c:GetCards();local pills=c:GetPillEffects();local nulls=c:GetNullItems()
assert(type(cards)=="userdata" and type(pills)=="userdata" and type(nulls)=="userdata")
assert(cards.Size==2 and #cards==2 and pills.Size==2 and #pills==2 and nulls.Size==2)
assert(cards:Get(0)==nil and pills:Get(0)==nil and nulls:Get(0)==nil)
assert(cards:Get(1).ID==1 and pills:Get(1).ID==1 and nulls:Get(1):IsNull())
assert(not c:GetCollectible(1):IsNull())
assert(ItemConfig.ShouldAddCostumeOnPickup(c:GetCollectible(1)))
assert(not ItemConfig.ShouldAddCostumeOnPickup(nil))
local item=c:GetCollectible(1);local mt=getmetatable(item);local oldIndex=mt.__index
mt.__index=function(self,key)if key=='AddCostumeOnPickup'then return false end return oldIndex(self,key)end
assert(item.AddCostumeOnPickup==false)
assert(ItemConfig.ShouldAddCostumeOnPickup(item)==true,'static native predicate must not consult a modded Lua property getter')
mt.__index=oldIndex
for _,v in ipairs({cards,pills})do assert(getmetatable(v).__len(v)==#v); assert(not pcall(function()v:Get(-1)end));assert(not pcall(function()v:Get(2)end));assert(not pcall(function()v:Get(1.5)end));assert(not pcall(function()v.Size=3 end))end
assert(getmetatable(cards).__type=='CardConfigList' and getmetatable(pills).__type=='PillConfigList')
assert(getmetatable(CppContainer.Vector.CardConfigList).__class==getmetatable(cards).__class)
assert(getmetatable(cards).__class~=getmetatable(pills).__class)
heldCards=cards;heldPills=pills
)lua";
if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@api600-config.lua")!=LuaRuntime::LuaInitResult::Success){LuaRuntime::LuaErrorHistoryEntryView e[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(e,8);for(std::size_t i=0;i<n;++i)std::fprintf(stderr,"%s\n",e[i].text);return 1;}return 0;}
'''
class ConfigConsumer(unittest.TestCase):
 def test_config_containers(self):
  r=run_main(MAIN);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
