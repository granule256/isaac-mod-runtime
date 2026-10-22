#include "application/shader/native_clear_probe.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "interfaces/lua/runtime_perf.hpp"
#include "lib/util/sys/rw_pages.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"
#include <atomic>
#include <array>
namespace isaac::runtime {
__attribute__((visibility("hidden"))) std::uint64_t g_NativeShaderClearDetail[2][3][3]{};
__attribute__((visibility("hidden"))) std::uint32_t g_NativeShaderClearDetailInstallState{};
namespace {
struct Import {std::uintptr_t plt,slot;std::array<unsigned char,16> bytes;};
constexpr Import kImports[]{
 {0x681300,0xAA68E8,{48,33,0,176,17,118,68,249,16,162,35,145,32,2,31,214}},
 {0x681120,0xAA67F8,{48,33,0,176,17,254,67,249,16,226,31,145,32,2,31,214}},
 {0x681390,0xAA6930,{48,33,0,176,17,154,68,249,16,194,36,145,32,2,31,214}}
};
std::atomic<std::uintptr_t> g_Original[3]{};
std::atomic<std::uintptr_t> g_Base{};
int g_ClearScope=-1; // 只有游戏线程读写；其它线程必须先经IsOnGameThread拒绝。
int CurrentScope() noexcept {return LuaRuntime::IsOnGameThread()?g_ClearScope:-1;}
void Note(int scope,unsigned metric,std::uint64_t start) noexcept {
 const auto spent=RuntimePerfTick()-start;
 auto* row=g_NativeShaderClearDetail[scope][metric];++row[0];row[1]+=spent;if(spent>row[2])row[2]=spent;
}
template<unsigned Metric>void QueueIntercept(void* object) {
 const auto original=g_Original[Metric].load(std::memory_order_acquire);
 if(!original)__builtin_trap(); // 入口发布前必须先发布原函数。
 const int scope=CurrentScope();
 if(scope<0){engine_call::AsFunction<void(*)(void*)>(original)(object);return;}
 const auto start=RuntimePerfTick();engine_call::AsFunction<void(*)(void*)>(original)(object);Note(scope,Metric,start);
}
void* AcquireIntercept(void* object) {
 const auto original=g_Original[2].load(std::memory_order_acquire);if(!original)__builtin_trap();
 const int scope=CurrentScope();
 if(scope<0)return engine_call::AsFunction<void*(*)(void*)>(original)(object);
 const auto start=RuntimePerfTick();void* result=engine_call::AsFunction<void*(*)(void*)>(original)(object);Note(scope,2,start);return result;
}
std::uintptr_t Callback(unsigned i) noexcept {
 if(i==0)return engine_call::AddressOfFunction(&QueueIntercept<0>);
 if(i==1)return engine_call::AddressOfFunction(&QueueIntercept<1>);
 return engine_call::AddressOfFunction(&AcquireIntercept);
}
}
NativeClearProbeScope::NativeClearProbeScope(bool offscreen) noexcept:previous_(-1),active_(LuaRuntime::IsOnGameThread()) {
 if(active_){previous_=g_ClearScope;g_ClearScope=offscreen?0:1;}
}
NativeClearProbeScope::~NativeClearProbeScope(){if(active_)g_ClearScope=previous_;}
bool InstallNativeClearProbe(std::uintptr_t base) noexcept {
 // 安装只发生在FrameInfo的游戏线程；原子槽使其它渲染线程始终透传。
 if(!LuaRuntime::IsOnGameThread())return false;
 const auto previous=g_Base.load(std::memory_order_acquire);
 if(!base||base>UINTPTR_MAX-0xAA6938||(previous&&previous!=base)){
  g_NativeShaderClearDetailInstallState=2;return false;
 }
 if(previous==base&&g_NativeShaderClearDetailInstallState==4)return true;
 std::uintptr_t originals[3]{};bool installed=true;
 // 全部守卫和快照先完成，任一lazy槽均不修改任何槽。
 for(unsigned i=0;i<3;++i){const auto& imp=kImports[i];
  if(!engine_memory::EngineMemoryReadable(base+imp.slot,sizeof(std::uintptr_t))||
     !engine_call::VerifyEntryBytes(base+imp.plt,imp.bytes.data(),imp.bytes.size(),engine_memory::EngineMemoryReadable)){
   g_NativeShaderClearDetailInstallState=2;return false;
  }
  originals[i]=__atomic_load_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(base+imp.slot)),__ATOMIC_ACQUIRE);
  if(originals[i]!=Callback(i))installed=false;
 }
 if(installed&&previous==base){g_NativeShaderClearDetailInstallState=4;return true;}
 for(unsigned i=0;i<3;++i){
  if(originals[i]==base+kPltResolverOffset){g_NativeShaderClearDetailInstallState=1;return false;}
  if(!originals[i]||originals[i]==base+kImports[i].plt||originals[i]==Callback(i)){
   g_NativeShaderClearDetailInstallState=2;return false;
  }
 }
 // 所有原函数均先发布；安装失败也不能清空，已进入wrapper的线程可能仍在运行。
 for(unsigned i=0;i<3;++i)g_Original[i].store(originals[i],std::memory_order_release);
 g_Base.store(base,std::memory_order_release);
 unsigned changed=0;
 for(;changed<3;++changed){const auto address=base+kImports[changed].slot;
  exl::util::RwPages page(address,sizeof(std::uintptr_t));
  auto* writable=static_cast<std::uintptr_t*>(engine_memory::AsObject(page.GetRw()));
  auto expected=originals[changed];
  if(!__atomic_compare_exchange_n(writable,&expected,Callback(changed),false,__ATOMIC_RELEASE,__ATOMIC_RELAXED))break;
  page.Flush();
 }
 if(changed==3){
  bool ready=true;for(unsigned i=0;i<3;++i)if(__atomic_load_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(base+kImports[i].slot)),__ATOMIC_ACQUIRE)!=Callback(i))ready=false;
  if(ready){g_NativeShaderClearDetailInstallState=4;return true;}
 }
 while(changed){--changed;exl::util::RwPages page(base+kImports[changed].slot,sizeof(std::uintptr_t));
  auto* writable=static_cast<std::uintptr_t*>(engine_memory::AsObject(page.GetRw()));auto expected=Callback(changed);
  __atomic_compare_exchange_n(writable,&expected,originals[changed],false,__ATOMIC_RELEASE,__ATOMIC_RELAXED);page.Flush();
 }
 g_NativeShaderClearDetailInstallState=3;return false;
}
}
