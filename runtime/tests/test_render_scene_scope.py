"""真实Manager/Present生产函数体：菜单不派游戏渲染，局内含暂停继续，缓存不清也不残留。"""
import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def body(text,signature):
 start=text.index(signature);brace=text.index('{',start);n=1;end=brace+1
 while n:
  n+=(text[end]=='{')-(text[end]=='}');end+=1
 return text[start:end]

class RenderSceneScopeTests(unittest.TestCase):
 def test_menu_game_pause_exit_and_continue_keep_correct_callback_scope(self):
  production=(ROOT/'runtime/source/hook_manager.cpp').read_text()
  manager=body(production,'void RenderHookBody(IsaacRepentance::Manager* self')
  present=body(production,'IsaacModRuntime_DispatchPostRenderBeforePresent(void* graphicsManager)')
  source=r'''
#include "domain/runtime/render_frame_coordinator.hpp"
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <initializer_list>
namespace IsaacRepentance {struct Manager {};}
static std::atomic<std::uintptr_t> g_RenderFrameManager{0};
static std::atomic<unsigned> g_RenderCallbackEntries{0},g_RenderPresentRelayEntries{0};
static isaac::runtime::RenderFrameCoordinator g_RenderFrameCoordinator;
static unsigned nativeScene=1,shaderFrames=0,postRender=0,shaderQueries=0;
static bool shaderActive=false,cacheStillValid=true,sceneReadable=true;
constexpr unsigned kManagerRenderSceneOffset=8,kManagerGameplayScene=2;
namespace isaac::runtime {
namespace engine_memory {
std::uintptr_t AddressOf(void* p){return reinterpret_cast<std::uintptr_t>(p);}
bool EngineMemoryReadable(std::uintptr_t,std::size_t){return true;}
template<class T,class Check>bool ReadField(std::uintptr_t p,unsigned offset,T* v,Check){assert(p==0x1234&&offset==8);if(!sceneReadable)return false;*v=nativeScene;return true;}
}
constexpr unsigned kProbeBreakAfterEntries=100000,kProbeBreakRenderCallback=1;
bool BeginShaderFrame(){++shaderFrames;shaderActive=true;return true;}
void AbortShaderFrame(){shaderActive=false;}
void FinishShaderFrame(std::uintptr_t manager){assert(manager==0x1234);if(shaderActive)++shaderQueries;shaderActive=false;}
}
void IsaacModRuntime_ProbeBreak(unsigned){assert(false);}
bool IsRenderPresentRelayInstalled(){return true;}
void DispatchModPostRender(void* manager){assert(manager==reinterpret_cast<void*>(0x1234));++postRender;}
MANAGER
void PRESENT
void Render(){RenderHookBody(reinterpret_cast<IsaacRepentance::Manager*>(0x1234),[](auto*){IsaacModRuntime_DispatchPostRenderBeforePresent(nullptr);});}
int main(){
 // No run yet, and room/map memory may already exist: scene is authoritative.
 Render();if(shaderFrames||postRender||shaderQueries){std::puts("main menu dispatched gameplay render/shader callbacks");return 81;}
 nativeScene=2;Render();assert(shaderFrames==1&&postRender==1&&shaderQueries==1);
 // Pause is a Game render too; it must keep the HUD/mod callback path.
 Render();assert(shaderFrames==2&&postRender==2&&shaderQueries==2);
 nativeScene=1;Render();assert(cacheStillValid);
 if(shaderFrames!=2||postRender!=2||shaderQueries!=2){std::puts("exit retained cached-map drawing in menu");return 82;}
 nativeScene=2;Render();assert(shaderFrames==3&&postRender==3&&shaderQueries==3);
 for(unsigned state:{0u,3u,4u,5u}){nativeScene=state;Render();}
 assert(shaderFrames==3&&postRender==3&&shaderQueries==3);
 sceneReadable=false;nativeScene=2;Render();assert(shaderFrames==3&&postRender==3);
 sceneReadable=true;Render();assert(shaderFrames==4&&postRender==4);
 static_assert(sizeof(isaac::runtime::RenderFrameScope)==32);
}
'''.replace('MANAGER',manager).replace('PRESENT',present)
  with tempfile.TemporaryDirectory(prefix='isaac-render-scene-')as tmp:
   cpp,exe=Path(tmp)/'test.cpp',Path(tmp)/'test';cpp.write_text(source)
   r=subprocess.run(['c++','-std=c++20','-DEXL_LAYERED_RUNTIME=1','-Wall','-Wextra','-Werror','-I'+str(ROOT/'runtime/src'),str(cpp),'-o',str(exe)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(exe)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)

 def test_fixed_nro_scene_switch_routes_only_state_two_to_game_render(self):
  import sys
  sys.path.insert(0,str(ROOT/'tools'))
  from gen_engine_symbol_signatures import NRO
  b=NRO.read_bytes()
  self.assertEqual(b[0x3f97b8:0x3f97bc],bytes.fromhex('680a40b9'))
  targets=[0x3f97e0+4*v for v in b[0x8bf819:0x8bf81e]]
  self.assertEqual(targets,[0x3f97e0,0x3f9814,0x3f9828,0x3f984c,0x3f983c])
