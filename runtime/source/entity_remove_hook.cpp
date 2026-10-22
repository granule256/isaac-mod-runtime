#include "entity_remove_hook.hpp"
#include "lua_runtime.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "infrastructure/memory/engine_field_access.hpp"

namespace isaac::runtime {
namespace {
void DispatchRemove(std::uintptr_t entity) noexcept {
    std::uint32_t type{}, variant{};
    const auto filter = ReadEntityIdentity(entity, &type, &variant) ? static_cast<std::int32_t>(type) : -1;
    LuaRuntime::DispatchPostEntityRemove(entity, filter);
}
}
void RunEntityRemoveIntercept(const EntityRemoveNativeBindings* native, void* entity) noexcept {
    if (native == nullptr || native->remove == nullptr) __builtin_trap();
    native->remove(entity); // PC先清Exists与设Removed，即使重复Remove仍派发。
    const auto address = engine_memory::AddressOf(entity);
    DispatchRemove(address);
    ClearEntityLifetimeData(address); // 数据在回调结束后才清；保存的Lua表仍可独立使用。
}
std::uint32_t EntityDestructorRemoveInternalCallback(relay::InternalHookContext& context,
                                                      const void* nativeBindings) noexcept {
    const auto& native = *static_cast<const EntityRemoveNativeBindings*>(nativeBindings);
    if (native.destroyRng == nullptr) __builtin_trap();
    const auto entity = context.x[19];
    // 原D2到该BL的完整路径：x8=0是原Exists=0；其余为旧Removed或刚写的1。
    if (context.x[8] != 0) DispatchRemove(entity);
    RetireEntityLifetime(entity); // 所有D2均释放data/身份，包括先显式Remove过的对象。
    native.destroyRng(engine_memory::AsObject(context.x[0]));
    return 0; // 0x58A04原析构余下步骤，原x19/栈/FP均由公共上下文恢复。
}
}
