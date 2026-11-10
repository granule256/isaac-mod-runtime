#pragma once

#include "infrastructure/persistence/sd_save_file_adapter.hpp"

namespace isaac::runtime {

// Call only from an engine-owned thread, before Mod discovery and Lua startup.
// Initialisation is attempted once; failure stays visible through the SD port.
[[nodiscard]] Status InitializeSdStorage(SdSaveFileAdapter&) noexcept;

struct SdStorageState {
    std::uint64_t magic{0x31524f5453445341ULL};
    std::uint32_t version{1}, stage{}, result{}, modsOnSd{};
    std::uint64_t sdkBase{}, ownerThread{};
};
extern SdStorageState g_SdStorageState;

} // namespace isaac::runtime
