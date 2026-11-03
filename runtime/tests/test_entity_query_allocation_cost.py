"""真实 Lua 下验证查询分配预算、独立返回值和 lifetime 热路径。"""
from pathlib import Path
import subprocess
import tempfile
import unittest

from .test_lua_api_method_lookup_cost import function
from .test_support import lua_harness_objects, prepare_harness_directory, LUA_SOURCE_RELATIVE

ROOT = Path(__file__).resolve().parents[2]
PREFIX = r'''
#include "interfaces/lua/entity_lifetime.hpp"
#include "lua_object_handles.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lobject.h"
}
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <set>
using LuaRuntime::EntityHandle;
using LuaRuntime::kEntityMetatable;
namespace engine_memory = isaac::runtime::engine_memory;
'''


class EntityQueryAllocationCostTests(unittest.TestCase):
    def run_driver(self, body, *, include_lifetime=False):
        with tempfile.TemporaryDirectory(prefix="entity-query-allocation-") as tmp:
            work = prepare_harness_directory(Path(tmp))
            driver = work / "test.cpp"
            driver.write_text(PREFIX + body)
            objects = lua_harness_objects(ROOT / "runtime/source", work)
            sources = [driver]
            if not include_lifetime:
                sources.append(ROOT / "runtime/src/interfaces/lua/entity_lifetime.cpp")
            result = subprocess.run([
                "c++", "-std=c++23", "-Wall", "-Wextra", "-Werror",
                "-I" + str(work / "compatibility"), "-I" + str(ROOT / "runtime/source"),
                "-I" + str(ROOT / "runtime/src"),
                "-I" + str(ROOT / "runtime/source" / LUA_SOURCE_RELATIVE),
                *map(str, sources), *map(str, objects), "-o", str(work / "test"),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(work / "test")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_warm_lifetime_lookup_avoids_redundant_lua_api_lookups(self):
        # Count real Lua C API calls without replacing the map or token implementation.
        body = r'''
unsigned mainReads = 0, pointerReads = 0;
int countedRawGetI(lua_State* L, int i, lua_Integer key) {
    if (i == LUA_REGISTRYINDEX && key == LUA_RIDX_MAINTHREAD) ++mainReads;
    return lua_rawgeti(L, i, key);
}
int countedRawGetP(lua_State* L, int i, const void* key) {
    ++pointerReads;
    return lua_rawgetp(L, i, key);
}
#define lua_rawgeti countedRawGetI
#define lua_rawgetp countedRawGetP
#include "interfaces/lua/entity_lifetime.cpp"
#undef lua_rawgeti
#undef lua_rawgetp
int acquire(lua_State* L) {
    isaac::runtime::PushEntityLifetimeToken(L, 0x1234);
    return 1;
}
int main() {
    auto* L = luaL_newstate(); assert(L);
    auto* first = isaac::runtime::PushEntityLifetimeToken(L, 0x1234);
    assert(mainReads == 1);
    auto* co = lua_newthread(L);
    mainReads = pointerReads = 0;
    for (unsigned i = 0; i < 64; ++i) {
        auto* state = i % 2 ? L : co;
        const int top = lua_gettop(state);
        assert(isaac::runtime::PushEntityLifetimeToken(state, 0x1234) == first);
        assert(lua_gettop(state) == top + 1);
        lua_pop(state, 1);
    }
    if (mainReads != 0 || pointerReads != 64) {
        std::fprintf(stderr, "warm lookup: main-thread reads=%u, map/key reads=%u; expected 0/64\n", mainReads, pointerReads);
        return 1;
    }
    isaac::runtime::ResetEntityLifetimeState();
    assert(isaac::runtime::PushEntityLifetimeToken(L, 0x1234) == first);
    assert(mainReads == 1);
    // Replacing the registry map must stop reusing the previous map's token.
    lua_newtable(L);
    lua_rawsetp(L, LUA_REGISTRYINDEX, &isaac::runtime::kRegistryKey);
    assert(isaac::runtime::PushEntityLifetimeToken(L, 0x1234) != first);
    lua_pop(L, 1);
    for (unsigned kind = 0; kind < 4; ++kind) {
        lua_rawgetp(L, LUA_REGISTRYINDEX, &isaac::runtime::kRegistryKey);
        if (kind == 0) lua_pushboolean(L, true);
        else {
            auto* token = static_cast<LuaRuntime::EntityLifetimeToken*>(
                lua_newuserdata(L, sizeof(LuaRuntime::EntityLifetimeToken) + (kind == 1 ? 1 : 0)));
            *token = {kind == 2 ? 0x5678U : 0x1234U, kind != 3};
        }
        lua_rawsetp(L, -2, engine_memory::AsObject(0x1234)); lua_pop(L, 1);
        lua_pushcfunction(L, acquire);
        assert(lua_pcall(L, 0, 1, 0) == LUA_ERRRUN); lua_pop(L, 1);
    }
    isaac::runtime::ResetEntityLifetimeState(); lua_close(L);
}
'''
        self.run_driver(body, include_lifetime=True)

    def test_room_query_presizes_fresh_arrays_without_caching_entities(self):
        source = (ROOT / "runtime/src/interfaces/lua/isaac_api.cpp").read_text()
        start = source.index("constexpr std::size_t kMaximumQueryResults")
        constants = source[start:source.index("// 批次 428", start)]
        body = constants + r'''
std::set<std::uintptr_t> seen;
unsigned count = 128;
bool available = true;
constexpr int kLiveEntityTable = 0, kEffectEntityTable = 1;
void ResetQueryDedup() { seen.clear(); }
bool QueryRecordUnique(std::uintptr_t p) { return seen.insert(p).second; }
std::uintptr_t ResolveRoom() { return available ? 1 : 0; }
bool EntityListFingerprintMatches(std::uintptr_t) { return true; }
std::uintptr_t ResolveGameAddress() { return 1; }
template<class F> void ForEachEntityInTable(std::uintptr_t, int table, F visit) {
    if (table == 0) for (unsigned i = 0; i < count; ++i) visit(0x10000 + 0x100 * i);
}
template<class F> void ForEachPlayerEntity(std::uintptr_t, F visit) {
    if (count) visit(0x10000); // duplicate player/list pointer must still be deduplicated
}
const char* EntityViewMetatableForPointer(std::uintptr_t) { return kEntityMetatable; }
'''
        body += function(source, "void PushEntityHandle(") + "\n"
        body += function(source, "struct QuerySink {") + ";\n"
        body += function(source, "void PushQueryResult(") + "\n"
        body += function(source, "void ResetEntityDataStore() noexcept {") + "\n"
        body += function(source, "int IsaacGetRoomEntities(lua_State* state) {") + "\n"
        body += r'''
struct Alloc { unsigned resizes{}; };
void* allocator(void* context, void* block, size_t, size_t size) {
    if (!size) { std::free(block); return nullptr; }
    if (block) ++static_cast<Alloc*>(context)->resizes;
    return std::realloc(block, size);
}
void query(lua_State* L, unsigned n) {
    count = n; lua_pushcfunction(L, IsaacGetRoomEntities);
    assert(lua_pcall(L, 0, 1, 0) == LUA_OK);
    assert(lua_rawlen(L, -1) == (available ? n : 0));
}
int main() {
    Alloc a; auto* L = lua_newstate(allocator, &a); assert(L);
    luaL_newmetatable(L, kEntityMetatable); lua_pop(L, 1);
    lua_gc(L, LUA_GCSTOP, 0);
    query(L, 128); const void* first = lua_topointer(L, -1);
    lua_rawgeti(L, -1, 1); const void* handle = lua_topointer(L, -1); lua_pop(L, 1);
    a.resizes = 0; query(L, 128);
    if (a.resizes > 1) {
        std::fprintf(stderr, "warm 128-result query resized %u times; expected at most 1\n", a.resizes);
        return 1;
    }
    assert(lua_topointer(L, -1) != first);
    lua_rawgeti(L, -1, 1); assert(lua_topointer(L, -1) != handle); lua_pop(L, 1);
    // Removing a result from one array cannot affect the next query.
    lua_pushnil(L); lua_rawseti(L, -2, 1); query(L, 1);
    lua_rawgeti(L, -1, 1);
    auto* h = static_cast<EntityHandle*>(lua_touserdata(L, -1));
    assert(h && h->entity == engine_memory::AsObject(0x10000)); lua_pop(L, 1);
    query(L, 4096); query(L, 0);
    assert(static_cast<const Table*>(lua_topointer(L, -1))->sizearray <= 512);
    available = false; query(L, 0); query(L, 0);
    assert(static_cast<const Table*>(lua_topointer(L, -1))->sizearray == 0);
    available = true; query(L, 128); ResetEntityDataStore(); query(L, 0);
    assert(static_cast<const Table*>(lua_topointer(L, -1))->sizearray == 0);
    lua_pushcfunction(L, IsaacGetRoomEntities); lua_pushinteger(L, 1);
    assert(lua_pcall(L, 1, 1, 0) == LUA_ERRRUN); lua_pop(L, 1);
    ResetEntityDataStore(); lua_close(L);
}
'''
        self.run_driver(body)
