"""PersistentGameData extension counters and collection bits."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX

SOURCE = Path(__file__).resolve().parents[1] / 'source'
DRIVER = PREFIX + r'''
#include "runtime_constants.hpp"
#include <vector>
static std::vector<unsigned char> moduleBytes,managerSlot,manager;
int main(){
 moduleBytes.resize(kGameManagerGlobalSlotOffset+sizeof(std::uintptr_t));
 managerSlot.resize(sizeof(std::uintptr_t));manager.resize(kManagerPersistentGameDataObjectOffset+0x2ad4);
 const auto slot=reinterpret_cast<std::uintptr_t>(managerSlot.data());
 const auto object=reinterpret_cast<std::uintptr_t>(manager.data());
 std::memcpy(moduleBytes.data()+kGameManagerGlobalSlotOffset,&slot,sizeof(slot));
 std::memcpy(managerSlot.data(),&object,sizeof(object));
 auto* pgd=manager.data()+kManagerPersistentGameDataObjectOffset;
 const std::int32_t counters[2]={17,-9};
 std::memcpy(pgd+0x2a8+3*4,&counters[0],4);
 std::memcpy(pgd+0x2a8+522*4,&counters[1],4);
 pgd[0xa68+1]=1;pgd[0xa68+732]=1;
 LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(moduleBytes.data()));
 Files files(true);SetSessionSaveFilePort(&files);LuaRuntime::ObserveGameThread();
 const repentogon::NativePort port{Ready,Ready};repentogon::SetNativePort(&port);
 const char* script=R"lua(
local p=Isaac.GetPersistentGameData()
assert(p:GetEventCounter(3)==17)
assert(p:GetEventCounter(522)==-9)
assert(p:GetEventCounter(0)==0)
assert(p:IsItemInCollection(1))
assert(p:IsItemInCollection(732))
assert(not p:IsItemInCollection(0))
assert(not p:IsItemInCollection(2))
for _,args in ipairs({{-1},{523},{1.5},{'x'},{}})do
 assert(not pcall(function()p:GetEventCounter(table.unpack(args))end))
end
for _,args in ipairs({{-1},{733},{1.5},{'x'},{}})do
 assert(not pcall(function()p:IsItemInCollection(table.unpack(args))end))
end
assert(not pcall(function()p:GetEventCounter(1,2)end))
assert(not pcall(function()p:IsItemInCollection(1,2)end))
)lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@persistent-extension.lua")!=LuaRuntime::LuaInitResult::Success){
  char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
  std::fprintf(stderr,"%s\n",error);return 1;
 }
 assert(LuaRuntime::ShutdownForModReload());
 repentogon::SetNativePort(nullptr);SetSessionSaveFilePort(nullptr);
}
'''


class RepentogonPersistentTests(unittest.TestCase):
    def test_counter_and_collection_boundaries(self):
        with tempfile.TemporaryDirectory(prefix='repentogon-pgd-') as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=DRIVER)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
