#pragma once

#include <cstdint>

namespace isaac::runtime {

enum class WorldContentMutation : unsigned { PickupsRerolled, CollectiblesRerolled };

struct WorldContentSnapshot {
    std::uint64_t worldEpoch{}, floorEpoch{}, version{}, scopeStartVersion{};
    std::uint64_t pickupsVersion{}, collectiblesVersion{};
};

struct WorldContentCursor { WorldContentSnapshot snapshot{}; };

struct WorldContentChanges {
    bool pickupsChanged{}, collectiblesChanged{};
    constexpr bool Any() const noexcept { return pickupsChanged || collectiblesChanged; }
};

constexpr WorldContentChanges ChangesSince(const WorldContentCursor& cursor,
                                           const WorldContentSnapshot& snapshot) noexcept {
    const bool sameScope = cursor.snapshot.worldEpoch == snapshot.worldEpoch &&
                           cursor.snapshot.floorEpoch == snapshot.floorEpoch;
    const auto after = sameScope ? cursor.snapshot.version : snapshot.scopeStartVersion;
    return {snapshot.pickupsVersion > after, snapshot.collectiblesVersion > after};
}

} // namespace isaac::runtime
