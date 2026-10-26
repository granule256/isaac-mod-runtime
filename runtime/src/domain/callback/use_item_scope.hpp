#pragma once

#include <cstdint>

namespace isaac::runtime {

struct UseItemCallFrame {
    std::uintptr_t player{};
    std::int32_t item{};
    std::int32_t postItem{};
    std::uint32_t flags{};
    std::int32_t slot{};
    std::int32_t custom{};
    bool dispatched{false};
    bool animationAllowed{false};
    UseItemCallFrame* previous{};
};

// 调用方仅在游戏线程维护 head；每层原生调用拥有自己的栈上帧。
class UseItemCallScope final {
public:
    UseItemCallScope(UseItemCallFrame*& head, std::uintptr_t player,
                     std::int32_t item, std::uint32_t flags,
                     std::int32_t slot, std::int32_t custom, bool mainVariant = true) noexcept
        : head_(head), frame_{player, item, item == 59 ? 34 : item,
                              flags, slot, custom, false, mainVariant && !(flags & 1U), head} {
        head_ = &frame_;
    }

    ~UseItemCallScope() noexcept { head_ = frame_.previous; }

    UseItemCallScope(const UseItemCallScope&) = delete;
    UseItemCallScope& operator=(const UseItemCallScope&) = delete;
    UseItemCallScope(UseItemCallScope&&) = delete;
    UseItemCallScope& operator=(UseItemCallScope&&) = delete;

    UseItemCallFrame& frame() noexcept { return frame_; }
    const UseItemCallFrame& frame() const noexcept { return frame_; }

private:
    UseItemCallFrame*& head_;
    UseItemCallFrame frame_;
};

inline bool TryClaimUseItemBoundary(UseItemCallFrame* head,
                                    std::uintptr_t player) noexcept {
    if (!head || head->player != player || head->item == 0 || head->dispatched)
        return false;
    // 回调可能同步重入，必须在回调开始前认领当前层，不追溯父层。
    head->dispatched = true;
    return true;
}

// 只有Blank Card原生已完成有效卡检查后、真正UseCard的这一条调用可改变资格。
inline void NoteUseItemCardAnimation(UseItemCallFrame* head, std::uintptr_t player,
    std::uint32_t card, std::uintptr_t caller, std::uintptr_t base) noexcept {
    if (head && !head->dispatched && head->item == 286 && head->player == player &&
        card == 48 && base && base <= UINTPTR_MAX - 0x310824 && caller == base + 0x310824)
        head->animationAllowed = false;
}

} // namespace isaac::runtime
