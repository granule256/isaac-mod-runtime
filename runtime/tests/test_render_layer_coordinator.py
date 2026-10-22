"""宿主编译生产帧协调器和HUD包装，核对前景顺序与重入去重。"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class RenderLayerCoordinatorTests(unittest.TestCase):
    def test_actual_manager_and_present_bodies_keep_shader_finish(self):
        production = (ROOT / "runtime/source/hook_manager.cpp").read_text()

        def body(signature):
            start = production.index(signature)
            brace = production.index("{", start)
            depth, end = 1, brace + 1
            while depth:
                depth += (production[end] == "{") - (production[end] == "}")
                end += 1
            return production[start:end]

        manager = body("void RenderHookBody(IsaacRepentance::Manager* self")
        present = body("IsaacModRuntime_DispatchPostRenderBeforePresent(void* graphicsManager)")
        driver = r'''
#include "domain/runtime/render_frame_coordinator.hpp"
#include <atomic>
#include <cassert>
#include <cstdint>
#include <vector>
namespace IsaacRepentance {struct Manager {};}
static std::atomic<std::uintptr_t> g_RenderFrameManager{0};
static std::atomic<unsigned> g_RenderCallbackEntries{0},g_RenderPresentRelayEntries{0};
static isaac::runtime::RenderFrameCoordinator g_RenderFrameCoordinator;
static int finish=0,abortCalls=0,begin=0,mod=0;
constexpr unsigned kManagerRenderSceneOffset=8,kManagerGameplayScene=2;
static bool presentInstalled=true;
static std::vector<int> order;
static auto* expectedManager=reinterpret_cast<IsaacRepentance::Manager*>(0x1234);
namespace isaac::runtime {
namespace engine_memory {
std::uintptr_t AddressOf(void* p){return reinterpret_cast<std::uintptr_t>(p);}
bool EngineMemoryReadable(std::uintptr_t,std::size_t){return true;}
template<class T,class C>bool ReadField(std::uintptr_t,unsigned offset,T* out,C){assert(offset==8);*out=2;return true;}
}
constexpr unsigned kProbeBreakAfterEntries=100000,kProbeBreakRenderCallback=1;
bool BeginShaderFrame(){++begin;return true;}
void AbortShaderFrame(){++abortCalls;}
void FinishShaderFrame(std::uintptr_t manager){assert(manager==0x1234);++finish;}
}
void IsaacModRuntime_ProbeBreak(unsigned){assert(false);}
bool IsRenderPresentRelayInstalled(){return presentInstalled;}
void DispatchModPostRender(void* manager){assert(manager==expectedManager);++mod;order.push_back(2);}
MANAGER
void PRESENT
static void Hud(void*){order.push_back(1);}
int main(){
 g_RenderFrameManager=0x1234;
 IsaacModRuntime_DispatchPostRenderBeforePresent(reinterpret_cast<void*>(0x9999));
#if defined(EXL_DIAGNOSTIC_STAGE)
 assert(mod==1); // 诊断包保留没有ManagerRender钩子时的旧派发。
#else
 assert(mod==0); // 生产不能用陈旧Manager派发。
#endif
 assert(finish==1);mod=0;finish=0;order.clear();
 RenderHookBody(expectedManager,[](auto*){
   isaac::runtime::RenderAfterNativeHud(g_RenderFrameCoordinator,nullptr,Hud,DispatchModPostRender);
   order.push_back(3); // 暂停/其它原生前景。
   IsaacModRuntime_DispatchPostRenderBeforePresent(nullptr);
   IsaacModRuntime_DispatchPostRenderBeforePresent(nullptr);
 });
 assert((order==std::vector<int>{1,2,3}));assert(mod==1&&finish==2&&begin==1&&abortCalls==1);
 assert(g_RenderFrameCoordinator.Manager()==nullptr);mod=0;order.clear();
 RenderHookBody(expectedManager,[](auto*){IsaacModRuntime_DispatchPostRenderBeforePresent(nullptr);});
 assert(mod==1&&finish==3&&begin==2&&abortCalls==2);mod=0;order.clear();
 presentInstalled=false;
 RenderHookBody(expectedManager,[](auto*){}); // HUD/Present都缺失的返回兜底。
 assert(mod==1&&finish==3&&begin==2&&abortCalls==3);
 assert(g_RenderFrameCoordinator.Manager()==nullptr);
}
'''.replace("MANAGER", manager).replace("PRESENT", present)
        with tempfile.TemporaryDirectory() as td:
            source, binary = Path(td) / "main.cpp", Path(td) / "probe"
            source.write_text(driver)
            for definitions in ([], ["-DEXL_DIAGNOSTIC_STAGE=15"]):
                with self.subTest(definitions=definitions):
                    result = subprocess.run(["c++", "-std=c++20", "-DEXL_LAYERED_RUNTIME=1", *definitions,
                                             "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "runtime/src"),
                                             str(source), "-o", str(binary)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    result = subprocess.run([str(binary)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_shared_coordinator_and_typed_hud_wrapper(self):
        header = ROOT / "runtime/src/domain/runtime/render_frame_coordinator.hpp"
        self.assertTrue(header.exists(), "缺少供HUD和Present共用的帧协调器")
        driver = r'''
#include "domain/runtime/render_frame_coordinator.hpp"
#include <cassert>
#include <stdexcept>
#include <vector>
using namespace isaac::runtime;
static std::vector<int> order;
static void NativeHud(void* hud) { assert(hud == reinterpret_cast<void*>(2)); order.push_back(1); }
int main() {
    RenderFrameCoordinator coordinator;
    auto mod = [&](void* manager) { assert(manager == reinterpret_cast<void*>(1)); order.push_back(2); };
    // 无Manager作用域的其它HUD调用，不能重用上一帧的Manager。
    RenderAfterNativeHud(coordinator, reinterpret_cast<void*>(2), NativeHud, mod);
    assert((order == std::vector<int>{1})); order.clear();
    for (bool paused : {false, true}) {
        RenderFrameScope frame(coordinator, reinterpret_cast<void*>(1));
        RenderAfterNativeHud(coordinator, reinterpret_cast<void*>(2), NativeHud, mod);
        order.push_back(paused ? 3 : 4); // 原生暂停/其它前景始终排在模组后面。
        assert(!coordinator.Dispatch(mod)); // Present兜底。
        assert(!coordinator.Dispatch(mod)); // Manager返回兜底。
        assert((order == std::vector<int>{1, 2, paused ? 3 : 4})); order.clear();
        RenderAfterNativeHud(coordinator, reinterpret_cast<void*>(2), NativeHud, mod);
        assert((order == std::vector<int>{1})); order.clear();
    }
    assert(coordinator.Manager() == nullptr);
    { // 局内没有HUD的帧，Present仍派发一次；菜单作用域另由scene用例拒绝。
        RenderFrameScope frame(coordinator, reinterpret_cast<void*>(1));
        assert(coordinator.Dispatch(mod)); assert(!coordinator.Dispatch(mod));
        assert((order == std::vector<int>{2})); order.clear();
    }
    { // 嵌套作用域退出恢复外层状态/Manager，不覆盖外层已派发标记。
        RenderFrameScope outer(coordinator, reinterpret_cast<void*>(1));
        { RenderFrameScope inner(coordinator, reinterpret_cast<void*>(3));
          assert(coordinator.Dispatch([](void* manager) { assert(manager == reinterpret_cast<void*>(3)); })); }
        assert(coordinator.Manager() == reinterpret_cast<void*>(1));
        assert(coordinator.Dispatch([&](void*) {
            assert(!coordinator.Dispatch(mod)); // 标记必须在Lua之前设置。
            RenderFrameScope reentrant(coordinator, reinterpret_cast<void*>(4));
            assert(!coordinator.Dispatch(mod)); // Lua递归绘制不递归派发Lua。
        }));
        assert(!coordinator.Dispatch(mod));
    }
    try { // 宿主异常退出也必须恢复作用域和派发深度。
        RenderFrameScope frame(coordinator, reinterpret_cast<void*>(1));
        coordinator.Dispatch([](void*) { throw std::runtime_error("callback"); });
    } catch (const std::runtime_error&) {}
    assert(coordinator.Manager() == nullptr);
    { RenderFrameScope frame(coordinator, reinterpret_cast<void*>(1)); assert(coordinator.Dispatch(mod)); }
    assert(!coordinator.Dispatch(mod));
}
'''
        with tempfile.TemporaryDirectory() as td:
            source, binary = Path(td) / "main.cpp", Path(td) / "probe"
            source.write_text(driver)
            result = subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror",
                                     "-I", str(ROOT / "runtime/src"), str(source), "-o", str(binary)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
