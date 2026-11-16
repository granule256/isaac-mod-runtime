#include "application/custom_cache/custom_cache_runtime.hpp"

#include <utility>

namespace isaac::runtime::custom_cache {
namespace {

RuntimeBridge g_Bridge{};
Store* g_Store{};

std::uintptr_t PrimaryPlayer(const RuntimeBridge& bridge) noexcept {
    return bridge.primaryPlayer != nullptr
               ? bridge.primaryPlayer(bridge.port.user)
               : 0;
}

void AfterBatch(
    const RuntimeBridge& bridge, std::uintptr_t player,
    const EvaluationBatch& batch) noexcept {
    if (bridge.afterBatch != nullptr) {
        bridge.afterBatch(bridge.port.user, player, batch);
    }
}

EvaluationBatch Finish(
    const RuntimeBridge& bridge, std::uintptr_t player,
    EvaluationBatch batch, bool immediate) {
    AfterBatch(bridge, player, batch);
    if (immediate && batch.requiresEvaluateItems &&
        bridge.requestEvaluateItems != nullptr) {
        static_cast<void>(bridge.requestEvaluateItems(bridge.port.user, player));
    }
    return batch;
}

}  // namespace

bool ConfigureRuntimeBridge(const RuntimeBridge* bridge) noexcept {
    if (bridge == nullptr) {
        ClearRuntimeBridge();
        return false;
    }
    g_Bridge = *bridge;
    return true;
}

void ClearRuntimeBridge() noexcept {
    g_Bridge = {};
}

Store& SharedStore() noexcept {
    if (g_Store == nullptr) g_Store = new Store;
    return *g_Store;
}

void AddCustomCacheTagForPlayer(
    std::uintptr_t player, std::span<const std::string_view> tags,
    bool immediate) {
    SharedStore().QueueTags(player, tags);
    if (immediate && g_Bridge.requestEvaluateItems != nullptr) {
        static_cast<void>(g_Bridge.requestEvaluateItems(g_Bridge.port.user, player));
    }
}

EvaluationBatch EvaluateCustomCacheItemsForPlayer(
    std::uintptr_t player, std::uint32_t cacheFlags) {
    auto& store = SharedStore();
    if ((cacheFlags & kCacheAll) != kCacheAll && !store.HasWork(player)) return {};
    auto batch = store.EvaluateItems(
        player, cacheFlags, PrimaryPlayer(g_Bridge), g_Bridge.port);
    AfterBatch(g_Bridge, player, batch);
    return batch;
}

EvaluationBatch TriggerItemCustomCacheForPlayer(
    std::uintptr_t player, ItemKind kind, std::int32_t id, bool immediate) {
    auto& store = SharedStore();
    if (store.ItemTags(kind, id).empty()) return {};
    auto batch = store.TriggerItemTags(
        player, kind, id, immediate, PrimaryPlayer(g_Bridge), g_Bridge.port);
    return Finish(g_Bridge, player, std::move(batch), immediate);
}

double GetCustomCacheValueForPlayer(
    std::uintptr_t player, std::string_view tag) {
    return SharedStore().GetCustomCacheValue(player, tag, g_Bridge.port);
}

std::int32_t GetConsumableMaximumForPlayer(
    std::uintptr_t player, std::string_view tag) {
    return SharedStore().GetConsumableMaximum(player, tag, g_Bridge.port);
}

void ResetCustomCachePlayers() noexcept {
    if (g_Store != nullptr) g_Store->ResetPlayers();
}

void ClearCustomCacheXmlTags() noexcept {
    if (g_Store != nullptr) g_Store->Reset();
}

void ResetCustomCacheRuntime() noexcept {
    ClearCustomCacheXmlTags();
    ClearRuntimeBridge();
}

}  // namespace isaac::runtime::custom_cache
