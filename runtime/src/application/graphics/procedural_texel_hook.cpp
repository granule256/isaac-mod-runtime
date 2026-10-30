#include "application/graphics/procedural_texel_readback.hpp"
#if defined(__SWITCH__)
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lib/util/sys/rw_pages.hpp"
#include "runtime_constants.hpp"
#include <atomic>
#include <array>
#include <cstring>
namespace isaac::runtime {
__attribute__((visibility("hidden"))) std::uint64_t g_ProceduralTexelReadback[4]{}; // calls/enabled/failures/install-state
namespace {
constexpr std::uintptr_t kCreate=0x4453E8,kPlt=0x677930,kSlot=0xAA1C00,kEnable=0x4F5BA0;
constexpr std::array<unsigned char,16> kCreateBytes{0xea,0x0f,0x18,0xfc,0xe9,0x23,0x01,0x6d,0xfd,0x7b,0x02,0xa9,0xfd,0x83,0x00,0x91};
constexpr std::array<unsigned char,16> kPltBytes{0x50,0x21,0x00,0xd0,0x11,0x02,0x46,0xf9,0x10,0x02,0x30,0x91,0x20,0x02,0x1f,0xd6};
constexpr std::array<unsigned char,16> kEnableBytes{0xff,0x43,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf7,0x13,0x00,0xf9};
std::atomic<std::uintptr_t> g_Base{},g_Original{};
bool Read(std::uintptr_t address,void*out,std::size_t size){
 if(!out||!engine_memory::EngineMemoryReadable(address,size))return false;
 std::memcpy(out,engine_memory::AsObject(address),size);return true;
}
void Enable(std::uintptr_t image,bool enabled){
 const auto base=g_Base.load(std::memory_order_acquire);
 engine_call::AsFunction<void(*)(void*,bool)>(base+kEnable)(engine_memory::AsObject(image),enabled);
}
constexpr ProceduralTexelBackend kBackend{Read,Enable};
}
extern "C" std::int32_t IsaacModRuntime_CreateProceduralItemWithCpuPixels(
 void* manager,std::uint32_t seed,std::uint32_t flags){
 const auto original=g_Original.load(std::memory_order_acquire);if(!original)__builtin_trap();
 const auto result=PrepareProceduralItemReadback(engine_memory::AddressOf(manager),kBackend);
 ++g_ProceduralTexelReadback[0];g_ProceduralTexelReadback[1]+=result.enabled;g_ProceduralTexelReadback[2]+=result.failed;
 // Orig owns generation, offscreen Present, CPU copy/sync and object lifetimes.
 return engine_call::AsFunction<std::int32_t(*)(void*,std::uint32_t,std::uint32_t)>(original)(manager,seed,flags);
}
bool InstallProceduralTexelReadbackHook(std::uintptr_t base) noexcept {
 if(!base||base>UINTPTR_MAX-kSlot-8||!engine_memory::EngineMemoryReadable(base+kSlot,8)||
    !engine_call::VerifyEntryBytes(base+kCreate,kCreateBytes.data(),16,engine_memory::EngineMemoryReadable)||
    !engine_call::VerifyEntryBytes(base+kEnable,kEnableBytes.data(),16,engine_memory::EngineMemoryReadable)||
    !engine_call::VerifyEntryBytes(base+kPlt,kPltBytes.data(),16,engine_memory::EngineMemoryReadable)){g_ProceduralTexelReadback[3]=2;return false;}
 auto* slot=static_cast<std::uintptr_t*>(engine_memory::AsObject(base+kSlot));
 const auto callback=engine_call::AddressOfFunction(&IsaacModRuntime_CreateProceduralItemWithCpuPixels);
 auto expected=__atomic_load_n(slot,__ATOMIC_ACQUIRE);const auto previous=g_Base.load(std::memory_order_acquire);
 if(previous==base&&expected==callback)return true;
 if((previous&&previous!=base)||(expected!=base+kCreate&&expected!=base+kPltResolverOffset)){g_ProceduralTexelReadback[3]=3;return false;}
 g_Original.store(base+kCreate,std::memory_order_release);g_Base.store(base,std::memory_order_release);
 exl::util::RwPages page(base+kSlot,8);auto* writable=static_cast<std::uintptr_t*>(engine_memory::AsObject(page.GetRw()));
 if(!__atomic_compare_exchange_n(writable,&expected,callback,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED)){g_ProceduralTexelReadback[3]=3;return false;}
 page.Flush();const bool installed=__atomic_load_n(slot,__ATOMIC_ACQUIRE)==callback;
 g_ProceduralTexelReadback[3]=installed?1:3;return installed;
}
}
#else
namespace isaac::runtime {bool InstallProceduralTexelReadbackHook(std::uintptr_t) noexcept{return false;}}
#endif
