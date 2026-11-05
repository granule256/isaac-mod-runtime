#pragma once

#include "domain/world/world_content_changes.hpp"

struct lua_State;

namespace isaac::runtime {

using CompatibilityAdapterId = unsigned;
enum class CompatibilityAdapterResult { None, Applied, NotApplicable, Failed };

struct CompatibilityAdapterDiagnostics {
    std::uint64_t attempts{}, failures{}, applications{}, skipped{};
    int lastStatus{};
    CompatibilityAdapterResult lastResult{};
    char name[48]{};
    char error[128]{};
    char reason[128]{};
    WorldContentCursor cursor{};
};

// Copies a function into a private registry reference. New consumers start at
// the current world snapshot; registration never publishes a Lua global/API.
// Return false, reason for a non-applicable consumer; nil/true acknowledges
// application. Lua errors retain the cursor and retry independently.
bool RegisterCompatibilityAdapter(lua_State* state, const char* name, int functionIndex,
                                  CompatibilityAdapterId* id = nullptr) noexcept;
void PumpCompatibilityAdapters(lua_State* state) noexcept;
bool HasPendingCompatibilityAdapters() noexcept;
CompatibilityAdapterDiagnostics GetCompatibilityAdapterDiagnostics(CompatibilityAdapterId id) noexcept;
// Call before lua_close. Passing nullptr is valid only when no VM is retained.
void ResetCompatibilityAdapters(lua_State* state) noexcept;

} // namespace isaac::runtime
