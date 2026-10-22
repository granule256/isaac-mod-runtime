#pragma once
#include "relay/internal_hook.hpp"
namespace isaac::runtime {
struct ConsoleCommandView {
    using Print=void(*)(void*,const void*,std::uint32_t,std::uint32_t);
    const void* tokens{};
    std::size_t count{};
    void* console{};
    Print print{};
};
struct ConsoleUnknownBindings { bool compareResult{}; ConsoleCommandView::Print print{}; };
bool ReadConsoleToken(const ConsoleCommandView&, std::size_t, const char**,std::size_t*) noexcept;
std::uint32_t ConsoleUnknownInternalCallback(relay::InternalHookContext&,const void*) noexcept;
}

namespace LuaRuntime {
void DispatchExecuteCommand(const isaac::runtime::ConsoleCommandView&) noexcept;
}
