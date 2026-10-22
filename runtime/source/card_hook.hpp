#pragma once
#include "ports/hook_port.hpp"
namespace isaac::runtime {
struct CardNativeBindings {
    using GetCard=std::uint32_t (*)(const void*,std::uint32_t,bool,bool,bool);
    using Construct=void (*)(void*,std::uint32_t,std::uint32_t);
    using Destroy=void (*)(void*);
    GetCard getCard{};Construct construct{};Destroy destroy{};
};
std::uint32_t RunCardIntercept(const CardNativeBindings*,const void*,std::uint32_t,bool,bool,bool) noexcept;
Status InstallCardPointerHook(const HookTarget&) noexcept;
// Lua主动抽卡必须经过同一已登记GOT拦截，不能直接调用basic绕过20号事件。
CardNativeBindings::GetCard ResolveCardApiEntry(std::uintptr_t moduleBase) noexcept;
}
