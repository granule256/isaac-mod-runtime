"""配置根、实时配置vector及SFX单例身份必须源自Manager真实内嵌对象。"""
from unittest import mock
import unittest
from . import test_object_pointer_identity as original
SETUP=r'''
 std::vector<unsigned char> manager(0x40000),managerSlot(8);
 WriteWord(managerSlot,0,AddressOf(manager));WriteWord(g_ModuleBytes,kGameManagerGlobalSlotOffset,AddressOf(managerSlot));
 for(const auto&r:{std::pair<const char*,std::uintptr_t>{"configAddress",AddressOf(manager)+0x36538},{"sfxAddress",AddressOf(manager)+0x364a8},{"collectiblesAddress",AddressOf(manager)+0x36538},{"trinketsAddress",AddressOf(manager)+0x36550}}){lua_pushinteger(L,static_cast<lua_Integer>(r.second));lua_setglobal(L,r.first);}
 Run(L,R"lua(
 configA=Isaac.GetItemConfig();configB=Isaac.GetItemConfig();assert(configA~=configB)
 assert(GetPtrHash(configA)==configAddress and GetPtrHash(configB)==configAddress,'ItemConfig root identity missing')
 sfxA=SFXManager();sfxB=SFXManager();assert(sfxA~=sfxB and GetPtrHash(sfxA)==sfxAddress and GetPtrHash(sfxB)==sfxAddress,'SFX singleton identity missing')
 configListA=configA:GetCollectibles();configListB=configB:GetCollectibles();trinketList=configA:GetTrinkets()
 assert(GetPtrHash(configListA)==collectiblesAddress and GetPtrHash(configListB)==collectiblesAddress and GetPtrHash(trinketList)==trinketsAddress,'configuration native vector identity missing')
 )lua");
 WriteWord(managerSlot,0,0);Run(L,"assert(GetPtrHash(configA)==0 and GetPtrHash(configB)==0 and GetPtrHash(sfxA)==0 and GetPtrHash(configListA)==0)");
'''
class ConfigSingletonPointerIdentity(unittest.TestCase):
 def test_manager_native_aliases_and_owner_loss(self):
  needle=' Run(L,R"lua('
  self.assertIn(needle,original.MAIN)
  with mock.patch.object(original,'MAIN',original.MAIN.replace(needle,SETUP+needle,1)):
   original.ObjectPointerIdentityTests.test_real_object_aliases_distinct_objects_and_lifetime(self)
