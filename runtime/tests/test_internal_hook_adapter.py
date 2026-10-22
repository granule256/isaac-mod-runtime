"""实际内部安装适配器：全部指纹拒绝、入口布局与真实后端路由。"""
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[2]
CPP=ROOT/'runtime/src/infrastructure/internal/internal_hook_adapter.cpp'

class InternalHookAdapterTests(unittest.TestCase):
 def test_real_installer_atomic_commit_retained_veneer_and_failure(self):
  shim=r"""
#pragma once
#include <array>
#include <span>
#include <cstdint>
#include <cstring>
extern void FakeFlush(std::uintptr_t,void*,std::size_t);
namespace exl::util {
class RwPages {
 std::uintptr_t address_;std::size_t size_;alignas(16) unsigned char shadow_[16]{};
public:
 RwPages(std::uintptr_t p,std::size_t n):address_(p),size_(n){std::memcpy(shadow_,reinterpret_cast<void*>(p),n);}
 std::uintptr_t GetRw()const{return reinterpret_cast<std::uintptr_t>(shadow_);}
 void Flush(){FakeFlush(address_,shadow_,size_);}
};
template<std::size_t N>class Jit {
 std::uintptr_t address_{};
public:
 constexpr Jit()=default;
 void Initialize(std::span<const std::uint8_t,N> a){address_=reinterpret_cast<std::uintptr_t>(a.data());}
 std::uintptr_t GetRo()const{return address_;}
 std::uintptr_t GetRw()const{return address_;}
 void Flush(){}
};
}
#define JIT_CREATE(name,size) namespace impl::name {alignas(4096) std::array<std::uint8_t,size>s_Area{};} constinit exl::util::Jit<size>name
"""
  driver=r"""
#include "relay/internal_hook.hpp"
#include <cassert>
#include <cstring>
#include <vector>
using namespace isaac::runtime::relay;
alignas(4096) static unsigned char memory[4096]{};
static std::vector<std::uintptr_t> flushes;
static int mode=0;static unsigned entryFlushes=0;
static std::uintptr_t entry(){return reinterpret_cast<std::uintptr_t>(memory+32);}
static std::uintptr_t veneer(){return reinterpret_cast<std::uintptr_t>(memory+64);}
void FakeFlush(std::uintptr_t p,void* shadow,std::size_t n){
 flushes.push_back(p);
 if(p==entry()){
  ++entryFlushes;
  if(entryFlushes==1&&mode==1)return; // RO暂未看到完整写入；RW仍有已提交B，可原子回滚。
  if(entryFlushes==1&&mode==2){auto* word=static_cast<unsigned*>(shadow);*word^=1;}
 }
 std::memcpy(reinterpret_cast<void*>(p),shadow,n);
}
extern "C" void isaac_internal_hook_context(){}
int main(){
 InternalHookBinding binding{};binding.callback=+[](InternalHookContext&,const void*)noexcept->unsigned{return 0;};
 binding.resumes[0]=0x452a1c;binding.resumeCount=1;binding.scratch=InternalScratchPolicy::ProvedDeadX16;
 constexpr unsigned original=0x94087527;
 const InternalHookSite site{entry(),original};
 unsigned branch{};assert(BuildInternalBranch(&branch,entry(),veneer()));
 for(int testMode:{0,1,2}){
  std::memset(memory,0,sizeof(memory));std::memcpy(memory+32,&original,4);
  mode=testMode;entryFlushes=0;flushes.clear();
  auto failure=TryInstallInternalHook(binding,site,veneer());
  assert(failure==(mode==0?InternalHookFailure::None:(mode==1?InternalHookFailure::WriteVerifyFailed:InternalHookFailure::RollbackFailed)));
  unsigned actual=0;std::memcpy(&actual,memory+32,4);
  assert(actual==(mode==0?branch:(mode==1?original:(branch^1))));
  assert(LoadLittleEndianWord(memory+64,0)==0x58000050 && LoadLittleEndianWord(memory+64,1)==0xd61f0200);
  assert(flushes.front()==veneer()&&flushes[1]==entry());
  if(mode==1){
   assert(flushes.size()==3&&flushes.back()==entry());
   flushes.clear();assert(TryInstallInternalHook(binding,site,veneer())==InternalHookFailure::VeneerNotEmpty&&flushes.empty());
  }
 }
 std::memset(memory,0,sizeof(memory));std::memcpy(memory+32,&original,4);flushes.clear();
 auto unsafe=site;unsafe.expected=0x7100151f;
 assert(TryInstallInternalHook(binding,unsafe,veneer())==InternalHookFailure::UnsafeInstruction&&flushes.empty());
 memory[32]^=1;
 assert(TryInstallInternalHook(binding,site,veneer())==InternalHookFailure::GuardMismatch&&flushes.empty());
}
"""
  with tempfile.TemporaryDirectory() as tmp:
   p=pathlib.Path(tmp);(p/'lib/util/sys').mkdir(parents=True)
   (p/'lib/util/sys/jit.hpp').write_text(shim);(p/'driver.cpp').write_text(driver)
   result=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror',
    '-I',str(p),'-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),
    str(p/'driver.cpp'),str(ROOT/'runtime/source/relay/internal_hook.cpp'),'-o',str(p/'driver')],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   result=subprocess.run([str(p/'driver')],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)

 def compile_run(self,driver,sources):
  if CPP in sources and 'PressurePlateDestructorInternalCallback' not in driver:
   driver+="""
#include "pressure_plate_animation_hook.hpp"
namespace isaac::runtime {
std::uint32_t PressurePlateDestructorInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
void MarkPressurePlateDestructorHookInstalled(bool)noexcept{}
}
"""
  if CPP in sources and 'ConsoleUnknownInternalCallback' not in driver:
   driver+="""
#include "relay/internal_hook.hpp"
namespace isaac::runtime {
std::uint32_t ConsoleUnknownInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
}
namespace isaac::runtime::relay {
InternalHookFailure TryInstallConsoleConditionalHook(const InternalHookBinding&,const ColdInternalHookSite&){return InternalHookFailure::InvalidPlan;}
}
"""
  with tempfile.TemporaryDirectory() as tmp:
   p=pathlib.Path(tmp);(p/'driver.cpp').write_text(driver)
   result=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror',
     '-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(p/'driver.cpp'),
     *map(str,sources),'-o',str(p/'driver')],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   result=subprocess.run([str(p/'driver')],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)

 def test_actual_nro_guards_reject_every_changed_byte_before_install(self):
  candidates=list(ROOT.glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro'))
  if not candidates:
   candidates=list(pathlib.Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro'))
  if not candidates:self.skipTest('没有用户提供的固定NRO')
  nro=candidates[0].read_bytes()
  spans=[(int(o,16),bytes(int(x,16) for x in re.findall(r'0x([0-9A-F]{2})',b)))
   for o,b in re.findall(r'\{0x([0-9A-F]+), \{([^}]+)\}\}',CPP.read_text())]
  self.assertGreaterEqual(len(spans),17)
  for off,data in spans:self.assertEqual(nro[off:off+16],data,f'0x{off:x}指纹与NRO不符')
  spans.extend([(0x4529c8,nro[0x4529c8:0x4529d8])])
  assignments='\n'.join(f'copy(0x{off:x},{{'+','.join(str(x) for x in data)+'});' for off,data in spans)
  offsets=','.join(f'0x{off:x}' for off,_ in spans)
  driver=r'''
#include "infrastructure/internal/internal_hook_adapter.hpp"
#include "room_spawn_internal_hook.hpp"
#include "trinket_internal_hook.hpp"
#include <cassert>
#include <cstring>
#include <vector>
using namespace isaac::runtime;
static std::uintptr_t base=0;static unsigned installs=0;
namespace isaac::runtime {
std::uint32_t LevelCurseFirstRandomInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t LevelCurseEvaluateInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t PickupSelectionInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}

std::uint32_t RoomFixSpawnCtorInternalCallback(relay::InternalHookContext&,const void*) noexcept {return 0;}
std::uint32_t TrinketFirstRandomInternalCallback(relay::InternalHookContext&,const void*) noexcept {return 0;}
std::uint32_t TrinketSelectedInternalCallback(relay::InternalHookContext&,const void*) noexcept {return 0;}
std::uint32_t ClearAwardInternalCallback(relay::InternalHookContext&,const void*) noexcept {return 0;}
std::uint32_t EntityDestructorRemoveInternalCallback(relay::InternalHookContext&,const void*) noexcept {return 0;}
}
namespace isaac::runtime::relay {
InternalHookFailure TryInstallPreinstalledInternalHook(const InternalHookBinding&,const ColdInternalHookSite&){return InternalHookFailure::InvalidPlan;}

InternalHookFailure TryInstallInternalHook(const InternalHookBinding& b,const InternalHookSite& s,std::uintptr_t v){
 assert(ValidInternalBinding(b)&&b.callback==RoomFixSpawnCtorInternalCallback&&b.resumeCount==2);
 assert(b.resumes[0]==base+0x452a1c&&b.resumes[1]==base+0x453798);
 auto& native=*static_cast<const RoomSpawnNativeBindings*>(b.user);
 assert(reinterpret_cast<std::uintptr_t>(native.next)==base+0x66fe90);
 assert(reinterpret_cast<std::uintptr_t>(native.getCard)==base+0x6743b0);
 assert(s.target==base+0x452984&&s.expected==0x94087527&&v==base+0x68cfd0);
 assert(reinterpret_cast<std::uintptr_t>(native.construct)==base+0x66fe20);
 assert(reinterpret_cast<std::uintptr_t>(native.random)==base+0x66fe30&&native.gameGotSlot==base+0xaac698);
 ++installs;return InternalHookFailure::None;
}
}
int main(){
 std::vector<unsigned char> image(0x68d000);base=reinterpret_cast<std::uintptr_t>(image.data());
 auto copy=[&](std::size_t o,std::initializer_list<unsigned char> b){std::memcpy(image.data()+o,b.begin(),b.size());};
 ASSIGNMENTS
 HookTarget target{};target.base=base;target.codeSize=image.size();target.imageSize=image.size();
 InternalHookAdapter adapter;
 for(unsigned off:{OFFSETS})for(unsigned byte=0;byte<16;++byte){
  image[off+byte]^=1;
  assert(!adapter.Install(HookId::RoomEntitySpawn,target).ok());
  assert(!adapter.IsInstalled(HookId::RoomEntitySpawn)&&installs==0&&adapter.LastFailureCode()!=0);
  image[off+byte]^=1;
 }
 HookTarget shortImage=target;shortImage.codeSize=0x4529cf;
 assert(!adapter.Install(HookId::RoomEntitySpawn,shortImage).ok()&&installs==0);
 assert(adapter.Install(HookId::RoomEntitySpawn,target).ok()&&installs==1);
 assert(adapter.IsInstalled(HookId::RoomEntitySpawn)&&adapter.LastFailureCode()==0);
 assert(!adapter.IsInstalled(HookId::GameSpawnEx));
 assert(adapter.Install(HookId::RoomEntitySpawn,target).code()==StatusCode::InvalidState&&installs==1);
 assert(adapter.Install(HookId::GameSpawnEx,target).code()==StatusCode::Unsupported);
}
'''.replace('ASSIGNMENTS',assignments).replace('OFFSETS',offsets)
  self.compile_run(driver,[CPP])

 def test_actual_routing_uses_internal_backend_and_failure_source(self):
  driver=r'''
#include "infrastructure/hook_routing_adapter.hpp"
#include <cassert>
using namespace isaac::runtime;
static unsigned internalCalls=0,entryCalls=0;
namespace isaac::runtime {
Status InternalHookAdapter::Install(HookId id,const HookTarget&)noexcept{assert(id==HookId::RoomEntitySpawn);++internalCalls;installed_=true;lastFailure_=5;return Status{StatusCode::Rejected};}
bool InternalHookAdapter::IsInstalled(HookId id)const noexcept{
 if(id==HookId::PressurePlateDestructor)return pressureDestructorInstalled_;
 if(id==HookId::PressurePlateDeletingDestructor)return pressureDeletingInstalled_;
 if(id==HookId::ItemPoolTrinketFirstRandom)return trinketFirstInstalled_;
 if(id==HookId::ItemPoolTrinketSelected)return trinketSelectedInstalled_;
 if(id==HookId::RoomClearAward)return clearAwardInstalled_;
 if(id==HookId::EntityDestructorRemove)return entityDestructorInstalled_;
 if(id==HookId::ConsoleUnknownLength)return consoleLengthInstalled_;
 if(id==HookId::ConsoleUnknownCompare)return consoleCompareInstalled_;
 if(id==HookId::LevelCurseFirstRandom)return levelCurseFirstInstalled_;
 if(id==HookId::LevelCurseEvaluation)return levelCurseEvaluationInstalled_;
 if(id==HookId::PickupSelection)return pickupSelectionInstalled_;
 if(id==HookId::PickupSelectionSpecial)return pickupSelectionSpecialInstalled_;
 return id==HookId::RoomEntitySpawn&&installed_;}
Status EntryRelayHookAdapter::Install(HookId id,const HookTarget&)noexcept{assert(id==HookId::GameSpawnEx);++entryCalls;lastFailure_=3;return Status{StatusCode::Rejected};}
bool EntryRelayHookAdapter::IsInstalled(HookId id)const noexcept{return installed_[static_cast<unsigned>(id)];}
std::uint32_t EntryRelayHookAdapter::LastFailureCode()const noexcept{return lastFailure_;}
Status GotSlotHookAdapter::Install(HookId,const HookTarget&)noexcept{return Status::Ok();}
bool GotSlotHookAdapter::IsInstalled(HookId id)const noexcept{return installed_[static_cast<unsigned>(id)];}
Status RelaySlotHookAdapter::Install(HookId,const HookTarget&)noexcept{return Status::Ok();}
bool RelaySlotHookAdapter::IsInstalled(HookId id)const noexcept{return installed_[static_cast<unsigned>(id)];}
Status ExlaunchHookAdapter::Install(HookId,const HookTarget&)noexcept{return Status::Ok();}
bool ExlaunchHookAdapter::IsInstalled(HookId id)const noexcept{return installed_[static_cast<unsigned>(id)];}
}
int main(){
 HookRoutingAdapter adapter;HookTarget target{};
 assert(!adapter.Install(HookId::RoomEntitySpawn,target).ok());
 assert(adapter.IsInstalled(HookId::RoomEntitySpawn)&&internalCalls==1&&entryCalls==0);
 assert(adapter.LastFailureCode()==5);
 assert(!adapter.Install(HookId::GameSpawnEx,target).ok());assert(adapter.LastFailureCode()==3&&entryCalls==1);
 assert(adapter.Install(HookId::ManagerPresent,target).ok());assert(adapter.LastFailureCode()==0);
 assert(adapter.Install(HookId::GameStart,target).ok());assert(adapter.LastFailureCode()==0);
 assert(!adapter.Install(HookId::Count,target).ok()&&adapter.LastFailureCode()==0);
}
'''
  self.compile_run(driver,[ROOT/'runtime/src/infrastructure/hook_routing_adapter.cpp'])

if __name__=='__main__':unittest.main()
