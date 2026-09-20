"""批次 102 的六个事件回调：**逐实参**与**过滤器**必须与 PC 一致（宿主机门禁）。

## 这个测试解决什么问题

`MC_PRE_GAME_EXIT` / `MC_USE_ITEM` / `MC_USE_CARD` / `MC_USE_PILL` / `MC_PRE_USE_ITEM` /
`MC_POST_GET_COLLECTIBLE` 这六条以前**一条都没派发**（`tools/callback_surface.json` 里全是
`needs_hook`）。接线之后最容易出的错不是"崩"，而是**默默传错实参**或**该筛的没筛**：

* 实参顺序错了（PC 的 `MC_PRE_USE_ITEM` 是 `(CollectibleType, RNG, EntityPlayer, UseFlags,
  ActiveSlot, CustomVarData)`，少一个 `RNG` 就会让后面**整体左移一位**）⇒ 模组读到的是错的东西、
  还不报错；
* 过滤器没生效 ⇒ EID 的 6 个 `MC_PRE_USE_ITEM` 处理器（分别绑 Smelter / Void / Flip / D4 /
  Genesis / Lemegeton）会在**任何**主动道具使用时全部跑一遍。最坏的一条是
  `EID.OnUseSmelter` —— 它对玩家的饰品动手。

所以这里用真 Lua 状态逐项断言，判据写在 Lua 侧（`error(...)`）：只要有一个实参不符，
回调就报错 ⇒ `TakeCallbackError()` 为真 ⇒ 用例红。

## 断言口径

1. **逐实参**：六条回调各自的实参值（含 `UseFlags` / `ActiveSlot` / `CustomVarData` /
   `shouldSave` / 药丸效果 / 卡 / 抽到的道具），以及 `RNG` 位置必须是 `nil`（那是**登记过的偏离**）；
2. **过滤器**：带过滤器的登记只在过滤值相等时被调用；不带过滤器的登记always 被调用；
   **过滤值对不上时，即使处理器返回 true 也不能拦**；
3. **返回值**：`MC_PRE_USE_ITEM` 任一条返回真值 ⇒ `DispatchPreUseItem` 返回 true；
   一条都没返回 ⇒ false（"没返回就绝不拦"）；
4. **没人登记时**：派发函数不碰 Lua、不报错，返回值是"不拦 / 没有替换值"（= 入口中继会原样转发，
   不影响游戏行为）；
5. **`MC_POST_GET_COLLECTIBLE`**：实参是 `(SelectedCollectible, ItemPoolType, Decrease, Seed)`
   —— 第一个实参是**刚选出来的道具**（这是它与 `MC_PRE_GET_COLLECTIBLE` 的唯一区别）；返回值
   能替换它；返回 `nil` 则不替换。
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import build_lua_harness
except ImportError:
    from test_support import build_lua_harness


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

#: 合成实体句柄：宿主上没有真引擎，而 `PushEntityCallbackArgument` 会**真的去读**那个地址
#: （可读性检查在宿主分支直接放行 ⇒ 传一个野指针就是段错；本批第一版传 `0x1234` 正是这么崩的，
#: 四个含"玩家实参"的场景全部 SIGSEGV）。所以给它一块**真内存**：vptr 读出来是 0
#: ⇒ `ClassifyCallbackEntity` 判 None ⇒ 通用 `Entity` 视图（非 nil，正是这里要断言的）。
#: 真机上这个实参必须能回答 `player:HasCollectible()`，那由 `test_lua_entity_player.py` 那一族管。

#: 过滤值（用两个互不相干的数字，不依赖任何具体枚举值 —— 这条门禁验的是机制不是表）。
FILTER_HIT = 100
FILTER_MISS = 200

HARNESS = r'''
#include "lua_runtime.hpp"
#include "interfaces/lua/isaac_api.hpp"

#include <cstdint>
#include <cstring>

namespace {

//: 合成的"玩家实体"内存（见文件头 `PLAYER_HANDLE` 的说明）。
alignas(16) unsigned char g_FakePlayer[1024] = {};

//: 合成实体句柄。
std::uintptr_t Player() { return reinterpret_cast<std::uintptr_t>(g_FakePlayer); }

//: 第二块合成实体内存：`MC_PRE_PICKUP_COLLISION` 的第二个实参（碰掉落物的那个实体）。
alignas(16) unsigned char g_FakeCollider[1024] = {};

std::uintptr_t Collider() { return reinterpret_cast<std::uintptr_t>(g_FakeCollider); }

//: 读一个由 Lua 侧维护的计数（`_probe.<名字>`）。返回 false = 那个计数根本没被 Lua 写过。
//:
//: ⚠️ 必须用**表 + 字段**那条通道，不能用 `ReadLuaGlobalNumber("_probe.x")`：后者是
//: `lua_getglobal`，而点号路径**不是**全局名（本批第一版就是这么写的，读出来恒"没有"）。
//: 这正是 `lua_runtime.hpp` 里 `ReadLuaTableNumber` 那段注释记的 2026-09-12 教训。
bool Counter(const char* name, double* value) {
    return LuaRuntime::ReadLuaTableNumber("_probe", name, value) == 0;
}

//: 读一个布尔标记（例如"最近一次退出事件的 shouldSave"）。
bool Flag(const char* name, bool* value) {
    return LuaRuntime::ReadLuaTableBoolean("_probe", name, value);
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    const char* script = nullptr;
    if (std::strcmp(scenario, "use_item_args") == 0) {
        script =
            "local mod = RegisterMod('Probe', 1) "
            "_probe = { use_item = 0, pre_use_item = 0 } "
            "local function check(self, item, rng, player, useFlags, slot, customVar) "
            "  if self ~= mod then error('mod object') end "
            "  if item ~= 33 then error('item') end "
            "  if rng ~= nil then error('rng must be nil (registered deviation)') end "
            "  if player == nil then error('player') end "
            "  if useFlags ~= 4 then error('useFlags') end "
            "  if slot ~= 2 then error('activeSlot') end "
            "  if customVar ~= 77 then error('customVarData') end "
            "end "
            "mod:AddCallback(ModCallbacks.MC_USE_ITEM, function(...) "
            "  check(...) _probe.use_item = _probe.use_item + 1 end) "
            "mod:AddCallback(ModCallbacks.MC_PRE_USE_ITEM, function(...) "
            "  check(...) _probe.pre_use_item = _probe.pre_use_item + 1 end)";
    } else if (std::strcmp(scenario, "card") == 0) {
        script =
            "local mod = RegisterMod('Probe', 1) "
            "_probe = { card = 0 } "
            "mod:AddCallback(ModCallbacks.MC_USE_CARD, function(self, card, player, useFlags) "
            "  if self ~= mod then error('mod object') end "
            "  if card ~= 42 then error('card') end "
            "  if player == nil then error('player') end "
            "  if useFlags ~= 8 then error('useFlags') end "
            "  _probe.card = _probe.card + 1 end)";
    } else if (std::strcmp(scenario, "pill") == 0) {
        script =
            "local mod = RegisterMod('Probe', 1) "
            "_probe = { pill = 0 } "
            "mod:AddCallback(ModCallbacks.MC_USE_PILL, function(self, effect, player, useFlags) "
            "  if self ~= mod then error('mod object') end "
            "  if effect ~= 11 then error('pillEffect') end "
            "  if player == nil then error('player') end "
            "  if useFlags ~= 16 then error('useFlags') end "
            "  _probe.pill = _probe.pill + 1 end)";
    } else if (std::strcmp(scenario, "exit") == 0) {
        script =
            "local mod = RegisterMod('Probe', 1) "
            "_probe = { exit = 0, lastSave = true } "
            "mod:AddCallback(ModCallbacks.MC_PRE_GAME_EXIT, function(self, shouldSave) "
            "  if self ~= mod then error('mod object') end "
            "  if type(shouldSave) ~= 'boolean' then error('shouldSave must be boolean') end "
            "  _probe.exit = _probe.exit + 1 "
            "  _probe.lastSave = shouldSave end)";
    } else if (std::strcmp(scenario, "filter") == 0) {
        script =
            "local mod = RegisterMod('Probe', 1) "
            "_probe = { hit = 0, miss = 0, plain = 0 } "
            "mod:AddCallback(ModCallbacks.MC_PRE_USE_ITEM, function() "
            "  _probe.hit = _probe.hit + 1 end, 100) "
            "mod:AddCallback(ModCallbacks.MC_PRE_USE_ITEM, function() "
            "  _probe.miss = _probe.miss + 1 end, 200) "
            "mod:AddCallback(ModCallbacks.MC_PRE_USE_ITEM, function() "
            "  _probe.plain = _probe.plain + 1 end)";
    } else if (std::strcmp(scenario, "filter_blocks") == 0) {
        // 带过滤器的处理器**返回真值**：过滤值对上才拦、对不上绝不许拦。
        script =
            "local mod = RegisterMod('Probe', 1) "
            "mod:AddCallback(ModCallbacks.MC_PRE_USE_ITEM, function() return true end, 100)";
    } else if (std::strcmp(scenario, "block") == 0) {
        script =
            "local mod = RegisterMod('Probe', 1) "
            "mod:AddCallback(ModCallbacks.MC_PRE_USE_ITEM, function() return false end) "
            "mod:AddCallback(ModCallbacks.MC_PRE_USE_ITEM, function() return true end)";
    } else if (std::strcmp(scenario, "no_block") == 0) {
        script =
            "local mod = RegisterMod('Probe', 1) "
            "mod:AddCallback(ModCallbacks.MC_PRE_USE_ITEM, function() end) "
            "mod:AddCallback(ModCallbacks.MC_PRE_USE_ITEM, function() return nil end)";
    } else if (std::strcmp(scenario, "post_get") == 0) {
        script =
            "local mod = RegisterMod('Probe', 1) "
            "_probe = { post = 0 } "
            "mod:AddCallback(ModCallbacks.MC_POST_GET_COLLECTIBLE, "
            "function(self, selected, pool, decrease, seed) "
            "  if self ~= mod then error('mod object') end "
            "  if selected ~= 733 then error('selectedCollectible') end "
            "  if pool ~= 1 then error('itemPoolType') end "
            "  if decrease ~= true then error('decrease must be boolean true') end "
            "  if seed ~= 2 then error('seed') end "
            "  _probe.post = _probe.post + 1 end)";
    } else if (std::strcmp(scenario, "post_get_override") == 0) {
        script =
            "local mod = RegisterMod('Probe', 1) "
            "mod:AddCallback(ModCallbacks.MC_POST_GET_COLLECTIBLE, function() return 1234 end)";
    } else if (std::strcmp(scenario, "post_get_nil") == 0) {
        script =
            "local mod = RegisterMod('Probe', 1) "
            "mod:AddCallback(ModCallbacks.MC_POST_GET_COLLECTIBLE, function() return nil end)";
    } else if (std::strcmp(scenario, "pickup_collision") == 0) {
        script =
            "local mod = RegisterMod('Probe', 1) "
            "_probe = { collision = 0 } "
            "mod:AddCallback(ModCallbacks.MC_PRE_PICKUP_COLLISION, "
            "function(self, pickup, collider, low) "
            "  if self ~= mod then error('mod object') end "
            "  if pickup == nil then error('pickup') end "
            "  if collider == nil then error('collider') end "
            "  if low ~= true then error('low must be boolean true') end "
            "  _probe.collision = _probe.collision + 1 end)";
    } else if (std::strcmp(scenario, "pickup_collision_filter") == 0) {
        // 过滤值是**掉落物的变体**（PC 的可选实参类型是 `PickupVariant`）。
        script =
            "local mod = RegisterMod('Probe', 1) "
            "_probe = { hit = 0, miss = 0, plain = 0 } "
            "mod:AddCallback(ModCallbacks.MC_PRE_PICKUP_COLLISION, function() "
            "  _probe.hit = _probe.hit + 1 end, 100) "
            "mod:AddCallback(ModCallbacks.MC_PRE_PICKUP_COLLISION, function() "
            "  _probe.miss = _probe.miss + 1 end, 200) "
            "mod:AddCallback(ModCallbacks.MC_PRE_PICKUP_COLLISION, function() "
            "  _probe.plain = _probe.plain + 1 end)";
    } else if (std::strcmp(scenario, "pickup_collision_false_blocks") == 0) {
        // ★ 三态里最容易写错的一条：PC 文档说返回 `false` 是"算碰撞但**不执行**内部代码"
        // ⇒ 它也算"非 nil"，原函数同样不许跑。
        script =
            "local mod = RegisterMod('Probe', 1) "
            "mod:AddCallback(ModCallbacks.MC_PRE_PICKUP_COLLISION, function() return false end)";
    } else if (std::strcmp(scenario, "pickup_collision_nil_continues") == 0) {
        script =
            "local mod = RegisterMod('Probe', 1) "
            "mod:AddCallback(ModCallbacks.MC_PRE_PICKUP_COLLISION, function() return nil end)";
    } else if (std::strcmp(scenario, "priority_order") == 0) {
        // 批次 105：**端到端**验两件事 ——
        //   ① `CallbackPriority` 这个全局真的存在（此前它根本不在枚举表里，
        //      而 GoodTrip 的 main.lua:84 起有 7 处无保护地引用它 ⇒ 整块脚本中止）；
        //   ② 优先级真的影响派发顺序（数值越小越早；同优先级保持登记顺序）。
        // 判据全写在 Lua 侧：值不对就 `error`，顺序不对就由 C++ 侧读 `_probe` 的序号判。
        script =
            "local mod = RegisterMod('Probe', 1) "
            "_probe = { late = 0, early = 0, default = 0, seq = 0 } "
            "if CallbackPriority.EARLY ~= -100 or CallbackPriority.DEFAULT ~= 0 "
            "  or CallbackPriority.LATE ~= 100 or CallbackPriority.IMPORTANT ~= -200 then "
            "  error('CallbackPriority values') end "
            "local function marker(name) return function() "
            "  _probe.seq = _probe.seq + 1 _probe[name] = _probe.seq end end "
            "mod:AddPriorityCallback(ModCallbacks.MC_POST_UPDATE, CallbackPriority.LATE, "
            "  marker('late')) "
            "mod:AddPriorityCallback(ModCallbacks.MC_POST_UPDATE, CallbackPriority.EARLY, "
            "  marker('early')) "
            "mod:AddCallback(ModCallbacks.MC_POST_UPDATE, marker('default'))";
    } else if (std::strcmp(scenario, "room_spawn") == 0) {
        script =
            "local mod = RegisterMod('Probe', 1) "
            "_probe = { spawn = 0 } "
            "mod:AddCallback(ModCallbacks.MC_PRE_ROOM_ENTITY_SPAWN, "
            "function(self, entityType, variant, subType, gridIndex, seed) "
            "  if self ~= mod then error('mod object') end "
            "  if entityType ~= 5 then error('entityType') end "
            "  if variant ~= 100 then error('variant') end "
            "  if subType ~= 7 then error('subType') end "
            "  if gridIndex ~= 42 then error('gridIndex') end "
            "  if seed ~= 12345 then error('seed') end "
            "  _probe.spawn = _probe.spawn + 1 end)";
    } else if (std::strcmp(scenario, "none") == 0) {
        // 被测的六条**一条登记都没有**：派发函数必须安安静静地返回"不拦 / 没有替换值"。
        //
        // 但仍要登记**别的**一条：`InitializeFromBuffer` 在登记表为空时返回
        // `MissingPostUpdateCallback`（`lua_runtime.cpp` 里那条判据是 `g_CallbackRegistry.Count() == 0`，
        // 名字是历史遗留、条件其实是"至少有一条登记"）。用 `MC_POST_UPDATE` 是因为它与本场景要
        // 验的六条都不相干 —— 被测条件（那六条零登记）依然成立。
        script = "local mod = RegisterMod('Probe', 1) _probe = { any = 0 } "
                 "mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function() end)";
    } else {
        return 91;
    }
    if (LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@event.lua") !=
        LuaRuntime::LuaInitResult::Success) {
        return 1;
    }

    if (std::strcmp(scenario, "use_item_args") == 0) {
        const bool blocked = LuaRuntime::DispatchPreUseItem(Player(), 33, 4, 2, 77);
        LuaRuntime::DispatchUseItem(Player(), 33, 4, 2, 77);
        if (blocked) return 2;                     // 没人返回真值 ⇒ 不许拦
        double pre = 0, use = 0;
        if (!Counter("pre_use_item", &pre) || pre != 1) return 3;
        if (!Counter("use_item", &use) || use != 1) return 4;
        return LuaRuntime::TakeCallbackError() ? 5 : 0;
    }
    if (std::strcmp(scenario, "card") == 0) {
        LuaRuntime::DispatchUseCard(Player(), 42, 8);
        double count = 0;
        if (!Counter("card", &count) || count != 1) return 2;
        return LuaRuntime::TakeCallbackError() ? 3 : 0;
    }
    if (std::strcmp(scenario, "pill") == 0) {
        LuaRuntime::DispatchUsePill(Player(), 11, 16);
        double count = 0;
        if (!Counter("pill", &count) || count != 1) return 2;
        return LuaRuntime::TakeCallbackError() ? 3 : 0;
    }
    if (std::strcmp(scenario, "exit") == 0) {
        LuaRuntime::DispatchPreGameExit(true);
        LuaRuntime::DispatchPreGameExit(false);
        double count = 0;
        bool last = true;
        if (!Counter("exit", &count) || count != 2) return 2;
        // 第二次派发传的是 false（"这一局不会产生可续存档"），处理器必须读到 false。
        if (!Flag("lastSave", &last) || last) return 3;
        return LuaRuntime::TakeCallbackError() ? 4 : 0;
    }
    if (std::strcmp(scenario, "filter") == 0) {
        // 过滤值 = 100 ⇒ 命中那条 + 无过滤器那条被调用；过滤值 200 的那条不调用。
        // 返回值这里用不上（本场景的两个处理器都不返回），显式丢弃以过 `-Werror=unused-result`。
        static_cast<void>(LuaRuntime::DispatchPreUseItem(Player(), 100, 0, 0, 0));
        double hit = 0, miss = 0, plain = 0;
        if (!Counter("hit", &hit) || hit != 1) return 2;
        if (!Counter("miss", &miss) || miss != 0) return 3;
        if (!Counter("plain", &plain) || plain != 1) return 4;
        // 过滤值 = 200 ⇒ 换成另一条命中。
        static_cast<void>(LuaRuntime::DispatchPreUseItem(Player(), 200, 0, 0, 0));
        if (!Counter("hit", &hit) || hit != 1) return 5;
        if (!Counter("miss", &miss) || miss != 1) return 6;
        if (!Counter("plain", &plain) || plain != 2) return 7;
        return LuaRuntime::TakeCallbackError() ? 8 : 0;
    }
    if (std::strcmp(scenario, "filter_blocks") == 0) {
        if (!LuaRuntime::DispatchPreUseItem(Player(), 100, 0, 0, 0)) return 2;  // 命中 ⇒ 拦
        if (LuaRuntime::DispatchPreUseItem(Player(), 200, 0, 0, 0)) return 3;   // 不命中 ⇒ 绝不拦
        return LuaRuntime::TakeCallbackError() ? 4 : 0;
    }
    if (std::strcmp(scenario, "block") == 0) {
        if (!LuaRuntime::DispatchPreUseItem(Player(), 33, 0, 0, 0)) return 2;
        return LuaRuntime::TakeCallbackError() ? 3 : 0;
    }
    if (std::strcmp(scenario, "no_block") == 0) {
        if (LuaRuntime::DispatchPreUseItem(Player(), 33, 0, 0, 0)) return 2;
        return LuaRuntime::TakeCallbackError() ? 3 : 0;
    }
    if (std::strcmp(scenario, "post_get") == 0) {
        const std::uint64_t result =
            LuaRuntime::DispatchPostGetCollectible(nullptr, 1, 2, 1, 733);
        double count = 0;
        if (!Counter("post", &count) || count != 1) return 2;
        if (result != 0) return 3;  // 处理器没返回替换值 ⇒ 没有替换
        return LuaRuntime::TakeCallbackError() ? 4 : 0;
    }
    if (std::strcmp(scenario, "post_get_override") == 0) {
        const std::uint64_t result =
            LuaRuntime::DispatchPostGetCollectible(nullptr, 1, 2, 1, 733);
        if (result != 0x1000004D2ULL) return 2;  // (1 << 32) | 1234
        return LuaRuntime::TakeCallbackError() ? 3 : 0;
    }
    if (std::strcmp(scenario, "post_get_nil") == 0) {
        const std::uint64_t result =
            LuaRuntime::DispatchPostGetCollectible(nullptr, 1, 2, 1, 733);
        if (result != 0) return 2;
        return LuaRuntime::TakeCallbackError() ? 3 : 0;
    }
    if (std::strcmp(scenario, "pickup_collision") == 0) {
        if (LuaRuntime::DispatchPrePickupCollision(Player(), Collider(), true, 100)) return 2;
        double count = 0;
        if (!Counter("collision", &count) || count != 1) return 3;
        return LuaRuntime::TakeCallbackError() ? 4 : 0;
    }
    if (std::strcmp(scenario, "pickup_collision_filter") == 0) {
        static_cast<void>(LuaRuntime::DispatchPrePickupCollision(Player(), Collider(), true, 100));
        double hit = 0, miss = 0, plain = 0;
        if (!Counter("hit", &hit) || hit != 1) return 2;
        if (!Counter("miss", &miss) || miss != 0) return 3;
        if (!Counter("plain", &plain) || plain != 1) return 4;
        static_cast<void>(LuaRuntime::DispatchPrePickupCollision(Player(), Collider(), true, 200));
        if (!Counter("hit", &hit) || hit != 1) return 5;
        if (!Counter("miss", &miss) || miss != 1) return 6;
        if (!Counter("plain", &plain) || plain != 2) return 7;
        return LuaRuntime::TakeCallbackError() ? 8 : 0;
    }
    if (std::strcmp(scenario, "pickup_collision_false_blocks") == 0) {
        // 返回 false ⇒ **非 nil** ⇒ 不跑原函数（PC 三态的第二态）。
        if (!LuaRuntime::DispatchPrePickupCollision(Player(), Collider(), false, 100)) return 2;
        return LuaRuntime::TakeCallbackError() ? 3 : 0;
    }
    if (std::strcmp(scenario, "pickup_collision_nil_continues") == 0) {
        // 返回 nil ⇒ 照常执行内部代码（原函数照跑）。
        if (LuaRuntime::DispatchPrePickupCollision(Player(), Collider(), false, 100)) return 2;
        return LuaRuntime::TakeCallbackError() ? 3 : 0;
    }
    if (std::strcmp(scenario, "priority_order") == 0) {
        LuaRuntime::DispatchPostUpdate();
        double early = 0, normal = 0, late = 0, seq = 0;
        if (!Counter("early", &early) || early != 1) return 2;      // EARLY(-100) 最先
        if (!Counter("default", &normal) || normal != 2) return 3;  // DEFAULT(0) 第二
        if (!Counter("late", &late) || late != 3) return 4;         // LATE(100) 最后
        if (!Counter("seq", &seq) || seq != 3) return 5;
        return LuaRuntime::TakeCallbackError() ? 6 : 0;
    }
    if (std::strcmp(scenario, "room_spawn") == 0) {
        LuaRuntime::DispatchPreRoomEntitySpawn(5, 100, 7, 42, 12345);
        double count = 0;
        if (!Counter("spawn", &count) || count != 1) return 2;
        if (LuaRuntime::TakeCallbackError()) return 3;
        // --- 顺带把 `ReadRoomConfigEntryFields` 的**字段宽度**钉住 ---------------------
        // 这是全批最值得钉的一点：PC 文档说 `RoomConfig::Entry` 是三个 `int`，而这个构建里
        // `Variant`/`SubType` 是 **i16**（证据见 runtime_constants.hpp）。若按 i32 读，
        // `Variant` 会把 `SubType` 拼进高 16 位 ⇒ 这里刻意让 subType 非零，就是为了让那种错**红**。
        unsigned char entry[16] = {0};
        const std::int32_t type = 5;
        const std::uint16_t variant = 100;
        const std::uint16_t subType = 7;
        std::memcpy(entry + 0x00, &type, sizeof(type));
        std::memcpy(entry + 0x04, &variant, sizeof(variant));
        std::memcpy(entry + 0x06, &subType, sizeof(subType));
        std::int32_t readType = -1, readVariant = -1, readSubType = -1;
        if (!isaac::runtime::ReadRoomConfigEntryFields(
                reinterpret_cast<std::uintptr_t>(entry), &readType, &readVariant, &readSubType)) {
            return 4;
        }
        if (readType != 5) return 5;
        if (readVariant != 100) return 6;      // 按 i32 读会得到 100 | (7 << 16)
        if (readSubType != 7) return 7;
        // 空指针/零地址必须**响亮失败**，不许返回编造的 0。
        if (isaac::runtime::ReadRoomConfigEntryFields(0, &readType, &readVariant, &readSubType)) {
            return 8;
        }
        return 0;
    }
    // "none"：一条登记都没有时，四个入口都必须报告"不拦 / 不替换"，且不得产生回调错误。
    if (LuaRuntime::DispatchPreUseItem(Player(), 33, 0, 0, 0)) return 2;
    LuaRuntime::DispatchUseItem(Player(), 33, 0, 0, 0);
    LuaRuntime::DispatchUseCard(Player(), 42, 0);
    LuaRuntime::DispatchUsePill(Player(), 11, 0);
    LuaRuntime::DispatchPreGameExit(true);
    if (LuaRuntime::DispatchPrePickupCollision(Player(), Collider(), true, 100)) return 5;
    LuaRuntime::DispatchPreRoomEntitySpawn(5, 100, 7, 42, 12345);
    if (LuaRuntime::DispatchPostGetCollectible(nullptr, 1, 2, 1, 733) != 0) return 3;
    return LuaRuntime::TakeCallbackError() ? 4 : 0;
}
'''

SCENARIOS = (
    "use_item_args",
    "card",
    "pill",
    "exit",
    "filter",
    "filter_blocks",
    "block",
    "no_block",
    "post_get",
    "post_get_override",
    "post_get_nil",
    "pickup_collision",
    "pickup_collision_filter",
    "pickup_collision_false_blocks",
    "pickup_collision_nil_continues",
    "room_spawn",
    "priority_order",
    "none",
)


class LuaEventCallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-event-callbacks-")
        cls.harness = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name),
            harness_source=HARNESS,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_harness(self, scenario):
        result = subprocess.run([str(self.harness), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0,
                         f"场景 {scenario} 失败（退出码 {result.returncode}）："
                         f"{result.stdout}{result.stderr}")

    def test_all_scenarios(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                self.run_harness(scenario)

    def test_dispatch_declarations_exist(self):
        """源码层面钉住六个入口 —— 接口名字改了而门禁没跟上会让上面的场景全部编译失败，
        但那条报错只会说"某个符号不存在"，不如直接说清"这六条派发入口是哪六条"。"""
        header = (SOURCE / "lua_runtime.hpp").read_text(encoding="utf-8")
        for declaration in ("void DispatchPreGameExit(bool shouldSave);",
                            "bool DispatchPreUseItem(",
                            "void DispatchUseItem(",
                            "void DispatchUseCard(",
                            "void DispatchUsePill(",
                            "std::uint64_t DispatchPostGetCollectible(",
                            "bool DispatchPrePickupCollision(",
                            "void DispatchPreRoomEntitySpawn("):
            with self.subTest(declaration=declaration):
                self.assertIn(declaration, header)


if __name__ == "__main__":
    unittest.main()
