#pragma once

#include "interfaces/lua/compatibility_adapter_runtime.hpp"

namespace isaac::runtime::compatibility {

struct BuiltinAdapterDiagnostics {
    unsigned installed{}, failures{};
    int lastStatus{};
    CompatibilityAdapterId adapterId{};
    char error[128]{};
};

// A composition-root extension, not a dependency of the PC Lua runtime.
// The caller chooses whether to install it, once for each newly created VM.
void InstallBuiltinCompatibilityAdapters(lua_State* state) noexcept;
BuiltinAdapterDiagnostics GetBuiltinAdapterDiagnostics() noexcept;

} // namespace isaac::runtime::compatibility
