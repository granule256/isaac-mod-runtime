#include "notice_integrity.hpp"
#include <new>

#if defined(__SWITCH__)
extern "C" {
#include <switch/crypto/sha256.h>
}
#elif defined(__APPLE__)
#define CC_IGNORE_DEPRECATION
#include <CommonCrypto/CommonDigest.h>
#else
#define OPENSSL_SUPPRESS_DEPRECATED
#include <openssl/sha.h>
#endif

namespace isaac::runtime::notice::integrity {
namespace {
#if defined(__SWITCH__)
using NativeContext = Sha256Context;
#elif defined(__APPLE__)
using NativeContext = CC_SHA256_CTX;
#else
using NativeContext = SHA256_CTX;
#endif
static_assert(sizeof(NativeContext) <= 256, "SHA context exceeds fixed storage");
static_assert(alignof(NativeContext) <= 16, "SHA context alignment exceeds storage");
}
Sha256::Sha256() noexcept {
    auto* context = ::new (static_cast<void*>(storage_)) NativeContext{};
#if defined(__SWITCH__)
    sha256ContextCreate(context);
#elif defined(__APPLE__)
    CC_SHA256_Init(context);
#else
    SHA256_Init(context);
#endif
}
void Sha256::Update(const void* data, std::size_t size) noexcept {
    auto* context = std::launder(reinterpret_cast<NativeContext*>(storage_));
#if defined(__SWITCH__)
    sha256ContextUpdate(context, data, size);
#elif defined(__APPLE__)
    // CC_LONG is 32 bit; retain streaming correctness for any caller size.
    auto* bytes = static_cast<const unsigned char*>(data);
    while (size) {
        const auto chunk = static_cast<CC_LONG>(size > 0xffffffffu ? 0xffffffffu : size);
        CC_SHA256_Update(context, bytes, chunk);
        bytes += chunk;
        size -= chunk;
    }
#else
    SHA256_Update(context, data, size);
#endif
}
Digest Sha256::Finish() noexcept {
    Digest digest{};
    auto* context = std::launder(reinterpret_cast<NativeContext*>(storage_));
#if defined(__SWITCH__)
    sha256ContextGetHash(context, digest.data());
#elif defined(__APPLE__)
    CC_SHA256_Final(digest.data(), context);
#else
    SHA256_Final(digest.data(), context);
#endif
    return digest;
}
}
