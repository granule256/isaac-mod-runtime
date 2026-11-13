#pragma once

#include "interfaces/lua/api_descriptor.hpp"
#include "interfaces/lua/engine_method_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "domain/callback/callback_descriptor.hpp"
#include <cstddef>

namespace isaac::runtime {

// A batch owns immutable descriptors and exactly one implementation per API.
// Descriptor IDs are permanent and must not alias the ordinary API catalog.
struct RepentogonApiBinding {
    LuaApiDescriptor descriptor{};
    lua_CFunction handler{};
    const FieldApiRow* field{};
    const EngineMethodRow* method{};
    bool replaceExisting{};
};
struct RepentogonEnumBinding {
    const char* table{};
    const char* name{};
    lua_Integer value{};
};
struct RepentogonCallbackBinding {
    CallbackId id{};
    const char* name{};
};
struct RepentogonBatch {
    const char* name{};
    const RepentogonApiBinding* apis{};
    std::size_t apiCount{};
    const RepentogonEnumBinding* enums{};
    std::size_t enumCount{};
    const RepentogonCallbackBinding* callbacks{};
    std::size_t callbackCount{};
    // Runs under the runtime's protected bootstrap, after ordinary types exist.
    lua_CFunction initialize{};
    // Releases native side state after lua_close, including failed initialization.
    void (*reset)() noexcept{};
    // Must verify native prerequisites without changing the engine or Lua state.
    bool (*ready)() noexcept{};
};
struct RepentogonCatalog {
    const RepentogonBatch* batches{};
    std::size_t count{};
    // Optional mod detection, published only after successful initialization.
    // Use 0.0.0 when no released upstream minimum is guaranteed; null omits it.
    const char* identityVersion{};
};

[[nodiscard]] const RepentogonCatalog& DefaultRepentogonCatalog() noexcept;

// Catalogs and all their rows must outlive the VM. Start before ordinary API
// registration, complete before author scripts. Lua failures abort that VM.
void BeginRepentogonEnvironment(lua_State*, bool requested, const RepentogonCatalog&);
void CompleteRepentogonEnvironment(lua_State*);
// Stop native event delivery before lua_close; keep object state until GC ends.
void SuspendRepentogonEnvironment(lua_State*) noexcept;
void EndRepentogonEnvironment(lua_State*) noexcept;
[[nodiscard]] bool RepentogonEnvironmentActive() noexcept;
[[nodiscard]] std::size_t AttachRepentogonOwnerMethods(lua_State*, const char* owner);

} // namespace isaac::runtime
