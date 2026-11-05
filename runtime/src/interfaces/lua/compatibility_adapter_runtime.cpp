#include "interfaces/lua/compatibility_adapter_runtime.hpp"
#include "infrastructure/native/world_content_mutations.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
}
#include <cstring>

namespace isaac::runtime {
namespace {
constexpr unsigned kCapacity = 16;
struct Adapter { int reference{LUA_NOREF}; CompatibilityAdapterDiagnostics diagnostics{}; };
Adapter g_Adapters[kCapacity]{};
unsigned g_Count{};
lua_State* g_State{};
bool g_Pumping{};

template<std::size_t N>
void CopyText(char (&target)[N], const char* value) noexcept {
    if (!value) value = "";
    std::strncpy(target, value, N - 1);
    target[N - 1] = 0;
}

int RetainFunction(lua_State* state) {
    lua_pushvalue(state, 1);
    const int reference = luaL_ref(state, LUA_REGISTRYINDEX);
    lua_pushinteger(state, reference);
    return 1;
}
} // namespace

bool RegisterCompatibilityAdapter(lua_State* state, const char* name, int functionIndex,
                                  CompatibilityAdapterId* id) noexcept {
    if (!state || (g_State && g_State != state) || g_Count == kCapacity ||
        !lua_isfunction(state, functionIndex) || !lua_checkstack(state, 3)) return false;
    const int top = lua_gettop(state);
    functionIndex = lua_absindex(state, functionIndex);
    lua_pushcfunction(state, RetainFunction);
    lua_pushvalue(state, functionIndex);
    const int status = lua_pcall(state, 1, 1, 0);
    if (status != LUA_OK) { lua_settop(state, top); return false; }
    auto& adapter = g_Adapters[g_Count];
    adapter.reference = static_cast<int>(lua_tointeger(state, -1));
    adapter.diagnostics = {};
    adapter.diagnostics.cursor.snapshot = CaptureWorldContentSnapshot();
    CopyText(adapter.diagnostics.name, name);
    lua_settop(state, top);
    g_State = state;
    if (id) *id = g_Count;
    ++g_Count;
    return true;
}

bool HasPendingCompatibilityAdapters() noexcept {
    const auto snapshot = CaptureWorldContentSnapshot();
    for (unsigned i = 0; i < g_Count; ++i)
        if (ChangesSince(g_Adapters[i].diagnostics.cursor, snapshot).Any()) return true;
    return false;
}

void PumpCompatibilityAdapters(lua_State* state) noexcept {
    if (!state || state != g_State || g_Pumping || !HasPendingCompatibilityAdapters()) return;
    g_Pumping = true;
    const unsigned count = g_Count;
    for (unsigned i = 0; i < count; ++i) {
        // A preceding consumer may have changed the world scope or produced
        // more work. Never hand its stale scope to the next consumer.
        const auto snapshot = CaptureWorldContentSnapshot();
        auto& adapter = g_Adapters[i];
        auto& diagnostics = adapter.diagnostics;
        const auto changes = ChangesSince(diagnostics.cursor, snapshot);
        if (!changes.Any()) continue;
        ++diagnostics.attempts;
        if (!lua_checkstack(state, 5)) {
            ++diagnostics.failures;
            diagnostics.lastStatus = LUA_ERRMEM;
            diagnostics.lastResult = CompatibilityAdapterResult::Failed;
            diagnostics.reason[0] = 0;
            CopyText(diagnostics.error, "cannot reserve compatibility adapter stack");
            continue;
        }
        const int top = lua_gettop(state);
        lua_rawgeti(state, LUA_REGISTRYINDEX, adapter.reference);
        lua_pushboolean(state, changes.pickupsChanged);
        lua_pushboolean(state, changes.collectiblesChanged);
        lua_pushinteger(state, static_cast<lua_Integer>(snapshot.worldEpoch));
        lua_pushinteger(state, static_cast<lua_Integer>(snapshot.floorEpoch));
        diagnostics.lastStatus = lua_pcall(state, 4, 2, 0);
        if (diagnostics.lastStatus == LUA_OK) {
            diagnostics.cursor.snapshot = snapshot;
            diagnostics.error[0] = 0;
            if (lua_isboolean(state, -2) && !lua_toboolean(state, -2)) {
                ++diagnostics.skipped;
                diagnostics.lastResult = CompatibilityAdapterResult::NotApplicable;
                CopyText(diagnostics.reason, lua_type(state, -1) == LUA_TSTRING ?
                         lua_tostring(state, -1) : "compatibility adapter not applicable");
            } else {
                ++diagnostics.applications;
                diagnostics.lastResult = CompatibilityAdapterResult::Applied;
                diagnostics.reason[0] = 0;
            }
        } else {
            ++diagnostics.failures;
            diagnostics.lastResult = CompatibilityAdapterResult::Failed;
            diagnostics.reason[0] = 0;
            CopyText(diagnostics.error, lua_type(state, -1) == LUA_TSTRING ?
                     lua_tostring(state, -1) : "compatibility adapter failed");
        }
        lua_settop(state, top);
    }
    g_Pumping = false;
}

CompatibilityAdapterDiagnostics GetCompatibilityAdapterDiagnostics(CompatibilityAdapterId id) noexcept {
    return id < g_Count ? g_Adapters[id].diagnostics : CompatibilityAdapterDiagnostics{};
}

void ResetCompatibilityAdapters(lua_State* state) noexcept {
    if (g_State && state != g_State) return;
    if (state)
        for (unsigned i = 0; i < g_Count; ++i)
            luaL_unref(state, LUA_REGISTRYINDEX, g_Adapters[i].reference);
    for (auto& adapter : g_Adapters) adapter = {};
    g_Count = 0;
    g_State = nullptr;
    g_Pumping = false;
}

} // namespace isaac::runtime
