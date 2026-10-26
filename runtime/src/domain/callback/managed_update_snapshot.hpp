#pragma once
#include <cstdint>
namespace isaac::runtime {
struct ManagedUpdateSnapshot {
    std::uintptr_t game{};
    std::uint32_t frame{};
};
}
