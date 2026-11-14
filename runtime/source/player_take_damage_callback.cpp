#include "player_take_damage_callback.hpp"

#include "application/callback/callback_dispatcher.hpp"

namespace isaac::runtime::player_take_damage {

bool DispatchPrePlayerTakeDamage(
    CallbackDispatcher& dispatcher, std::int32_t playerVariant) noexcept {
    const auto outcome = dispatcher.DispatchModifying(
        kPrePlayerTakeDamageCallbackId, ThreadAffinity::Any, playerVariant);
    // Lua's only non-nil falsey value is boolean false. Integers (including 0),
    // strings and tables all return true from lua_toboolean and continue.
    return outcome.failed == 0 && outcome.anyNonNil && !outcome.anyTruthy;
}

}  // namespace isaac::runtime::player_take_damage
