"""Custom ItemPool ids use XML records and the native pool picker, not a fake item."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from .test_support import build_lua_harness


SOURCE = Path(__file__).resolve().parents[1] / "source"
CUSTOM_ITEM_POOL_HEADER = SOURCE / "program" / "custom_item_pool.hpp"


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "program/custom_item_pool.hpp"
#include "program/custom_item_pool_native.hpp"
#include "program/xml_data_store.hpp"
#include "relay/internal_hook.hpp"
#include "runtime_constants.hpp"

#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>

namespace custom = isaac::runtime::custom_item_pool;
namespace custom_native = isaac::runtime::custom_item_pool_native;
namespace xml = isaac::runtime::xml_data;

static unsigned char g_item_pool[0x940]{};
static unsigned g_native_get_calls = 0;
static const float g_expected_weights[] = {2.0F, 2.0F, 1.5F, 1.0F};

GameItemPoolObservation ReadCurrentGameItemPool(uintptr_t, void** out) {
    *out = g_item_pool;
    return GameItemPoolObservation::Success;
}

static std::uint32_t NativeGetCollectible(void* item_pool,
                                          std::uint32_t pool_type,
                                          std::uint32_t seed,
                                          std::uint32_t no_decrease,
                                          std::uint32_t default_item) {
    ++g_native_get_calls;
    assert(item_pool == g_item_pool);
    assert(pool_type == 31);
    assert(default_item == 0);
    assert(g_native_get_calls <= 4);

    isaac::runtime::relay::InternalHookContext context{};
    context.x[22] = reinterpret_cast<std::uintptr_t>(item_pool);
    context.x[23] = pool_type;
    assert(custom_native::ApplyPoolSubstitutionForHook(
        context, custom_native::PoolAccessSite::Initial));
    auto* entry = reinterpret_cast<custom::NativePoolEntry*>(context.x[23]);
    assert(entry != nullptr);
    assert(entry->pool.begin != nullptr && entry->pool.end == entry->pool.begin + 3);
    assert(entry->pool.begin[0].itemId == 316);
    assert(entry->pool.begin[1].itemId == 806);
    assert(entry->pool.begin[2].itemId == 900);
    assert(std::fabs(entry->pool.totalWeight - 3.5F) < 0.0001F);

    custom::NativePoolItem* selected = &entry->pool.begin[1];
    assert(std::fabs(selected->initialWeight - 2.0F) < 0.0001F);
    assert(std::fabs(selected->weight - g_expected_weights[g_native_get_calls - 1]) <
           0.0001F);
    if (seed == 100) {
        assert(no_decrease == 1);
    } else if (seed == 101) {
        assert(no_decrease == 0);
        selected->weight -= selected->decreaseBy;
    } else if (seed == 102) {
        assert(no_decrease == 0);
        selected->weight -= selected->decreaseBy;
    } else if (seed == 900) {
        context.x[23] = 0;
        assert(custom_native::ApplyPoolSubstitutionForHook(
            context, custom_native::PoolAccessSite::Initial));
        assert(context.x[23] == reinterpret_cast<std::uintptr_t>(item_pool));
        return 25;
    } else {
        assert(false);
    }
    return 806;
}

static std::int32_t ResolveName(void*, const char* name, std::size_t length) {
    if (length == std::strlen("Author Item") &&
        std::memcmp(name, "Author Item", length) == 0) {
        return 806;
    }
    if (length == std::strlen("Missing Item") &&
        std::memcmp(name, "Missing Item", length) == 0) {
        return -1;
    }
    return -1;
}

static bool InspectId(void*, std::int32_t id, bool* is_special) {
    if (id != 316 && id != 806 && id != 900) {
        return false;
    }
    *is_special = (id == 900);
    return true;
}

int main() {
    const char pools[] =
        "<ItemPools><Pool Name='shionBeggar'>"
        "<Item Id='316' Weight='1' DecreaseBy='1' RemoveOn='0.1'/>"
        "<Item Name='Author Item' Weight='2' DecreaseBy='0.5' RemoveOn='0.1'/>"
        "<Item Id='900' Weight='0.5' DecreaseBy='0.5' RemoveOn='0.05'/>"
        "<Item Name='Missing Item' Weight='9'/>"
        "</Pool></ItemPools>";
    assert(xml::IngestXmlDataFile(xml::XmlDataFileKind::ItemPools, "Mod", true, pools,
                                  std::strlen(pools), {}));
    const auto* record = xml::FindEntryById(xml::XmlNodeType::ItemPool, 31);
    assert(record != nullptr && record->id == 31);

    custom::Bindings bindings{};
    bindings.resolveName = &ResolveName;
    bindings.inspectId = &InspectId;
    custom::SetHostBindingsForTests(bindings);
    custom_native::SetHostReadyForTests(true);

    const auto image_size = static_cast<std::size_t>(kRandomU32Offset + 8);
    std::vector<unsigned char> image(image_size);
    std::memcpy(image.data() + kRandomU32Offset, &kRandomU32EntryWord, 4);
    LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(image.data()));
    LuaRuntime::SetItemPoolGetCollectibleBinding(
        reinterpret_cast<std::uintptr_t>(&NativeGetCollectible));

    const char* script = R"lua(
        local pool = Game():GetItemPool()
        local pre_count, post_count = 0, 0
        local mod = RegisterMod("CustomPool", 1)
        mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE,
            function(_, pool_type, decrease, seed)
                assert(pool_type == 31)
                pre_count = pre_count + 1
                if seed == 777 then return 733 end
            end)
        mod:AddCallback(ModCallbacks.MC_POST_GET_COLLECTIBLE,
            function(_, selected, pool_type, decrease, seed)
                assert(selected == 806 and pool_type == 31)
                post_count = post_count + 1
            end)
        assert(pool:GetCollectible(31, false, 100) == 806)
        assert(pool:GetCollectible(31, true, 101) == 806)
        assert(pool:GetCollectible(31, true, 102) == 806)
        assert(pool:GetCollectible(31, false, 900) == 25)
        assert(pre_count == 0 and post_count == 0)
        local ok, error = pcall(function() pool:GetCollectible(33, false, 103) end)
        assert(not ok and string.find(tostring(error), "not registered"))
        mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function() end)
    )lua";
    const auto result =
        LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@custom-pool.lua");
    char error[1024]{};
    (void)LuaRuntime::CopyLastLuaErrorText(error, sizeof(error));
    auto* retained = custom::AcquireNativePool(g_item_pool, 31, bindings);
    assert(retained != nullptr);
    custom::NativePoolEntry other{};
    {
        custom_native::ScopedPoolContext outer(g_item_pool, 31, retained);
        custom_native::ScopedPoolContext inner(g_item_pool, 29, &other);
        isaac::runtime::relay::InternalHookContext context{};
        context.x[22] = reinterpret_cast<std::uintptr_t>(g_item_pool);
        context.x[23] = 29;
        assert(custom_native::ApplyPoolSubstitutionForHook(
            context, custom_native::PoolAccessSite::Initial));
        assert(context.x[23] == reinterpret_cast<std::uintptr_t>(&other));
    }
    {
        isaac::runtime::relay::InternalHookContext context{};
        context.x[22] = reinterpret_cast<std::uintptr_t>(g_item_pool);
        context.x[23] = 29;
        assert(custom_native::ApplyPoolSubstitutionForHook(
            context, custom_native::PoolAccessSite::Initial));
        assert(context.x[23] ==
               reinterpret_cast<std::uintptr_t>(g_item_pool) + 29 * 0x48);
        {
            custom_native::ScopedPoolContext custom(g_item_pool, 31, retained);
            context.x[23] = 31;
            assert(custom_native::ApplyPoolSubstitutionForHook(
                context, custom_native::PoolAccessSite::Initial));
            assert(context.x[23] == reinterpret_cast<std::uintptr_t>(retained));
        }
    }
    std::printf("status=%u native=%u error=%s\n", unsigned(result),
                g_native_get_calls, error);
    return result == LuaRuntime::LuaInitResult::Success &&
                   g_native_get_calls == 4
               ? 0
               : 1;
}
'''


class LuaCustomItemPoolTests(unittest.TestCase):
    def test_custom_pool_ids_use_xml_weights_and_native_picker(self):
        self.assertTrue(CUSTOM_ITEM_POOL_HEADER.is_file(),
                        f"missing implementation: {CUSTOM_ITEM_POOL_HEADER}")
        with tempfile.TemporaryDirectory(prefix="isaac-custom-itempool-") as temporary:
            binary = build_lua_harness(
                source_root=SOURCE,
                workdir=Path(temporary),
                harness_source=HARNESS,
            )
            result = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
