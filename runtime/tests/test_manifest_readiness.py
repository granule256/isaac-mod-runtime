"""编译真实安装函数，故意在worker每个阶段模拟游戏帧，禁止提早初始化Lua。"""
import pathlib,re,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]

def installation_function():
 s=(ROOT/'runtime/source/hook_manager.cpp').read_text()
 s=re.sub(r'//[^\n]*','',s);s=re.sub(r'/\*.*?\*/','',s,flags=re.S)
 a=s.index('DefaultManifestInstallResult TryInstallDefaultManifestMod(');start=s.index('{',a);depth=1;i=start+1
 while depth:depth+=(s[i]=='{')-(s[i]=='}');i+=1
 return s[a:i]

class ManifestReadinessTests(unittest.TestCase):
 def test_actual_worker_function_does_not_arm_during_install_or_failure(self):
  driver=r'''
#include "domain/runtime/hook_catalog.hpp"
#include <atomic>
#include <array>
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <cassert>
using u32=std::uint32_t;
enum class DefaultManifestState:u32{Unarmed,Armed,Running,Ready,Failed};
static std::atomic<DefaultManifestState>g_DefaultManifestState{DefaultManifestState::Unarmed};
static std::atomic<std::uintptr_t>g_RenderFrameManager{0};
static unsigned premature=0;static bool complete=false,allowHooks=true,allowBindings=true;
static void Frame(){if(g_DefaultManifestState.load(std::memory_order_acquire)==DefaultManifestState::Armed&&!complete)++premature;}
struct TargetModule{std::uintptr_t base=4;std::size_t textSize=16,size=32;std::array<unsigned char,20>buildId{};};
namespace GameFileReader{
struct Bindings{unsigned marker{};};
bool VerifyBindings(const TargetModule&,Bindings* b){Frame();b->marker=77;return allowBindings;}
}
static GameFileReader::Bindings g_DefaultManifestBindings{};
enum class DefaultManifestInstallResult{Success,FileBindingMismatch};
bool VerifyManagerUpdate(const TargetModule&,std::uintptr_t*){Frame();return true;}
bool VerifyManagerRelay(const TargetModule&,std::uintptr_t,std::uintptr_t*){Frame();return true;}
bool SkipOptionalHooksPredicate(isaac::runtime::HookId,void*){return false;}
void PublishManagerEngineBindings(const TargetModule&){Frame();}
void PublishEntryRelayOriginals(const TargetModule&){Frame();}
namespace LuaRuntime{void SetFrameManagerProvider(std::uintptr_t(*)()){Frame();}}
namespace isaac::runtime{
constexpr auto kHookBackends=CatalogBackends();
struct ModuleInfo{std::uintptr_t base{};std::size_t textSize{},imageSize{};bool valid{};std::array<unsigned char,20>buildId{};};
struct HookInstallReport{};struct HookRoutingAdapter{};
struct Result{bool value;bool ok()const{return value;}};
struct HookInstallService{
 HookInstallService(HookRoutingAdapter&){}
 void SetSkipPredicate(bool(*)(HookId,void*),void*){Frame();}
 Result InstallProductionHooks(const ModuleInfo&,HookInstallReport*){Frame();Frame();Frame();return{allowHooks};}
};
void RegisterEntryRelayCallbacks(){Frame();}
unsigned HookRoutingFailureCode(const HookRoutingAdapter&){Frame();return 0;}
void PublishHookInstallReport(const HookInstallReport&,unsigned){Frame();}
void InstallMinimapTouchGate(std::uintptr_t,std::size_t){Frame();complete=true;}
namespace modmenu{void ModMenuNativeInstall(const TargetModule&){Frame();}}
}
FUNCTION
int main(){
 for(unsigned mode:{0,1,2}){
  premature=0;complete=false;allowHooks=mode!=1;allowBindings=mode!=2;
  g_DefaultManifestState.store(DefaultManifestState::Unarmed);g_DefaultManifestBindings={};
  auto result=TryInstallDefaultManifestMod(TargetModule{});
  assert(premature==0);
  if(mode==0){assert(result==DefaultManifestInstallResult::Success&&complete&&g_DefaultManifestState.load()==DefaultManifestState::Armed);}
  else{assert(result==DefaultManifestInstallResult::FileBindingMismatch&&g_DefaultManifestState.load()==DefaultManifestState::Unarmed&&g_DefaultManifestBindings.marker==0);}
 }
}
'''.replace('FUNCTION',installation_function())
  with tempfile.TemporaryDirectory()as tmp:
   p=pathlib.Path(tmp);(p/'driver.cpp').write_text(driver)
   result=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/src'),str(p/'driver.cpp'),'-o',str(p/'driver')],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   result=subprocess.run([str(p/'driver')],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
