#include "application/custom_cache/custom_cache.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>

namespace isaac::runtime::custom_cache {
namespace {

constexpr std::string_view kFamiliarMultiplier = "familiarmultiplier";
constexpr std::string_view kMaxCoins = "maxcoins";
constexpr std::string_view kMaxKeys = "maxkeys";
constexpr std::string_view kMaxBombs = "maxbombs";
constexpr std::string_view kTearsCap = "tearscap";
constexpr std::string_view kStatMultiplier = "statmultiplier";
constexpr std::string_view kHealthType = "healthtype";
constexpr std::int32_t kDeepPockets = 416;

bool IsSpace(char value) noexcept { return value == ' '; }

std::int32_t ItemId(ItemKind kind, std::int32_t id) noexcept {
    constexpr auto kTrinketIdMask = 0x7FFF;
    return kind == ItemKind::Trinket ? id & kTrinketIdMask : id;
}

}  // namespace

std::string NormalizeTag(std::string_view tag) {
    std::string normalized(tag);
    for (char& value : normalized) {
        if (value >= 'A' && value <= 'Z') {
            value = static_cast<char>(value - 'A' + 'a');
        }
    }
    return normalized;
}

std::int32_t ClampMaximum(double value) noexcept {
    if (!std::isfinite(value)) return 0;
    const auto bounded = std::clamp(
        value, 0.0,
        static_cast<double>(std::numeric_limits<std::int32_t>::max()));
    return static_cast<std::int32_t>(bounded);
}

Store::Store() { Reset(); }

void Store::Reset() {
    knownTags_.clear();
    itemTags_.clear();
    ResetPlayers();
    for (const auto tag : {
             kFamiliarMultiplier, kMaxCoins, kMaxKeys, kMaxBombs,
             kTearsCap, kStatMultiplier}) {
        knownTags_.emplace(tag);
    }
    // Like PC REPENTOGON, re-evaluate the coin cap when Deep Pockets changes.
    RegisterItemTags(ItemKind::Collectible, kDeepPockets, kMaxCoins);
}

void Store::ResetPlayers() noexcept {
    players_.clear();
    maximums_ = {};
}

bool Store::RegisterTag(std::string_view tag) {
    auto normalized = NormalizeTag(tag);
    if (normalized.empty()) return false;
    return knownTags_.insert(std::move(normalized)).second;
}

std::size_t Store::RegisterTags(std::string_view spaceSeparated) {
    std::size_t added{};
    std::size_t cursor{};
    while (cursor < spaceSeparated.size()) {
        while (cursor < spaceSeparated.size() &&
               IsSpace(spaceSeparated[cursor])) {
            ++cursor;
        }
        const auto begin = cursor;
        while (cursor < spaceSeparated.size() &&
               !IsSpace(spaceSeparated[cursor])) {
            ++cursor;
        }
        if (cursor > begin &&
            RegisterTag(spaceSeparated.substr(begin, cursor - begin))) {
            ++added;
        }
    }
    return added;
}

std::size_t Store::RegisterItemTags(
    ItemKind kind, std::int32_t id, std::string_view spaceSeparated) {
    if (spaceSeparated.empty()) return 0;
    auto& tags = itemTags_[{kind, ItemId(kind, id)}];
    std::size_t added{};
    std::size_t cursor{};
    while (cursor < spaceSeparated.size()) {
        while (cursor < spaceSeparated.size() &&
               IsSpace(spaceSeparated[cursor])) {
            ++cursor;
        }
        const auto begin = cursor;
        while (cursor < spaceSeparated.size() &&
               !IsSpace(spaceSeparated[cursor])) {
            ++cursor;
        }
        if (cursor == begin) continue;
        auto normalized =
            NormalizeTag(spaceSeparated.substr(begin, cursor - begin));
        if (normalized.empty()) continue;
        knownTags_.insert(normalized);
        if (tags.insert(std::move(normalized)).second) ++added;
    }
    return added;
}

bool Store::RemoveItemTags(ItemKind kind, std::int32_t id) {
    return itemTags_.erase({kind, ItemId(kind, id)}) != 0;
}

const std::set<std::string>& Store::ItemTags(
    ItemKind kind, std::int32_t id) const {
    const auto found = itemTags_.find({kind, ItemId(kind, id)});
    return found == itemTags_.end() ? emptyItemTags_ : found->second;
}

bool Store::IsGlobalMaximum(std::string_view tag) noexcept {
    return tag == kMaxCoins || tag == kMaxKeys || tag == kMaxBombs;
}

double Store::DefaultValue(
    std::uintptr_t player, std::string_view tag, const Port& port) const {
    if (port.defaultValue != nullptr) {
        const auto supplied = port.defaultValue(port.user, player, tag);
        if (std::isfinite(supplied)) return supplied;
    }
    if (tag == kMaxCoins || tag == kMaxKeys || tag == kMaxBombs) return 99.0;
    if (tag == kTearsCap) return 5.0;
    if (tag == kStatMultiplier) return 1.0;
    return 0.0;
}

Evaluation Store::EvaluateOne(
    std::uintptr_t player, std::uintptr_t primaryPlayer,
    std::string_view tag, const Port& port, EvaluationBatch* batch) {
    auto normalized = NormalizeTag(tag);
    auto target = player;
    if (IsGlobalMaximum(normalized) && primaryPlayer != 0) {
        target = primaryPlayer;
        for (auto& [otherPlayer, other] : players_) {
            static_cast<void>(otherPlayer);
            other.pending.erase(normalized);
        }
    }

    auto& state = players_[player];
    const auto initial = DefaultValue(player, normalized, port);
    double previous = initial;
    const auto previousResult = state.results.find(normalized);
    if (previousResult != state.results.end()) previous = previousResult->second;

    double value = initial;
    if (normalized == kFamiliarMultiplier) {
        if (port.invalidateFamiliarMultipliers != nullptr) {
            port.invalidateFamiliarMultipliers(port.user, target);
        }
        value = 0.0;
    } else if (port.evaluate != nullptr) {
        double replacement{};
        if (port.evaluate(port.user, target, normalized, initial, &replacement) &&
            std::isfinite(replacement)) {
            value = replacement;
        }
    }
    state.results[normalized] = value;
    const bool changed = value != previous;
    if (normalized == kMaxCoins) {
        maximums_.maxCoins = ClampMaximum(value);
        maximums_.coinsConfigured = true;
    } else if (normalized == kMaxKeys) {
        maximums_.maxKeys = ClampMaximum(value);
        maximums_.keysConfigured = true;
    } else if (normalized == kMaxBombs) {
        maximums_.maxBombs = ClampMaximum(value);
        maximums_.bombsConfigured = true;
    } else if (normalized == kHealthType) {
        if (port.healthTypeEnforced != nullptr) {
            port.healthTypeEnforced(port.user, target);
        }
    } else if (normalized == kTearsCap && changed) {
        state.cacheFlags |= kCacheFireDelay;
        state.requiresEvaluateItems = true;
    } else if (normalized == kStatMultiplier && changed) {
        state.cacheFlags |= kCacheStats;
        state.requiresEvaluateItems = true;
    }
    if (IsGlobalMaximum(normalized) && port.maximumsChanged != nullptr) {
        port.maximumsChanged(port.user, target, normalized, maximums_);
    }

    if (batch != nullptr) {
        if (state.cacheFlags != 0) batch->cacheFlags |= state.cacheFlags;
        batch->requiresEvaluateItems =
            batch->requiresEvaluateItems || state.requiresEvaluateItems;
    }
    return {std::move(normalized), target, previous, value, changed};
}

void Store::QueueTags(
    std::uintptr_t player, std::span<const std::string_view> tags) {
    if (tags.empty()) return;
    auto& pending = players_[player].pending;
    for (const auto tag : tags) pending.insert(NormalizeTag(tag));
}

EvaluationBatch Store::AddCustomCacheTag(
    std::span<const std::string_view> tags, bool immediate,
    std::uintptr_t player, std::uintptr_t primaryPlayer,
    const Port& port) {
    EvaluationBatch batch;
    if (tags.empty()) return batch;
    if (!immediate) {
        QueueTags(player, tags);
        auto& state = players_[player];
        state.shouldEvaluateCache = true;
        ++state.deferredEpoch;
        batch.shouldEvaluateCache = true;
        return batch;
    }

    std::set<std::string> requested;
    for (const auto tag : tags) requested.insert(NormalizeTag(tag));
    auto& state = players_[player];
    for (const auto& tag : requested) {
        state.pending.erase(tag);
        batch.evaluations.push_back(
            EvaluateOne(player, primaryPlayer, tag, port, &batch));
    }
    return batch;
}

EvaluationBatch Store::EvaluateItems(
    std::uintptr_t player, std::uint32_t cacheFlags,
    std::uintptr_t primaryPlayer, const Port& port) {
    EvaluationBatch batch;
    const bool all = (cacheFlags & kCacheAll) == kCacheAll;
    if (!all && !players_.contains(player)) return batch;
    auto& state = players_[player];
    if (all) {
        state.pending.insert(knownTags_.begin(), knownTags_.end());
    }
    if (state.cacheFlags != 0) batch.cacheFlags |= state.cacheFlags;
    batch.requiresEvaluateItems = state.requiresEvaluateItems;
    const auto deferredEpoch = state.deferredEpoch;

    std::set<std::string> pending;
    pending.swap(state.pending);
    for (const auto& tag : pending) {
        batch.evaluations.push_back(
            EvaluateOne(player, primaryPlayer, tag, port, &batch));
    }

    state.cacheFlags = 0;
    state.requiresEvaluateItems = false;
    if (state.deferredEpoch == deferredEpoch) {
        state.shouldEvaluateCache = false;
    } else {
        batch.shouldEvaluateCache = true;
    }
    return batch;
}

EvaluationBatch Store::TriggerItemTags(
    std::uintptr_t player, ItemKind kind, std::int32_t id,
    bool immediate, std::uintptr_t primaryPlayer, const Port& port) {
    const auto& tags = ItemTags(kind, id);
    std::vector<std::string_view> views;
    views.reserve(tags.size());
    for (const auto& tag : tags) views.emplace_back(tag);
    return AddCustomCacheTag(
        views, immediate, player, primaryPlayer, port);
}

double Store::GetCustomCacheValue(
    std::uintptr_t player, std::string_view tag, const Port& port) const {
    const auto state = players_.find(player);
    if (state != players_.end()) {
        const auto result = state->second.results.find(tag);
        if (result != state->second.results.end()) return result->second;
    }
    return DefaultValue(player, tag, port);
}

std::int32_t Store::GetConsumableMaximum(
    std::uintptr_t player, std::string_view tag, const Port& port) const {
    if (tag == kMaxCoins && maximums_.coinsConfigured) return maximums_.maxCoins;
    if (tag == kMaxKeys && maximums_.keysConfigured) return maximums_.maxKeys;
    if (tag == kMaxBombs && maximums_.bombsConfigured) return maximums_.maxBombs;
    return ClampMaximum(DefaultValue(player, tag, port));
}

bool Store::HasPending(std::uintptr_t player) const {
    const auto state = players_.find(player);
    return state != players_.end() && !state->second.pending.empty();
}

bool Store::HasWork(std::uintptr_t player) const {
    const auto state = players_.find(player);
    return state != players_.end() &&
           (!state->second.pending.empty() || state->second.cacheFlags != 0 ||
            state->second.shouldEvaluateCache);
}

bool Store::ShouldEvaluateCache(std::uintptr_t player) const {
    const auto state = players_.find(player);
    return state != players_.end() && state->second.shouldEvaluateCache;
}

}  // namespace isaac::runtime::custom_cache
