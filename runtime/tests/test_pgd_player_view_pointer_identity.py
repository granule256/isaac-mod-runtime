"""PGD与玩家内嵌const EntityRef/Pocket借用身份和真实owner退役。"""
from unittest import mock
import unittest
from . import test_object_pointer_identity as original
PREFIX=r'''
#include "interfaces/lua/api700_player.guards.hpp"
'''
SETUP=r'''
 std::vector<unsigned char> identityManager(0x40000),identityManagerSlot(8);
 WriteWord(identityManagerSlot,0,AddressOf(identityManager));WriteWord(g_ModuleBytes,kGameManagerGlobalSlotOffset,AddressOf(identityManagerSlot));
 lua_pushinteger(L,static_cast<lua_Integer>(AddressOf(identityManager)+0x18));lua_setglobal(L,"pgdAddress");
 for(const auto&g:{api700_player::kLastDamageEntry,api700_player::kPocketEntry})std::memcpy(g_ModuleBytes.data()+g.offset,g.guard,16);
 lua_pushinteger(L,static_cast<lua_Integer>(AddressOf(g_Entities[kPlayer])));lua_setglobal(L,"playerAddress");
 Run(L,R"lua(
 pgdA=Isaac.GetPersistentGameData();pgdB=Isaac.GetPersistentGameData();assert(pgdA~=pgdB and GetPtrHash(pgdA)==pgdAddress and GetPtrHash(pgdB)==pgdAddress,'PGD native singleton identity missing')
 damageRefA=player:GetLastDamageSource();damageRefB=player:GetLastDamageSource();pocket0=player:GetPocketItem(0);pocket3=player:GetPocketItem(3)
 assert(GetPtrHash(damageRefA)==playerAddress+0x1a70 and GetPtrHash(damageRefB)==GetPtrHash(damageRefA),'player const EntityRef identity missing')
 assert(GetPtrHash(pocket0)==playerAddress+0x1c10 and GetPtrHash(pocket3)==playerAddress+0x1c28,'pocket native identities missing')
 )lua");
 WriteWord(identityManagerSlot,0,0);Run(L,"assert(GetPtrHash(pgdA)==0 and GetPtrHash(pgdB)==0)");
'''
class PgdPlayerViewPointerIdentity(unittest.TestCase):
 def test_native_singleton_and_player_embedded_views(self):
  main=original.MAIN.replace('int main(){',PREFIX+'\nint main(){',1).replace(' Run(L,R"lua(',SETUP+' Run(L,R"lua(',1)
  main=main.replace('assert(GetPtrHash(refA)==0 and GetPtrHash(refB)==0);','assert(GetPtrHash(refA)==0 and GetPtrHash(refB)==0);assert(GetPtrHash(damageRefA)==0 and GetPtrHash(damageRefB)==0 and GetPtrHash(pocket0)==0 and GetPtrHash(pocket3)==0);')
  with mock.patch.object(original,'MAIN',main):original.ObjectPointerIdentityTests.test_real_object_aliases_distinct_objects_and_lifetime(self)
