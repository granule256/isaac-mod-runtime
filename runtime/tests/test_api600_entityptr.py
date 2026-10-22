"""EntityPtr真实Lua公共构造/读取/方法、nil、只读、销毁与同址复用。"""
import unittest
from .test_api400_params import run_main
MAIN=r'''
#include "interfaces/lua/api600_entityptr.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "lua_object_handles.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
const char*script=R"lua(
local function same(a,b)return a~=nil and b~=nil and GetPtrHash(a)==GetPtrHash(b)end
assert(type(EntityPtr)=='table');local p=Isaac.GetPlayer();local npc=Isaac.FindByType(20)[1];local ptr=EntityPtr(p)
assert(type(ptr)=='userdata','ptr type');assert(ptr.Ref~=nil,'ptr nil');assert(same(ptr.Ref,p),'ptr identity');assert(same(ptr.Ref:ToPlayer(),p),'ptr player cast')
assert(getmetatable(ptr).__type=='EntityPtr' and getmetatable(ptr).__class==getmetatable(EntityPtr).__class)
assert(select('#',ptr:SetReference(npc))==0 and same(ptr.Ref,npc))
assert(ptr.Ref:ToNPC().Type==20);ptr:SetReference(nil);assert(ptr.Ref==nil)
local empty=EntityPtr(nil);assert(empty.Ref==nil);empty:SetReference(p);assert(same(empty.Ref,p))
ptr.SetReference(ptr,npc);assert(same(ptr.Ref,npc))
assert(not pcall(function()ptr.Ref=p end));assert(not pcall(function()ptr.Ref=nil end));assert(not pcall(function()ptr.Unknown=1 end));assert(ptr.Unknown==nil)
assert(not pcall(function()EntityPtr()end));assert(not pcall(function()ptr:SetReference()end))
for _,wrong in ipairs({false,true,3,'bad',{},Vector(1,2),Color(1,1,1,1),EntityRef(p)})do
 assert(not pcall(function()EntityPtr(wrong)end));assert(not pcall(function()ptr:SetReference(wrong)end))
end
assert(not pcall(function()ptr.SetReference({},p)end))
ptr:SetReference(p);assert(same(ptr.Ref,p));collectgarbage('collect');assert(same(ptr.Ref,p))
)lua";
if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@api600-entityptr.lua")!=LuaRuntime::LuaInitResult::Success){LuaRuntime::LuaErrorHistoryEntryView errors[8]{};auto count=LuaRuntime::CopyLuaErrorHistory(errors,8);for(std::size_t i=0;i<count;++i)std::fprintf(stderr,"%s\n",errors[i].text);return 1;}
auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));PushEntityCallbackArgument(L,AddressOf(g_Entities[kPlayer]));lua_setglobal(L,"player");
if(luaL_dostring(L,"function same(a,b)return a~=nil and b~=nil and GetPtrHash(a)==GetPtrHash(b)end;a=EntityPtr(player);b=EntityPtr(player);assert(same(a.Ref,player) and same(b.Ref,player))")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 2;}
RetireEntityLifetime(AddressOf(g_Entities[kPlayer]));
if(luaL_dostring(L,"assert(a.Ref==nil and b.Ref==nil);c=EntityPtr(player);assert(c.Ref==nil);b:SetReference(player);assert(b.Ref==nil)")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 3;}
// The bytes and address are intentionally reused, so only token identity can distinguish generations.
PushEntityCallbackArgument(L,AddressOf(g_Entities[kPlayer]));lua_setglobal(L,"newPlayer");
if(luaL_dostring(L,"assert(a.Ref==nil);fresh=EntityPtr(newPlayer);assert(same(fresh.Ref,newPlayer));a:SetReference(newPlayer);assert(same(a.Ref,newPlayer) and b.Ref==nil);fresh:SetReference(player);assert(fresh.Ref==nil);fresh:SetReference(newPlayer);assert(same(fresh.Ref,newPlayer))")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 4;}
std::vector<unsigned char>other=g_ModuleBytes;const auto otherBase=AddressOf(other);WriteWord(g_Entities[kPlayer],0,otherBase+kEntityPlayerVtableOffset);LuaRuntime::SetEngineModuleBase(otherBase);
if(luaL_dostring(L,"assert(a.Ref==nil and fresh.Ref==nil);a:SetReference(nil);assert(a.Ref==nil)")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 5;}
lua_close(L);return 0;}
'''
class EntityPtrConsumer(unittest.TestCase):
 def test_public_entityptr(self):
  r=run_main(MAIN);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
