#pragma once

#include <cstddef>
#include <cstdint>

namespace isaac::runtime {

inline constexpr std::size_t kRuntimeFrameTraceCapacity = 512;
inline constexpr std::uint64_t kRuntimeFrameTraceMagic = 0x3145434152544652ULL;
enum class RuntimeFramePhase : unsigned { Update, Lua, Render, SubmitTail, Unknown };
enum class RuntimeFrameFinish : std::uint64_t { Deadline = 1, Capacity, Superseded, VmReset };

struct RuntimeFrameRow {
    std::uint64_t interval;
    std::uint64_t ticks[5];
    std::uint64_t gc; // Overlay: GC already included in the exclusive phase totals.
};
static_assert(sizeof(RuntimeFrameRow) == 56);

struct RuntimeFrameTrace {
    std::uint64_t completedUntil{}, count{};
    RuntimeFrameFinish reason{};
    RuntimeFrameRow rows[kRuntimeFrameTraceCapacity];
    std::uint64_t until{}, start{}, tick{}, gcStart{}, ticks[5]{};
    RuntimeFramePhase phase{RuntimeFramePhase::Unknown};
    bool active{};

    void SetPhase(RuntimeFramePhase next, std::uint64_t now) noexcept {
        ticks[static_cast<unsigned>(phase)] += now - tick;
        tick = now;
        phase = next;
    }
    RuntimeFramePhase Enter(RuntimeFramePhase next, std::uint64_t now) noexcept {
        const auto previous = phase;
        if (previous != next) SetPhase(next, now);
        return previous;
    }
    void Leave(RuntimeFramePhase previous, std::uint64_t now) noexcept {
        if (phase != previous) SetPhase(previous, now);
    }
    void BeginSubmit(std::uint64_t now) noexcept { SetPhase(RuntimeFramePhase::SubmitTail, now); }
    void Boundary(std::uint64_t now, std::uint64_t request, std::uint64_t gc) noexcept {
        if (active && (request != until || now >= until)) {
            Finish(request == until ? RuntimeFrameFinish::Deadline : RuntimeFrameFinish::Superseded);
        }
        if (!active) {
            if (request == 0 || request == completedUntil || now >= request) return;
            count = 0;
            until = request;
            active = true;
        } else {
            SetPhase(RuntimeFramePhase::Unknown, now);
            auto& row = rows[count++];
            row.interval = now - start;
            for (unsigned i = 0; i < 5; ++i) row.ticks[i] = ticks[i];
            row.gc = gc >= gcStart ? gc - gcStart : 0;
            if (count == kRuntimeFrameTraceCapacity) {
                Finish(RuntimeFrameFinish::Capacity);
                return;
            }
        }
        start = tick = now;
        gcStart = gc;
        phase = RuntimeFramePhase::Unknown;
        for (auto& value : ticks) value = 0;
    }
    void Finish(RuntimeFrameFinish why) noexcept {
        active = false;
        reason = why;
        __atomic_store_n(&completedUntil, until, __ATOMIC_RELEASE);
    }
};
static_assert(offsetof(RuntimeFrameTrace, rows) == 24);

struct RuntimeFrameTraceLayout {
    std::uint64_t magic, version, bytes, rowBytes, capacity;
    const RuntimeFrameTraceLayout* self;
    const std::uint64_t* request;
    RuntimeFrameTrace* const* trace;
};
static_assert(sizeof(RuntimeFrameTraceLayout) == 64);

} // namespace isaac::runtime
