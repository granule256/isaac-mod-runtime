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
    def test_custom_names_unlock_storage_and_readonly(self):
        driver = DRIVER.replace('#include <vector>', r'''
#include <vector>
#include <unordered_map>
#include <string>
#include "program/xml_data_store.hpp"
#include "interfaces/lua/repentogon_persistent_api.hpp"
static lua_State* observed;
static void Capture(lua_State* L) noexcept {observed=L;}
static unsigned nativeReads{},nativeWrites{};
static bool NativeUnlocked(std::uintptr_t,int id) {++nativeReads;assert(id<641);return id==-1||id==2;}
static bool NativeTryUnlock(std::uintptr_t,int id) {++nativeWrites;assert(id==2);return true;}
struct AchievementFiles:ISaveFilePort {
 unsigned slot=2;bool fail=false;
 std::unordered_map<std::string,std::string> data;
 Status GetSaveSlot(unsigned* out) noexcept override{*out=slot;return Status::Ok();}
 Status Read(std::string_view path,char* out,std::size_t cap,std::size_t* size) noexcept override{
  std::string bytes;
  if(path=="isaac-repentogon-state.txt")bytes="isaac-repentogon 1\nenabled 1\n";
  else {auto it=data.find(std::string(path));if(it==data.end())return Status{StatusCode::NotFound};bytes=it->second;}
  *size=bytes.size();if(*size>cap)return Status{StatusCode::CapacityExceeded};std::memcpy(out,bytes.data(),*size);return Status::Ok();
 }
 Status Write(std::string_view path,std::string_view bytes) noexcept override{
  if(fail)return Status{StatusCode::IoFailure};data[std::string(path)]=std::string(bytes);return Status::Ok();
 }
 Status Remove(std::string_view) noexcept override{return Status{StatusCode::Unsupported};}
 Status Exists(const char*,bool*) noexcept override{return Status{StatusCode::Unsupported};}
};
''').replace('Files files(true);', r'''
 const char* xml="<achievements><achievement name='First' hidden='true'/><achievement name='Second' hidden='true'/><achievement name='Visible'/></achievements>";
 assert(xml_data::IngestXmlDataFile(static_cast<xml_data::XmlDataFileKind>(26),"ModA",true,xml,std::strlen(xml)));
 LuaRuntime::SetRuntimeExtensionInstaller(Capture);
 std::memcpy(moduleBytes.data()+kPersistentGameDataUnlockedOffset,kPersistentGameDataUnlockedExpectedBytes.data(),16);
 const unsigned char guard[]={0xfd,0x7b,0xbd,0xa9,0xf5,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
 std::memcpy(moduleBytes.data()+0x4393d0,guard,16);
 SetRepentogonAchievementNativeTestBindings({reinterpret_cast<std::uintptr_t>(&NativeUnlocked),reinterpret_cast<std::uintptr_t>(&NativeTryUnlock)});
 AchievementFiles files;
''')
        script = r'''
assert(type(Isaac.GetAchievementIdByName)=='function')
local id=Isaac.GetAchievementIdByName('First')
assert(id==641 and Isaac.GetAchievementIdByName('Second')==642)
assert(Isaac.GetAchievementIdByName('first')==-1)
assert(not pcall(Isaac.GetAchievementIdByName,{}))
assert(XMLData.GetEntryById(XMLNode.ACHIEVEMENT,id).sourceid=='ModA')
local p=Isaac.GetPersistentGameData()
assert(p:Unlocked(-1) and p:Unlocked(2) and not p:Unlocked(-2))
assert(p:TryUnlock(2))
assert(not p:Unlocked(id) and not p:Unlocked(99999))
assert(p:TryUnlock(id) and p:Unlocked(id))
assert(not p:TryUnlock(id) and not p:TryUnlock(99999))
assert(not p:TryUnlock(0) and not p:TryUnlock(-1) and not p:TryUnlock(638))
assert(not pcall(function()p:TryUnlock(643)end) and not p:Unlocked(643))
'''
        begin = driver.index(' const char* script=R"lua(')
        end = driver.index(')lua";', begin) + len(')lua";')
        driver = driver[:begin] + ' const char* script=R"lua(' + script + ')lua";' + driver[end:]
        driver = driver.replace(' assert(LuaRuntime::ShutdownForModReload());', r'''
 auto* L=observed;
 assert(nativeReads==3&&nativeWrites==1);
 auto run=[L](const char* code){if(luaL_dostring(L,code)!=LUA_OK){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));assert(false);}};
 files.slot=3;run("assert(not Isaac.GetPersistentGameData():Unlocked(641))");
 files.slot=2;run("assert(Isaac.GetPersistentGameData():Unlocked(641))");
 pgd[1]=1;run("assert(not Isaac.GetPersistentGameData():TryUnlock(642))");pgd[1]=0;
 files.fail=true;run("assert(not pcall(function()Isaac.GetPersistentGameData():TryUnlock(642)end))");files.fail=false;
 run("assert(not Isaac.GetPersistentGameData():Unlocked(642))");
 assert(LuaRuntime::ShutdownForModReload());
''')
        with tempfile.TemporaryDirectory(prefix='repentogon-achievements-') as folder:
            binary = test_support.build_lua_harness(source_root=SOURCE,
                workdir=Path(folder), harness_source=driver)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_counter_and_collection_boundaries(self):
        with tempfile.TemporaryDirectory(prefix='repentogon-pgd-') as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=DRIVER)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
