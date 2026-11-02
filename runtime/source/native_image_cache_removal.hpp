#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

struct TargetModule;
namespace isaac::runtime {
struct ImageCacheEntry { void* image; void* control; };
struct ImageCacheBucket { ImageCacheEntry* begin; ImageCacheEntry* end; ImageCacheEntry* capacity; };
static_assert(sizeof(ImageCacheEntry)==16 && sizeof(ImageCacheBucket)==24);

// Caller holds the image-manager mutex and has validated the vector. Moving
// these two-word owners transfers ownership; only the erased owner is released.
// Keep that owner alive through native bookkeeping, which still reads its path.
template<class Cleanup,class Release>
bool DetachImageCacheEntry(ImageCacheBucket& bucket,void* image,Cleanup cleanup,Release release) {
    ImageCacheEntry removed{};
    bool found=false;
    for(auto* at=bucket.begin;at!=bucket.end;++at) {
        if(at->image!=image)continue;
        removed=*at;
        std::memmove(at,at+1,static_cast<std::size_t>(bucket.end-at-1)*sizeof(*at));
        --bucket.end;
        found=true;
        break;
    }
    cleanup();
    if(found)release(removed);
    return found;
}
bool InstallNativeImageCacheRemovalFix(const TargetModule&) noexcept;
bool NativeImageCacheRemovalFixReady() noexcept;
}
