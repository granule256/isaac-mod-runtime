#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
namespace isaac::runtime {
struct ModRoomLoadBindings {
    using Load = bool (*)(void*, int, int);
    using Append = void (*)(void*, int, int);
    Load load{};
    Append append{};
};
// 本体失败保持失败；成功后才合并模组，调用者随后才能查询完整房间集合。
inline bool LoadStageRoomsWithMods(const ModRoomLoadBindings& native, void* config,
                                  int stage, int mode) noexcept {
    const bool loaded = native.load(config, stage, mode);
    if (loaded && native.append) native.append(config, stage, mode);
    return loaded;
}

// A stage's base RoomSet can be loaded while the runtime is still assembling
// the later mods' real ModEntry objects. Keep those stage/mode pairs and replay
// the native room merge after the content cycle has finished.
class ModRoomPendingLoads {
public:
    static constexpr int kStageCount = 37;
    static constexpr int kModeCount = 3;

    bool Add(int stage, int mode) noexcept {
        const int modeSlot = ModeSlot(mode);
        if (stage < 0 || stage >= kStageCount || modeSlot < 0) return false;
        Entry& entry = entries_[Slot(stage, modeSlot)];
        if (entry.pending) return true;
        entry = Entry{stage, mode, true};
        ++size_;
        return true;
    }

    bool Remove(int stage, int mode) noexcept {
        const int modeSlot = ModeSlot(mode);
        if (stage < 0 || stage >= kStageCount || modeSlot < 0) return false;
        Entry& entry = entries_[Slot(stage, modeSlot)];
        if (!entry.pending) return false;
        entry = Entry{};
        --size_;
        return true;
    }

    bool Peek(int* stage, int* mode) const noexcept {
        if (stage == nullptr || mode == nullptr) return false;
        for (const Entry& entry : entries_) {
            if (!entry.pending) continue;
            *stage = entry.stage;
            *mode = entry.mode;
            return true;
        }
        return false;
    }

    bool Empty() const noexcept { return size_ == 0; }
    std::size_t Size() const noexcept { return size_; }

    void Clear() noexcept {
        entries_ = {};
        size_ = 0;
    }

private:
    struct Entry {
        int stage{};
        int mode{};
        bool pending{};
    };

    static constexpr int ModeSlot(int mode) noexcept {
        switch (mode) {
            case -1: return 0;
            case 0: return 1;
            case 1: return 2;
            default: return -1;
        }
    }

    static constexpr std::size_t Slot(int stage, int modeSlot) noexcept {
        return static_cast<std::size_t>(stage) * kModeCount +
               static_cast<std::size_t>(modeSlot);
    }

    std::array<Entry, static_cast<std::size_t>(kStageCount) * kModeCount> entries_{};
    std::size_t size_{};
};
}
