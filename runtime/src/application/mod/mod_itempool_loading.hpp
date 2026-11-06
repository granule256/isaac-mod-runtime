#pragma once

namespace isaac::runtime {
struct ModItemPoolBindings {
    using Load = void (*)(void*, const char*, bool);
    using Append = void (*)(void*);
    Load load{};
    Append append{};
};

// Complete the base pool before its caller rolls starting items or restores
// weights. Native mod loads re-enter with append=true and must not merge again.
inline void LoadItemPoolsWithMods(const ModItemPoolBindings& native, void* pool,
                                 const char* path, bool append) noexcept {
    native.load(pool, path, append);
    if (!append && native.append) native.append(pool);
}
}
