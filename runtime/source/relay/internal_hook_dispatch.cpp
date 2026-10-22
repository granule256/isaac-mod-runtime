#include "relay/internal_hook.hpp"
#include "infrastructure/memory/engine_field_access.hpp"

extern "C" void isaac_internal_hook_dispatch(isaac::runtime::relay::InternalHookContext* context) {
    using namespace isaac::runtime::relay;
    // 这是本模块发布的不可变绑定地址，不是未经核验的引擎对象地址。
    const auto* binding = static_cast<const InternalHookBinding*>(isaac::runtime::engine_memory::AsObject(context->binding));
    const auto selected = binding->callback(*context, binding->user);
    if (selected >= binding->resumeCount) __builtin_trap();
    context->continuation = binding->resumes[selected];
}
