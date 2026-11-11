#pragma once

#include "interfaces/lua/runtime_perf.hpp"

#include <cstring>

namespace isaac::runtime {

inline constexpr std::uint64_t kRuntimePerfSnapshotMagic = 0x3150414e53504652ULL;
inline constexpr std::uint64_t kRuntimePerfSnapshotTiming = 1;
inline constexpr std::uint64_t kRuntimePerfSnapshotReady = 2;
inline constexpr std::uint64_t kRuntimePerfSnapshotApiWrappers = 4;
inline constexpr std::uint64_t kRuntimePerfSnapshotAttribution = 8;

[[nodiscard]] constexpr bool RuntimePerfAttributionActive(std::uint64_t until,
                                                         std::uint64_t now) noexcept {
    return now != 0 && now < until;
}

// Versioned wire layout. Capture only on request, on the VM owner thread.
struct RuntimePerfSnapshotHeader {
    std::uint64_t magic, version, headerBytes, bucketBytes;
    std::uint64_t callbackCapacity, apiCapacity, sequence, tick, tickFrequency;
    std::uint64_t generation, nativeCycles, logicCycles;
    std::uint64_t callbackCalls, callbackTicks, callbackOverflow;
    std::uint64_t apiCalls, apiTicks, apiOverflow, syscalls, syscallTicks;
    std::uint64_t gcTicks, gcSteps, gcCycles, gcMaxFrame, gcHeap, gcDebt;
    std::uint64_t flags, errors;
};

struct RuntimePerfSnapshot {
    RuntimePerfSnapshotHeader header;
    RuntimePerfCallbackBucket callbacks[kRuntimePerfBucketCount];
    RuntimePerfCallbackBucket apis[kRuntimePerfApiBucketCount];
};

inline constexpr std::uint64_t kRuntimePerfLayoutMagic = 0x3154594c465052ULL;

// Live pointers bind external writes to this image's actual layout, not merely
// to unchanged code prefixes in a possibly stale ELF.
struct RuntimePerfLayout {
    std::uint64_t magic, version, descriptorBytes, snapshotBytes;
    std::uint64_t headerBytes, bucketBytes, callbackCapacity, apiCapacity;
    std::uint64_t ownerCount, ownerStride;
    const RuntimePerfLayout* self;
    const std::uint64_t* request;
    const std::uint64_t* done;
    const std::uint64_t* attributionUntil;
    const RuntimePerfSnapshot* snapshot;
    const char* owners;
};

static_assert(sizeof(RuntimePerfSnapshotHeader) == 28 * 8);
static_assert(sizeof(RuntimePerfCallbackBucket) == 48);
static_assert(sizeof(RuntimePerfLayout) == 16 * 8);

inline void CopyRuntimePerfSnapshot(RuntimePerfSnapshot& snapshot,
                                    RuntimePerfSnapshotHeader header,
                                    const RuntimePerfCallbackBucket* callbacks,
                                    const RuntimePerfCallbackBucket* apis) noexcept {
    header.magic = kRuntimePerfSnapshotMagic;
    header.version = 1;
    header.headerBytes = sizeof(header);
    header.bucketBytes = sizeof(RuntimePerfCallbackBucket);
    header.callbackCapacity = kRuntimePerfBucketCount;
    header.apiCapacity = kRuntimePerfApiBucketCount;
    snapshot.header = header;
    std::memcpy(snapshot.callbacks, callbacks, sizeof(snapshot.callbacks));
    std::memcpy(snapshot.apis, apis, sizeof(snapshot.apis));
}

} // namespace isaac::runtime
