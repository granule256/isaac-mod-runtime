#include "card_hook.hpp"
#include "lua_runtime.hpp"
namespace isaac::runtime {
std::uint32_t RunCardIntercept(const CardNativeBindings* native,const void* pool,
    std::uint32_t seed,bool playing,bool runes,bool onlyRunes) noexcept {
    if(!native||!native->getCard)__builtin_trap();
    const auto selected=native->getCard(pool,seed,playing,runes,onlyRunes);
    if(!LuaRuntime::CanDispatchGetCard())return selected;
    if(!native->construct||!native->destroy)__builtin_trap();
    alignas(16) std::uint8_t rng[16]{};
    native->construct(rng,seed,35);
    const auto result=LuaRuntime::DispatchGetCard(rng,selected,playing,runes,onlyRunes);
    // Lua分配及转换错误均由派发保护桥截住；析构不跨越longjmp。
    native->destroy(rng);
    return result;
}
}
