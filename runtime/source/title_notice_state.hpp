#pragma once

#include <cstdint>

#include "runtime_settings_ui.hpp"

namespace isaac::runtime::notice {

enum Key : unsigned {
    Confirm = 1U, Back = 2U, Left = 4U, Right = 8U,
    Up = 16U, Down = 32U, Previous = 64U, Next = 128U,
};
enum class Phase : unsigned { Hidden, Opening, Reading, FlipOut, FlipIn, Closing };
// A pointer table would be relocated into mutable data outside the immutable
// policy range. Keep phase-to-animation selection entirely in read-only bytes.
inline constexpr char kPhaseAnimationNames[6][8]{"", "Open", "Idle", "FlipOut", "FlipIn", "Close"};
inline constexpr unsigned kHoldTicks = 60;
inline constexpr unsigned kOpenTicks = 20;
inline constexpr unsigned kCloseTicks = 20;
inline constexpr unsigned kFlipTicks = 6;

// Game-thread state only. Animation time advances in Update, never in Render.
// Input edges are retained through transitions, so an opening/closing key cannot
// also activate the underlying title menu or flip several pages while held.
struct State {
    Phase phase{Phase::Hidden};
    unsigned page{}, phaseTicks{}, holdTicks{};
    bool focused{}, requiresHold{};

    void SetSeenVersion(bool seen) noexcept { seenKnown_ = true; seen_ = seen; }
    void ResetForLanguage() noexcept {
        // Version acknowledgement survives translations; reading progress does
        // not, since different languages can have different page counts.
        acknowledged_ = manualCloseRequested_ = false;
        viewedPages_ = page = phaseTicks = holdTicks = targetPage_ = 0;
        settings_.Reset(lastKeys_);
        focused = false;
        if (phase != Phase::Hidden) Open(requiresHold, lastKeys_);
        else blockThisTick_ = false;
    }
    bool AllPagesViewed(unsigned count) const noexcept {
        if (count == 0 || count > 32) return false;
        const auto required = count == 32 ? UINT32_MAX : (std::uint32_t{1} << count) - 1U;
        return (viewedPages_ & required) == required;
    }
    std::uint32_t ViewedPagesMask() const noexcept { return viewedPages_; }
    bool BlocksTitleConfirm() const noexcept { return blockThisTick_ || confirmLatch_; }
    [[nodiscard]] const title::State& Settings() const noexcept { return settings_; }
    [[nodiscard]] title::State& Settings() noexcept { return settings_; }
    bool ConsumeAcknowledgement() noexcept {
        const bool result = acknowledged_;
        acknowledged_ = false;
        return result;
    }

    void Tick(unsigned keys, bool title, bool ready, unsigned pageCount) noexcept {
        const unsigned pressed = keys & ~lastKeys_;
        lastKeys_ = keys;
        if (!(keys & Confirm)) confirmLatch_ = false;
        if (!title) {
            phase = Phase::Hidden;
            focused = false;
            holdTicks = phaseTicks = 0;
            blockThisTick_ = confirmLatch_ = false;
            manualCloseRequested_ = false;
            settings_.Reset(keys);
            return;
        }
        settings_.Tick(title, ready && seenKnown_ && pageCount != 0, phase != Phase::Hidden, keys);
        focused = settings_.focus() == title::Focus::Notice;
        const auto settingsAction = settings_.PeekAction();
        if (settingsAction == title::Action::OpenNotice) {
            static_cast<void>(settings_.ConsumeAction());
            Open(false, keys);
            // The old hidden-entry branch opened and returned in the same switch
            // iteration. Do not advance the opening animation a second time in
            // this tick, or a queued B tap closes one frame early.
            settings_.Tick(true, true, true, keys);
            blockThisTick_ = true;
            return;
        }
        blockThisTick_ = phase != Phase::Hidden || settings_.BlocksTitleInput();
        if (!ready || !seenKnown_ || pageCount == 0) return;
        if (!autoEvaluated_) {
            autoEvaluated_ = true;
            if (!seen_) Open(true, keys);
        }
        if (phase != Phase::Hidden) {
            settings_.Tick(true, true, true, keys);
            focused = false;
        }
        blockThisTick_ = phase != Phase::Hidden || settings_.BlocksTitleInput();
        if (phase != Phase::Hidden && (keys & Confirm)) confirmLatch_ = true;
        if (!(keys & Back)) backArmed_ = true;
        if (!requiresHold && backArmed_ && (pressed & Back) &&
            (phase == Phase::Opening || phase == Phase::FlipOut || phase == Phase::FlipIn)) {
            manualCloseRequested_ = true;
        }

        switch (phase) {
        case Phase::Hidden:
            break;
        case Phase::Opening:
            if (++phaseTicks >= kOpenTicks) { phase = Phase::Reading; phaseTicks = 0; }
            break;
        case Phase::Reading:
            if (page < 32) viewedPages_ |= std::uint32_t{1} << page;
            if (backArmed_ && (keys & Back) && (!requiresHold || AllPagesViewed(pageCount))) {
                ++holdTicks;
                if ((!requiresHold && (pressed & Back)) || holdTicks >= kHoldTicks) {
                    phase = Phase::Closing;
                    phaseTicks = 0;
                    break;
                }
            } else holdTicks = 0;
            if (pressed & (Left | Previous | Right | Next)) {
                const bool before = (pressed & (Left | Previous)) != 0;
                const bool after = (pressed & (Right | Next)) != 0;
                if (before != after && ((before && page > 0) || (after && page + 1 < pageCount))) {
                    targetPage_ = before ? page - 1 : page + 1;
                    phase = Phase::FlipOut;
                    phaseTicks = holdTicks = 0;
                }
            }
            break;
        case Phase::FlipOut:
            if (++phaseTicks >= kFlipTicks) {
                page = targetPage_; phase = Phase::FlipIn; phaseTicks = 0;
            }
            break;
        case Phase::FlipIn:
            if (++phaseTicks >= kFlipTicks) { phase = Phase::Reading; phaseTicks = 0; }
            break;
        case Phase::Closing:
            if (++phaseTicks >= kCloseTicks) {
                acknowledged_ = requiresHold;
                focused = !requiresHold;
                if (focused) settings_.ReturnFromNotice(keys);
                requiresHold = false;
                phase = Phase::Hidden;
                phaseTicks = holdTicks = 0;
            }
            break;
        }
        if (phase == Phase::Reading && page < 32) viewedPages_ |= std::uint32_t{1} << page;
        // Finish both halves of a flip before honoring a queued manual tap.
        // A held B keeps the request, but cannot bypass automatic hold timing.
        if (phase == Phase::Reading && manualCloseRequested_) {
            manualCloseRequested_ = false;
            phase = Phase::Closing;
            phaseTicks = holdTicks = 0;
        }
    }

private:
    void Open(bool automatic, unsigned keys) noexcept {
        phase = Phase::Opening;
        requiresHold = automatic;
        backArmed_ = (keys & Back) == 0;
        manualCloseRequested_ = false;
        viewedPages_ = 0;
        phaseTicks = holdTicks = page = 0;
        blockThisTick_ = true;
        if (keys & Confirm) confirmLatch_ = true;
    }
    unsigned lastKeys_{}, targetPage_{};
    std::uint32_t viewedPages_{};
    bool seenKnown_{}, seen_{}, autoEvaluated_{}, backArmed_{};
    bool acknowledged_{}, blockThisTick_{}, confirmLatch_{}, manualCloseRequested_{};
    title::State settings_{};
};

} // namespace isaac::runtime::notice
