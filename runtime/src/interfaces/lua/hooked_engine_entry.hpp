#pragma once

#include "infrastructure/call/engine_call_access.hpp"
#include "relay/entry_relay.hpp"
#include <array>

namespace isaac::runtime {

// 原入口或本运行时已安装的中继均可调用；调用公开入口保留模组伤害回调。
// 中继必须指向登记的槽，回放完整原序言并准确跳回本函数，不能只接受跳转指令。
[[nodiscard]] inline bool VerifiedHookedEngineEntry(
    std::uintptr_t address, const std::array<std::uint8_t, 16>& original,
    bool installed, std::uintptr_t fallback, engine_call::ReadableCheck readable) noexcept {
    if (engine_call::VerifyEntryBytes(address, original.data(), original.size(), readable))
        return true;
    if (!installed || fallback < relay::kSlotFallbackOffset ||
        address > UINTPTR_MAX - relay::kOriginalEntryBytes) return false;
    std::array<std::uint8_t, relay::kEntryPatchBytes> patch{};
    std::array<std::uint8_t, relay::kSlotBytes> slot{};
    relay::BuildEntryPatch(patch.data(), fallback - relay::kSlotFallbackOffset);
    relay::BuildSlotImage(slot.data(), address, original.data(), 0);
    return engine_call::VerifyEntryBytes(address, patch.data(), patch.size(), readable) &&
           engine_call::VerifyEntryBytes(fallback, slot.data() + relay::kSlotFallbackOffset,
               relay::kSlotBytes - relay::kSlotFallbackOffset, readable);
}

} // namespace isaac::runtime
