"""运行时菜单扩展四接口：公开Lua到真实开关服务/存档端口/诊断状态。"""
from unittest import mock
import unittest
from . import test_object_pointer_identity as original
PREFIX=r'''
#include "interfaces/lua/mod_menu_api.hpp"
#include "application/mod/mod_toggle_service.hpp"
#include <atomic>
namespace isaac::runtime {extern std::atomic<std::uint32_t> g_ModMenuMilestones,g_ModMenuReportCount,g_ModMenuLastCode;}
struct MenuFiles final:isaac::runtime::ISaveFilePort{
 std::string data;bool exists=false;unsigned writes=0,reads=0;
 isaac::runtime::Status Read(std::string_view,char*out,std::size_t capacity,std::size_t*size)noexcept override{++reads;if(!exists)return isaac::runtime::Status{isaac::runtime::StatusCode::NotFound};if(data.size()>capacity)return isaac::runtime::Status{isaac::runtime::StatusCode::CapacityExceeded};std::memcpy(out,data.data(),data.size());*size=data.size();return isaac::runtime::Status::Ok();}
 isaac::runtime::Status Write(std::string_view,std::string_view value)noexcept override{++writes;data=value;exists=true;return isaac::runtime::Status::Ok();}
 isaac::runtime::Status Remove(std::string_view)noexcept override{data.clear();exists=false;return isaac::runtime::Status::Ok();}
 isaac::runtime::Status Exists(const char*,bool*out)noexcept override{*out=false;return isaac::runtime::Status::Ok();}
};
'''
SETUP=r'''
 MenuFiles menuFiles;ModToggleService toggles(menuFiles);assert(toggles.Load().ok());ModMenuAttachToggles(&toggles);
 ResolvedManifestModBatch discovered{};discovered.count=2;discovered.mods[0].modRoot="rom:/isaac_mods/mods/ProbeA";discovered.mods[1].modRoot="rom:/isaac_mods/mods/ProbeB";ModMenuPublishDiscovered(discovered);
 ResolvedManifestModBatch active{};active.count=1;active.mods[0].modRoot=discovered.mods[0].modRoot;ModMenuMarkActive(active);
 const auto reports=g_ModMenuReportCount.load();const auto milestones=g_ModMenuMilestones.load();
 Run(L,R"lua(
 local list=RuntimeMods.List();assert(#list==2 and list[1].Directory=='ProbeA' and list[2].Directory=='ProbeB');assert(list[1].Enabled and list[2].Enabled and list[1].Active and not list[2].Active)
 list[1].Directory='changed';assert(RuntimeMods.List()[1].Directory=='ProbeA')
 assert(RuntimeMods.SetEnabled('ProbeB',false));assert(not RuntimeMods.List()[2].Enabled and not pcall(RuntimeMods.SetEnabled,'NoSuchProbe',false))
 assert(RuntimeMods.Save());assert(RuntimeMods.SetEnabled('ProbeB',true));assert(RuntimeMods.Reload());assert(not RuntimeMods.List()[2].Enabled)
 assert(select('#',RuntimeMods.Report(3))==0 and select('#',RuntimeMods.Report(35))==0)
 assert(not pcall(RuntimeMods.List,1) and not pcall(RuntimeMods.SetEnabled,'ProbeB',0) and not pcall(RuntimeMods.Reload,1) and not pcall(RuntimeMods.Report,{}))
 )lua");
 assert(menuFiles.writes==1&&menuFiles.reads==2&&g_ModMenuReportCount.load()==reports+2&&g_ModMenuLastCode.load()==35&&g_ModMenuMilestones.load()==(milestones|8));
 ModMenuAttachToggles(nullptr);Run(L,"assert(not RuntimeMods.SetEnabled('ProbeB',true) and not RuntimeMods.Reload());assert(#RuntimeMods.List()==2)");
'''
class RuntimeModsPublicContract(unittest.TestCase):
 def test_list_toggle_reload_and_report_reach_owners(self):
  needle=' Run(L,R"lua('
  main=original.MAIN.replace(needle,SETUP+needle,1)
  main=main.replace('int main(){',PREFIX+'\nint main(){',1)
  with mock.patch.object(original,'MAIN',main):original.ObjectPointerIdentityTests.test_real_object_aliases_distinct_objects_and_lifetime(self)
