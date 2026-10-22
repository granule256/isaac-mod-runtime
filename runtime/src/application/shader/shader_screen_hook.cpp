#include "application/shader/shader_screen_hook.hpp"
#include "application/shader/shader_pipeline.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lib/util/sys/rw_pages.hpp"
#include "runtime_constants.hpp"
#include "lua_runtime.hpp"
#include <atomic>
#include <array>
#include <cstring>
namespace isaac::runtime {
namespace {
constexpr std::uintptr_t kEntry=0x4EF70C, kPlt=0x671300, kSlot=0xA9E8E8;
constexpr std::array<unsigned char,16> kEntryBytes{0x28,0x00,0x80,0x52,0x08,0xA0,0x00,0x39,0x1F,0x10,0x00,0xF9,0xC0,0x03,0x5F,0xD6};
constexpr std::array<unsigned char,16> kPltBytes{0x70,0x21,0x00,0xB0,0x11,0x76,0x44,0xF9,0x10,0xA2,0x23,0x91,0x20,0x02,0x1F,0xD6};
std::atomic<std::uintptr_t> g_Base{},g_Original{};
}
extern "C" void IsaacModRuntime_ShaderScreenIntercept(void* graphics) {
 const auto original=g_Original.load(std::memory_order_acquire);
 if(!original){__builtin_trap();}
 engine_call::AsFunction<void(*)(void*)>(original)(graphics);
 if(LuaRuntime::IsOnGameThread())static_cast<void>(CaptureShaderScreenTarget());
}
bool InstallShaderScreenHook(std::uintptr_t base) noexcept {
 if(!base||base>UINTPTR_MAX-kSlot-8||!engine_memory::EngineMemoryReadable(base+kSlot,8)||
    !engine_call::VerifyEntryBytes(base+kEntry,kEntryBytes.data(),16,engine_memory::EngineMemoryReadable)||
    !engine_call::VerifyEntryBytes(base+kPlt,kPltBytes.data(),16,engine_memory::EngineMemoryReadable)){return false;}
 auto* slot=static_cast<std::uintptr_t*>(engine_memory::AsObject(base+kSlot));
 const auto callback=engine_call::AddressOfFunction(&IsaacModRuntime_ShaderScreenIntercept);
 auto expected=__atomic_load_n(slot,__ATOMIC_ACQUIRE);
 const auto previous=g_Base.load(std::memory_order_acquire);
 if(previous==base&&expected==callback){return true;}
 if(previous&&previous!=base){return false;}
 if(expected!=base+kEntry&&expected!=base+kPltResolverOffset){return false;}
 // 发布原函数必须先于可执行的入口，避免其他线程在安装窗口读到0。
 g_Original.store(base+kEntry,std::memory_order_release);g_Base.store(base,std::memory_order_release);
 exl::util::RwPages page(base+kSlot,8);
 auto* writable=static_cast<std::uintptr_t*>(engine_memory::AsObject(page.GetRw()));
 if(!__atomic_compare_exchange_n(writable,&expected,callback,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED)){return false;}
 page.Flush();
 if(__atomic_load_n(slot,__ATOMIC_ACQUIRE)==callback){return true;}
 auto ours=callback;__atomic_compare_exchange_n(writable,&ours,expected,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED);page.Flush();return false;
}
}
