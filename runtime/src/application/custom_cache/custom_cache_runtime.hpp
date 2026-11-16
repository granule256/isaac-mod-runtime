#pragma once

#include "application/custom_cache/custom_cache.hpp"

#include <span>
#include <string_view>

namespace isaac::runtime::custom_cache {

// The private native adapter fills this bridge from Configure(). Dispatch Event
// 1224 remains parent-owned through Port::evaluate.
struct RuntimeBridge {
    Port port{};
    std::uintptr_t (*primaryPlayer)(void* user) noexcept{};
    void (*afterBatch)(
        void* user, std::uintptr_t player,
        const EvaluationBatch& batch) noexcept{};
    bool (*requestEvaluateItems)(
        void* user, std::uintptr_t player) noexcept{};
};

bool ConfigureRuntimeBridge(const RuntimeBridge* bridge) noexcept;
void ClearRuntimeBridge() noexcept;
[[nodiscard]] Store& SharedStore() noexcept;

void AddCustomCacheTagForPlayer(
    std::uintptr_t player, std::span<const std::string_view> tags,
    bool immediate);
EvaluationBatch EvaluateCustomCacheItemsForPlayer(
    std::uintptr_t player, std::uint32_t cacheFlags);
EvaluationBatch TriggerItemCustomCacheForPlayer(
    std::uintptr_t player, ItemKind kind, std::int32_t id, bool immediate);
double GetCustomCacheValueForPlayer(
    std::uintptr_t player, std::string_view tag);
std::int32_t GetConsumableMaximumForPlayer(
    std::uintptr_t player, std::string_view tag);
void ResetCustomCachePlayers() noexcept;
void ClearCustomCacheXmlTags() noexcept;
void ResetCustomCacheRuntime() noexcept;

}  // namespace isaac::runtime::custom_cache
