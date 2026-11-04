"""原版PC的ItemConfig.Config命名空间，静态函数与实际实例元表一致。"""
import unittest
from .test_api400_params import run_main
from .test_api600_config import MAIN

NAMESPACE_MAIN=MAIN.replace('int main(){', '''
#include "infrastructure/call/engine_call_access.hpp"
#include "interfaces/lua/api300_world.hpp"
#include "interfaces/lua/api300_world.guards.hpp"
static unsigned validityCalls;
static bool IsValid(std::int32_t id){++validityCalls;return id==1||id==105;}
int main(){''',1).replace('const char*script=R"lua(', '''
std::memcpy(g_ModuleBytes.data()+api300_world::kItemConfigIsValidCollectibleEntry,api300_world::kItemConfigIsValidCollectibleGuard.data(),16);
Api300WorldNativeTestBindings bindings{};bindings.methods[static_cast<unsigned>(Api300WorldNative::ItemConfigIsValidCollectible)]=engine_call::AddressOfFunction(&IsValid);SetApi300WorldNativeTestBindings(bindings);
const char*script=R"lua(
assert(type(ItemConfig.Config)=="table","PC ItemConfig.Config namespace missing")
assert(ItemConfig.Config.IsValidCollectible==ItemConfig.IsValidCollectible)
assert(ItemConfig.Config.ShouldAddCostumeOnPickup==ItemConfig.ShouldAddCostumeOnPickup)
assert(ItemConfig.Config.IsValidCollectible(1) and ItemConfig.Config.IsValidCollectible(105))
assert(not ItemConfig.Config.IsValidCollectible(-1))
local instance=Isaac.GetItemConfig()
assert(getmetatable(ItemConfig.Config).__class==getmetatable(instance))
assert(ItemConfig.Config.ShouldAddCostumeOnPickup(instance:GetCollectible(1)))
assert(not ItemConfig.Config.ShouldAddCostumeOnPickup(nil))
assert(ItemConfig.TAG_BOB~=nil)
assert(ItemConfig.CHARGE_NORMAL==0 and ItemConfig.CHARGE_TIMED==1 and ItemConfig.CHARGE_SPECIAL==2)
assert("slot:"..ItemConfig.CHARGE_NORMAL=="slot:0")
for i,name in ipairs({'TAROT','SUIT','RUNE','SPECIAL','SPECIAL_OBJECT','TAROT_REVERSE'}) do
 assert(ItemConfig['CARDTYPE_'..name]==i-1)
end
''',1)
class ItemConfigNamespaceTests(unittest.TestCase):
 def test_pc_namespace_statics_and_class_identity(self):
  r=run_main(NAMESPACE_MAIN)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
