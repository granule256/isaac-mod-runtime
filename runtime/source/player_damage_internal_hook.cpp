#include "player_damage_internal_hook.hpp"
#include "infrastructure/memory/engine_field_access.hpp"

namespace isaac::runtime {
namespace {
// Managed native damage runs on the game thread; every nested native call owns
// its frame and restores the previous one before returning.
PlayerDamageCallScope* s_CurrentScope{};
}

struct PlayerDamageCallbackState {
    std::uint64_t entries{}, dispatched{}, cancelled{}, missingContext{};
};
extern "C" { PlayerDamageCallbackState g_PlayerDamageCallbackState{}; }

PlayerDamageCallScope::PlayerDamageCallScope(std::uintptr_t player,
    std::uintptr_t source, std::int32_t countdown) noexcept
    : previous_(s_CurrentScope), player_(player), source_(source), countdown_(countdown) {
    s_CurrentScope = this;
}

PlayerDamageCallScope::~PlayerDamageCallScope() noexcept {
    if (s_CurrentScope != this) __builtin_trap();
    s_CurrentScope = previous_;
}

std::uint32_t PlayerDamageInternalCallback(relay::InternalHookContext& context,
    const void* nativeBindings) noexcept {
    if (nativeBindings == nullptr) __builtin_trap();
    const auto& native = *static_cast<const PlayerDamageNativeBindings*>(nativeBindings);
    if (native.tryEndAstralProjection == nullptr) __builtin_trap();
    auto& state = g_PlayerDamageCallbackState;
    ++state.entries;
    const auto* frame = s_CurrentScope;
    std::int32_t hearts{};
    if (frame != nullptr && frame->player_ == context.x[19] &&
        frame->source_ == context.x[22] && native.dispatch != nullptr &&
        engine_memory::ReadField(context.originalSp, 0x4C, &hearts,
                                 engine_memory::EngineMemoryReadable)) {
        ++state.dispatched;
        if (native.dispatch(context.x[19], static_cast<float>(hearts), context.x[20],
                            context.x[22], frame->countdown_, 1)) {
            ++state.cancelled;
            return 1;
        }
    } else {
        // Never invent a countdown for an unmatched or unreadable native frame.
        ++state.missingContext;
    }
    context.x[0] = native.tryEndAstralProjection(engine_memory::AsObject(context.x[0])) ? 1U : 0U;
    return 0;
}

} // namespace isaac::runtime
