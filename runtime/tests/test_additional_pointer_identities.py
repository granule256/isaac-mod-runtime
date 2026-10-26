"""GetPtrHash额外类型：原生借用别名/自有值存储/拥有者失效，保持原实体快路径。"""
from pathlib import Path
from unittest import mock
import unittest
from . import test_object_pointer_identity as original

SETUP=r'''
 std::vector<unsigned char> grid(0x500);WriteWord(grid,0,g_EngineBase+kGridEntity_RockVtableOffset);
 auto pushGrid=[&](const char*name){auto*h=static_cast<LuaRuntime::GridEntityHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::GridEntityHandle)));h->entity=grid.data();luaL_getmetatable(L,LuaRuntime::kGridEntityMetatable);lua_setmetatable(L,-2);lua_setglobal(L,name);};
 pushGrid("gridA");pushGrid("gridB");lua_pushinteger(L,static_cast<lua_Integer>(AddressOf(grid)));lua_setglobal(L,"gridAddress");
 PushBorrowedGameFont(L,AddressOf(g_GameBytes),0x24f9c8);lua_setglobal(L,"fontA");PushBorrowedGameFont(L,AddressOf(g_GameBytes),0x24f9c8);lua_setglobal(L,"fontB");
 lua_pushinteger(L,static_cast<lua_Integer>(AddressOf(g_GameBytes)+0x24f9c8));lua_setglobal(L,"fontAddress");
 Run(L,R"lua(
 assert(GetPtrHash(gridA)==gridAddress and GetPtrHash(gridB)==gridAddress,'Grid native identity missing')
 assert(GetPtrHash(fontA)==fontAddress and GetPtrHash(fontB)==fontAddress,'Font native identity missing')
 vecA=Vector(3,4);vecB=Vector(3,4);colorA=Color(1,1,1,1);colorB=Color(1,1,1,1)
 refValueA=EntityRef(player);refValueB=EntityRef(player);bitsA=BitSet128(1,2);bitsB=BitSet128(1,2)
 for _,pair in ipairs({{vecA,vecB},{colorA,colorB},{refValueA,refValueB},{bitsA,bitsB}})do
  assert(GetPtrHash(pair[1])~=0 and GetPtrHash(pair[1])~=GetPtrHash(pair[2]),'distinct native values collide')
  local hash=GetPtrHash(pair[1]);for i=1,8 do assert(GetPtrHash(pair[1])==hash,'value identity changed')end
 end
 )lua");
 WriteWord(grid,0,0);Run(L,"assert(GetPtrHash(gridA)==0 and GetPtrHash(gridB)==0)");
'''
class AdditionalPointerIdentities(unittest.TestCase):
 def test_grid_font_and_native_owned_values(self):
  main=original.MAIN.replace('#include "lua_object_handles.hpp"','#include "lua_object_handles.hpp"\n#include "interfaces/lua/font_api.hpp"')
  self.assertIn('g_GameBytes.resize(0x350000)',main)
  needle=' Run(L,R"lua('
  self.assertIn(needle,main);main=main.replace(needle,SETUP+needle,1)
  main=main.replace('assert(GetPtrHash(Game())==0 and GetPtrHash(Game():GetRoom())==0)','assert(GetPtrHash(Game())==0 and GetPtrHash(Game():GetRoom())==0 and GetPtrHash(fontA)==0 and GetPtrHash(fontB)==0)')
  with mock.patch.object(original,'MAIN',main):
   original.ObjectPointerIdentityTests.test_real_object_aliases_distinct_objects_and_lifetime(self)
