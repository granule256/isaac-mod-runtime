#pragma once

#include <cstddef>
#include <cstdint>

namespace isaac::runtime {

struct UseItemImageOverlay {
    std::uintptr_t source{};
    std::uint32_t original{};
};

// An integration authenticates its installed code before the whole-function
// guard hashes the corresponding original instruction. Installation only.
using UseItemImageVerifier = bool (*)(const std::uint8_t*, std::size_t,
                                     UseItemImageOverlay*) noexcept;
inline UseItemImageVerifier& UseItemImageVerifierSlot() noexcept {
    static UseItemImageVerifier verifier{};
    return verifier;
}
inline void SetUseItemImageVerifier(UseItemImageVerifier verifier) noexcept {
    UseItemImageVerifierSlot() = verifier;
}

} // namespace isaac::runtime
