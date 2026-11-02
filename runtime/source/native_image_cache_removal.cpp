#include "native_image_cache_removal.hpp"
#if defined(__SWITCH__)
#include "module_finder.hpp"
#include "runtime_constants.hpp"
#include "relay/entry_relay.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <array>
#include <atomic>

namespace isaac::runtime {
extern "C" {
__attribute__((visibility("hidden"))) std::atomic<std::uint64_t> g_ImageCacheRemovalState[4]{}; // installed/calls/detached/guard-failures
}
namespace {
constexpr std::uintptr_t kRemove=0x4d32f8,kRemoveEnd=0x4d3644;
constexpr std::array<unsigned char,16> kRemoveBytes{0xff,0x03,0x02,0xd1,0xfd,0x7b,0x02,0xa9,0xfd,0x83,0x00,0x91,0xfc,0x6f,0x03,0xa9};
struct Entry {std::uintptr_t offset;std::array<unsigned char,16> bytes;};
constexpr Entry kLock{0x670580,{0x70,0x21,0x00,0xd0,0x11,0x16,0x41,0xf9,0x10,0xa2,0x08,0x91,0x20,0x02,0x1f,0xd6}};
constexpr Entry kUnlock{0x670590,{0x70,0x21,0x00,0xd0,0x11,0x1a,0x41,0xf9,0x10,0xc2,0x08,0x91,0x20,0x02,0x1f,0xd6}};
constexpr Entry kPath{0x670550,{0x70,0x21,0x00,0xd0,0x11,0x0a,0x41,0xf9,0x10,0x42,0x08,0x91,0x20,0x02,0x1f,0xd6}};
constexpr Entry kHash{0x680450,{0x30,0x21,0x00,0xd0,0x11,0xca,0x40,0xf9,0x10,0x42,0x06,0x91,0x20,0x02,0x1f,0xd6}};
std::atomic<std::uintptr_t> g_Original{};
std::uintptr_t g_Base{},g_NotifySlot{},g_BucketCountSlot{};
using Remove=void(*)(void*,void*);
template<class T> bool Read(std::uintptr_t address,T* out) noexcept {
    return engine_memory::ReadAt(address,out,engine_memory::EngineMemoryReadable);
}
template<class F> F Method(const Entry& entry) noexcept {return engine_call::AsFunction<F>(g_Base+entry.offset);}
bool Publish(std::uintptr_t original,void*) noexcept {
    g_Original.store(original,std::memory_order_release);return original!=0;
}
}
extern "C" void IsaacModRuntime_RemoveImageCacheEntry(void* manager,void* image) {
    const auto address=g_Original.load(std::memory_order_acquire);
    if(!address)__builtin_trap();
    const auto original=engine_call::AsFunction<Remove>(address);
    g_ImageCacheRemovalState[1].fetch_add(1,std::memory_order_relaxed);
    if(!image){original(manager,image);return;}
    auto* mutex=static_cast<unsigned char*>(manager)+8;
    Method<void(*)(void*,unsigned)>(kLock)(mutex,~0U);
    std::uintptr_t table{};
    std::uint32_t count{};
    const auto path=Method<const char*(*)(void*)>(kPath)(image);
    const bool ready=Read(g_BucketCountSlot,&count)&&count&&Read(engine_memory::AddressOf(manager),&table)&&table;
    ImageCacheBucket* bucket=nullptr;
    if(ready) {
        const auto index=Method<unsigned(*)(const char*,bool)>(kHash)(path,false)%count;
        if(table<=UINTPTR_MAX-std::size_t(index)*sizeof(ImageCacheBucket)) {
            const auto slot=table+std::size_t(index)*sizeof(ImageCacheBucket);
            ImageCacheBucket view{};
            if(Read(slot,&view)) {
                const auto begin=engine_memory::AddressOf(view.begin),end=engine_memory::AddressOf(view.end),capacity=engine_memory::AddressOf(view.capacity);
                if(begin<=end&&end<=capacity&&(end-begin)%sizeof(ImageCacheEntry)==0&&
                   engine_memory::EngineMemoryWritable(slot,sizeof(view))&&
                   (begin==end||engine_memory::EngineMemoryWritable(begin,end-begin)))
                    bucket=static_cast<ImageCacheBucket*>(engine_memory::AsObject(slot));
            }
        }
    }
    if(bucket) {
        const bool detached=DetachImageCacheEntry(*bucket,image,[&]{original(manager,image);},[](ImageCacheEntry removed) {
            if(!removed.control)return;
            // The native bucket owned this pair; use its real virtual decrement
            // and current notification callback, exactly as its destructor does.
            std::uintptr_t vtable{},decrement{};
            if(!Read(engine_memory::AddressOf(removed.control),&vtable)||!Read(vtable+0x20,&decrement)||!decrement)__builtin_trap();
            if(engine_call::AsFunction<bool(*)(void*)>(decrement)(removed.control)) {
                std::uintptr_t notify{};
                if(!Read(g_NotifySlot,&notify))__builtin_trap();
                if(notify)engine_call::AsFunction<void(*)(ImageCacheEntry*)>(notify)(&removed);
            }
        });
        if(detached)g_ImageCacheRemovalState[2].fetch_add(1,std::memory_order_relaxed);
    } else {
        g_ImageCacheRemovalState[3].fetch_add(1,std::memory_order_relaxed);
        original(manager,image);
    }
    Method<void(*)(void*)>(kUnlock)(mutex);
}
bool NativeImageCacheRemovalFixReady() noexcept {return g_ImageCacheRemovalState[0].load(std::memory_order_acquire)==1;}
bool InstallNativeImageCacheRemovalFix(const TargetModule& module) noexcept {
    if(NativeImageCacheRemovalFixReady())return g_Base==module.base;
    if(!module.base||module.buildId!=kTargetBuildId||!module.Contains(module.base+kRemove,kRemoveEnd-kRemove))return false;
    if(!engine_memory::EngineMemoryReadable(module.base+kRemove,kRemoveEnd-kRemove))return false;
    const auto* bytes=static_cast<const unsigned char*>(engine_memory::AsObject(module.base+kRemove));
    std::uint64_t hash=0xcbf29ce484222325ULL;
    for(std::size_t i=0;i<kRemoveEnd-kRemove;++i)hash=(hash^bytes[i])*0x100000001b3ULL;
    if(hash!=0xb55392b73d27e3e2ULL)return false;
    for(const auto* entry:{&kLock,&kUnlock,&kPath,&kHash})
        if(!module.Contains(module.base+entry->offset,16)||!engine_call::VerifyEntryBytes(module.base+entry->offset,entry->bytes.data(),16,engine_memory::EngineMemoryReadable))return false;
    std::uintptr_t notify{},count{};
    if(!Read(module.base+0xaac6a8,&notify)||!notify||!Read(module.base+0xaad518,&count)||!count)return false;
    g_Base=module.base;g_NotifySlot=notify;g_BucketCountSlot=count;
    if(!relay::TryInstallEntryRelayWithPublisher(module.base+kRemove,kRemoveBytes.data(),
        engine_call::AddressOfFunction(&IsaacModRuntime_RemoveImageCacheEntry),Publish,nullptr))return false;
    g_ImageCacheRemovalState[0].store(1,std::memory_order_release);return true;
}
}
#else
namespace isaac::runtime {
bool NativeImageCacheRemovalFixReady() noexcept {return false;}
bool InstallNativeImageCacheRemovalFix(const TargetModule&) noexcept {return false;}
}
#endif
