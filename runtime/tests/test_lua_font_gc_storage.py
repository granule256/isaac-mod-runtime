"""真实 Lua 5.3.3 的字体记账、GC 压力与 OOM 生命周期回归。"""
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_lua_font_resources import HARNESS, SOURCE
    from .test_support import build_lua_harness
except ImportError:
    from test_lua_font_resources import HARNESS, SOURCE
    from test_support import build_lua_harness


STORAGE_HARNESS = r'''
#include <string>
#include "interfaces/lua/font_api.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"
extern "C" {
#include <lauxlib.h>
}

static std::size_t Bytes(lua_State* state) {
    return static_cast<std::size_t>(lua_gc(state, LUA_GCCOUNT, 0)) * 1024 +
           static_cast<std::size_t>(lua_gc(state, LUA_GCCOUNTB, 0));
}
static void Collect(lua_State* state) {
    lua_gc(state, LUA_GCCOLLECT, 0);
    lua_gc(state, LUA_GCCOLLECT, 0);
}
static void Prepare(lua_State* state) {
    luaL_newmetatable(state, LuaRuntime::kFontMetatable);
    lua_pushcfunction(state, isaac::runtime::DestroyFontHandle);
    lua_setfield(state, -2, "__gc");
    lua_pop(state, 1);
    lua_checkstack(state, 128);
    Collect(state);
}
static int Make(lua_State* state) {
    lua_pushcfunction(state, isaac::runtime::CreateFontHandle);
    return lua_pcall(state, 0, 1, 0);
}
static bool Valid(lua_State* state, int index) {
    auto* handle = static_cast<LuaRuntime::FontHandle*>(luaL_checkudata(
        state, index, LuaRuntime::kFontMetatable));
    if (handle->font == nullptr || reinterpret_cast<std::uintptr_t>(handle->font) % 16) return false;
    // 访问整个引擎对象首尾，确保对象没有越出 userdata 的有效载荷。
    auto* bytes = static_cast<unsigned char*>(handle->font);
    bytes[kFontObjectSize - 1] = 0xAB;
    return static_cast<FakeFont*>(handle->font)->magic == kFakeFontMagic &&
           bytes[kFontObjectSize - 1] == 0xAB;
}
struct Allocator {
    std::size_t live = 0;
    int failAfter = -1;
    bool shift = false;
    std::size_t limit = static_cast<std::size_t>(-1);
};
static void* Allocate(void* context, void* pointer, std::size_t oldSize, std::size_t newSize) {
    auto* alloc = static_cast<Allocator*>(context);
    if (newSize == 0) {
        if (pointer) {
            alloc->live -= oldSize;
            std::free(*(static_cast<void**>(pointer) - 1));
        }
        return nullptr;
    }
    if (alloc->live + newSize - (pointer ? oldSize : 0) > alloc->limit) return nullptr;
    if (alloc->failAfter == 0) return nullptr;
    if (alloc->failAfter > 0) --alloc->failAfter;
    void* base = std::malloc(newSize + 32);
    if (!base) return nullptr;
    // 两种底层地址交替出现，覆盖 userdata 只对齐 8 字节的情形。
    auto* result = static_cast<unsigned char*>(base) + (alloc->shift ? 8 : 16);
    alloc->shift = !alloc->shift;
    *(reinterpret_cast<void**>(result) - 1) = base;
    if (pointer) {
        std::memcpy(result, pointer, oldSize < newSize ? oldSize : newSize);
        alloc->live -= oldSize;
        std::free(*(static_cast<void**>(pointer) - 1));
    }
    alloc->live += newSize;
    return result;
}
int main(int argc, char** argv) {
    if (argc != 2) return 90;
    PublishFakeBindings();
    if (std::strcmp(argv[1], "accounting") == 0) {
        auto* state = luaL_newstate();
        Prepare(state);
        lua_gc(state, LUA_GCSTOP, 0);
        const auto before = Bytes(state);
        void* context = nullptr;
        const auto allocator = lua_getallocf(state, &context);
        void* direct = allocator(context, nullptr, 0, kFontObjectSize);
        if (!direct) return 1;
        const auto directDelta = Bytes(state) - before;
        allocator(context, direct, kFontObjectSize, 0);
        if (directDelta != 0) return 2;
        if (Make(state) != LUA_OK) return 3;
        const auto fontDelta = Bytes(state) - before;
        std::printf("direct_allocator_delta=%zu font_delta=%zu required=%zu\n",
                    directDelta, fontDelta, kFontObjectSize);
        if (fontDelta < kFontObjectSize) return 4;
        if (!Valid(state, 1)) return 5;
        lua_close(state);
        return g_ctorCalls == 1 && g_dtorCalls == 1 ? 0 : 6;
    }
    if (std::strcmp(argv[1], "bounded") == 0) {
        Allocator bounded{};
        bounded.limit = 8 * 1024 * 1024;
        auto* limited = lua_newstate(Allocate, &bounded);
        Prepare(limited);
        // 模组常驻数据约占堆的一半；保留引用，正常GC不可回收它。
        std::string persistent(4 * 1024 * 1024, 'x');
        lua_pushlstring(limited, persistent.data(), persistent.size());
        const auto baseline = Bytes(limited);
        int maximumLive = 0;
        for (int i = 0; i < 2048; ++i) {
            if (Make(limited) != LUA_OK) {
                std::printf("bounded_oom_at=%d font_live=%d lua_bytes=%zu physical=%zu\n",
                    i, g_ctorCalls-g_dtorCalls, Bytes(limited), bounded.live);
                lua_close(limited);
                return 51;
            }
            lua_pop(limited, 1);
            if (lua_rawlen(limited, 1) != persistent.size()) return 52;
            const int live = g_ctorCalls-g_dtorCalls;
            if (live > maximumLive) maximumLive = live;
        }
        lua_close(limited);
        if (bounded.live != 0 || g_ctorCalls != g_dtorCalls) return 53;
        std::printf("bounded_font_peak=%d baseline=%zu created=%d destroyed=%d\n",
            maximumLive,baseline,g_ctorCalls,g_dtorCalls);
        return 0;
    }
    Allocator allocator{};
    auto* state = lua_newstate(Allocate, &allocator);
    Prepare(state);
    if (std::strcmp(argv[1], "pressure") == 0) {
        const auto baseline = Bytes(state);
        const auto actualBaseline = allocator.live;
        lua_gc(state, LUA_GCSTOP, 0);
        for (int i = 0; i < 32; ++i) {
            if (Make(state) != LUA_OK || !Valid(state, -1)) return 10;
        }
        const auto held = Bytes(state);
        if (held - baseline < 32 * kFontObjectSize) return 11;
        Collect(state);
        if (g_dtorCalls != 0) return 12;
        for (int i = 1; i <= 32; ++i) if (!Valid(state, i)) return 13;
        lua_settop(state, 0);
        Collect(state);
        const auto reclaimed = Bytes(state);
        const auto actualReclaimed = allocator.live;
        if (g_ctorCalls != 32 || g_dtorCalls != 32 ||
            reclaimed > baseline + 1024 || actualReclaimed > actualBaseline + 1024) return 14;
        if (Make(state) != LUA_OK) return 15;
        lua_gc(state, LUA_GCRESTART, 0);
        int peakLive = 0;
        for (int i = 0; i < 2048; ++i) {
            if (Make(state) != LUA_OK || !Valid(state, -1)) return 16;
            lua_pop(state, 1);
            if (!Valid(state, 1)) return 17;
            const int live = g_ctorCalls - g_dtorCalls;
            if (live > peakLive) peakLive = live;
        }
        if (g_dtorCalls <= 32 || peakLive >= 256) return 18;
        Collect(state);
        if (!Valid(state, 1) || g_ctorCalls - g_dtorCalls != 1) return 19;
        // 手动析构重复调用，然后 GC，底层析构必须只有一次。
        lua_pushcfunction(state, isaac::runtime::DestroyFontHandle);
        lua_pushvalue(state, 1);
        if (lua_pcall(state, 1, 0, 0) != LUA_OK) return 20;
        lua_pushcfunction(state, isaac::runtime::DestroyFontHandle);
        lua_pushvalue(state, 1);
        if (lua_pcall(state, 1, 0, 0) != LUA_OK) return 21;
        lua_settop(state, 0);
        Collect(state);
        if (g_ctorCalls != g_dtorCalls || Bytes(state) > baseline + 1024 ||
            allocator.live > actualBaseline + 1024) return 22;
        std::printf("held=%zu reclaimed=%zu actual_reclaimed=%zu baseline=%zu actual_baseline=%zu "
                    "created=%d destroyed=%d auto_gc_peak=%d final=%zu\n", held, reclaimed,
                    actualReclaimed, baseline, actualBaseline, g_ctorCalls, g_dtorCalls,
                    peakLive, Bytes(state));
    } else if (std::strcmp(argv[1], "oom") == 0) {
        int failures = 0;
        for (int failAfter = 0; failAfter < 5; ++failAfter) {
            Collect(state);
            const auto baseline = allocator.live;
            allocator.failAfter = failAfter;
            const int ctors = g_ctorCalls;
            const int status = Make(state);
            allocator.failAfter = -1;
            if (status != LUA_OK) {
                ++failures;
                if (status != LUA_ERRMEM || g_ctorCalls != ctors) return 30;
            } else if (!Valid(state, -1)) return 31;
            lua_settop(state, 0);
            Collect(state);
            if (g_ctorCalls != g_dtorCalls || allocator.live > baseline + 1024) return 32;
            if (Make(state) != LUA_OK || !Valid(state, -1)) return 33;
            lua_settop(state, 0);
            Collect(state);
        }
        if (failures < 2) return 34;
        std::printf("oom_failures=%d created=%d destroyed=%d\n", failures, g_ctorCalls, g_dtorCalls);
    } else return 91;
    lua_close(state);
    if (allocator.live != 0 || g_ctorCalls != g_dtorCalls) return 40;
    return 0;
}
'''


class LuaFontGcStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-font-gc-")
        cls.harness = build_lua_harness(
            source_root=SOURCE, workdir=Path(cls.temporary.name),
            harness_source=HARNESS.replace("int main(int argc, char** argv)",
                                           "int resources_main(int argc, char** argv)") + STORAGE_HARNESS,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def check_scenario(self, scenario):
        result = subprocess.run([str(self.harness), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr +
                         f"\n场景 {scenario} 退出码 {result.returncode}")
        print(result.stdout.strip())

    def test_repeated_fonts_with_live_mod_data_fit_a_bounded_heap(self):
        self.check_scenario("bounded")

    def test_default_allocator_is_not_gc_accounting_but_font_storage_is(self):
        self.check_scenario("accounting")

    def test_gc_reclaims_large_blocks_and_keeps_referenced_fonts_valid(self):
        self.check_scenario("pressure")

    def test_oom_before_construction_does_not_leak_and_state_recovers(self):
        self.check_scenario("oom")


if __name__ == "__main__":
    unittest.main()
