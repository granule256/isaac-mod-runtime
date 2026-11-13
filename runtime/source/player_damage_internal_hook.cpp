#include "player_damage_internal_hook.hpp"
#include "infrastructure/memory/engine_field_access.hpp"

#include <cstring>

namespace isaac::runtime {

struct PlayerDamageCallbackState {
    std::uint64_t entries{}, dispatched{}, cancelled{}, missingContext{};
    std::uint64_t accepted{}, posted{}, whitefireSkipped{}, extraSourceOverflow{},
        extraSourceUnreadable{};
};
extern "C" { PlayerDamageCallbackState g_PlayerDamageCallbackState{}; }

std::uint32_t PlayerDamageInternalCallback(relay::InternalHookContext& context,
    const void* nativeBindings) noexcept {
    if (nativeBindings == nullptr) __builtin_trap();
    const auto& native = *static_cast<const PlayerDamageNativeBindings*>(nativeBindings);
    if (native.tryEndAstralProjection == nullptr) __builtin_trap();
    auto& state = g_PlayerDamageCallbackState;
    ++state.entries;
    auto* frame = damage::CurrentScope();
    std::int32_t hearts{};
    const bool contextMatches = frame != nullptr &&
        frame->Entity() == context.x[19] &&
        frame->OriginalSourceRef() == context.x[22];
    damage::Values values{};
    if (frame != nullptr) frame->FillValues(&values);
    if (contextMatches &&
        engine_memory::ReadField(context.originalSp, 0x4C, &hearts,
                                 engine_memory::EngineMemoryReadable)) {
        values.amount = static_cast<float>(hearts);
        values.playerDamage = hearts;
        values.damageFlags = context.x[20];
        // NS Entity_Player::TakeDamage does not consume its w3 countdown
        // argument in the accepted path (the only w3 move is the separate
        // Wisp branch at 0x2A3528/0x2A374C). REPENTOGON likewise writes the
        // entity countdown only for non-player damage. Keep the callback
        // override visible to post and, if needed, the next layer; do not
        // invent a write to +0x27C for players.
        values.countdown = frame->Countdown();
        values.entityType = 1;
        values.player = true;
        bool extraSourceOverflow = false;
        const auto extraSource =
            damage::FindExtraSource(context.x[22], &extraSourceOverflow);
        if (extraSourceOverflow) {
            values.extraSourceOverflow = true;
            values.extraSourceOverflowSource = context.x[22];
            ++state.extraSourceOverflow;
        } else if (extraSource != 0) {
            if (!frame->SetExtraSourceEntity(extraSource)) {
                values.extraSourceUnreadable = true;
                values.extraSourceOverflowSource = context.x[22];
                ++state.extraSourceUnreadable;
            } else {
                frame->FillValues(&values);
                values.amount = static_cast<float>(hearts);
                values.playerDamage = hearts;
                values.damageFlags = context.x[20];
                values.countdown = frame->Countdown();
                values.entityType = 1;
                values.player = true;
            }
        }
        ++state.dispatched;
        bool cancelled = false;
        if (values.extraSourceOverflow || values.extraSourceUnreadable) {
            // Do not turn a real-but-unrepresentable ExtraSource into nil.
            cancelled = true;
        } else if (native.dispatchPreValues != nullptr) {
            cancelled = native.dispatchPreValues(values);
        } else if (native.dispatch != nullptr) {
            cancelled = native.dispatch(context.x[19], values.amount, values.damageFlags,
                                        context.x[22], values.countdown, values.entityType);
        }
        // Apply the fields that are actually live at the accepted boundary.
        context.x[20] = values.damageFlags;
        std::memcpy(engine_memory::AsObject(context.originalSp + 0x4C),
                    &values.playerDamage, sizeof(values.playerDamage));
        if (cancelled) {
            ++state.cancelled;
            return 1;
        }
    } else {
        // Never invent a countdown for an unmatched or unreadable native frame.
        ++state.missingContext;
    }
    const bool astral = native.tryEndAstralProjection(
        engine_memory::AsObject(context.x[0]));
    context.x[0] = astral ? 1U : 0U;
    if (!astral && contextMatches) {
        const auto extraSource = damage::FindExtraSource(context.x[22]);
        static_cast<void>(frame->MarkAccepted(
            values.amount, values.playerDamage, values.damageFlags, context.x[22],
            values.countdown, extraSource, values.entityType,
            values.extraSourceOverflow, values.extraSourceUnreadable));
        ++state.accepted;
    }
    return 0;
}

void DispatchPlayerDamagePost(bool succeeded,
                              const PlayerDamageNativeBindings& bindings) noexcept {
    if (!succeeded) return;
    damage::Values values{};
    if (!damage::TakeCurrentAccepted(&values)) return;
    if (values.extraSourceOverflow || values.extraSourceUnreadable) return;
    if (damage::IsWhitefireSource(values)) {
        ++g_PlayerDamageCallbackState.whitefireSkipped;
        return;
    }
    if (bindings.dispatchPostValues == nullptr) return;
    ++g_PlayerDamageCallbackState.posted;
    bindings.dispatchPostValues(values);
}

} // namespace isaac::runtime
