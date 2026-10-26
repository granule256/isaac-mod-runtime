"""枚举/原生32B描述符自有存储与Game内嵌借用对象的身份。"""
from unittest import mock
import unittest
from . import test_object_pointer_identity as original
PREFIX=r'''
#include "interfaces/lua/opaque_scalar_value.hpp"
#include "interfaces/lua/api700_world.hpp"
#include "interfaces/lua/api700_world.guards.hpp"
#include "infrastructure/call/engine_call_access.hpp"
struct IdentityDescriptor {std::int32_t words[8];};
static IdentityDescriptor IdentityArea(const void*p){assert(p==g_RoomBytes.data());return{{1,-2,3,-4,5,-6,7,-8}};}
static IdentityDescriptor IdentityTile(const void*p){assert(p==g_RoomBytes.data());return{{8,7,6,5,4,3,2,1}};}
'''
SETUP=r'''
 for(const auto&g:api700_world::kGuards)std::memcpy(g_ModuleBytes.data()+g.offset,g.bytes.data(),16);
 const std::uintptr_t identityWorld[]={0,0,0,0,engine_call::AddressOfFunction(&IdentityArea),engine_call::AddressOfFunction(&IdentityTile)};SetApi700WorldNativeTestBindings(identityWorld,6);
 PushOpaqueScalarValue<std::uint32_t>(L,"IsaacRuntime.IdentityTestEnum","IdentityTestEnum",0xf1234567);lua_setglobal(L,"ownedEnumA");PushOpaqueScalarValue<std::uint32_t>(L,"IsaacRuntime.IdentityTestEnum","IdentityTestEnum",0xf1234567);lua_setglobal(L,"ownedEnumB");
 Run(L,R"lua(
 assert(GetPtrHash(ownedEnumA)~=0 and GetPtrHash(ownedEnumA)~=GetPtrHash(ownedEnumB),'opaque native value identity missing')
 ownedArea=Game():GetRoom():GetLRoomAreaDesc();ownedTile=Game():GetRoom():GetLRoomTileDesc()
 assert(GetPtrHash(ownedArea)~=0 and GetPtrHash(ownedTile)~=0 and GetPtrHash(ownedArea)~=GetPtrHash(ownedTile),'native descriptor identity missing')
 ambushA=Game():GetAmbush();ambushB=Game():GetAmbush();overlay=Game():GetItemOverlay()
 assert(GetPtrHash(ambushA)==gameAddress+0x26faa8 and GetPtrHash(ambushB)==GetPtrHash(ambushA) and GetPtrHash(overlay)==gameAddress+0x25db0,'embedded Game object identity missing')
 )lua");
 for(const auto&name:{"ownedEnumA","ownedArea","ownedTile"}){lua_getglobal(L,name);const auto*data=lua_touserdata(L,-1);assert(data);lua_pushinteger(L,static_cast<lua_Integer>(reinterpret_cast<std::uintptr_t>(data)));lua_setglobal(L,"expectedStorage");lua_pop(L,1);Run(L,(std::string("assert(GetPtrHash(")+name+")==expectedStorage)").c_str());}
 lua_getglobal(L,"ownedArea");assert(lua_rawlen(L,-1)==32);const std::int32_t expectedArea[]={1,-2,3,-4,5,-6,7,-8};assert(!std::memcmp(lua_touserdata(L,-1),expectedArea,32));lua_pop(L,1);
 lua_getglobal(L,"ownedTile");assert(lua_rawlen(L,-1)==32);const std::int32_t expectedTile[]={8,7,6,5,4,3,2,1};assert(!std::memcmp(lua_touserdata(L,-1),expectedTile,32));lua_pop(L,1);
'''
class OwnedOpaquePointerIdentity(unittest.TestCase):
 def test_native_value_payloads_and_game_borrowed_owners(self):
  main=original.MAIN.replace('int main(){',PREFIX+'\nint main(){',1)
  main=main.replace(' Run(L,R"lua(',SETUP+' Run(L,R"lua(',1)
  main=main.replace('assert(GetPtrHash(Game())==0 and GetPtrHash(Game():GetRoom())==0)','assert(GetPtrHash(Game())==0 and GetPtrHash(Game():GetRoom())==0 and GetPtrHash(ambushA)==0 and GetPtrHash(overlay)==0 and GetPtrHash(ownedArea)~=0)')
  with mock.patch.object(original,'MAIN',main):original.ObjectPointerIdentityTests.test_real_object_aliases_distinct_objects_and_lifetime(self)
