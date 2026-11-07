#pragma once

#include <cstdint>

// `MC_EVALUATE_CACHE`(8) 的派发顺序—— 宿主上可测的那一半。
//
// ## 为什么单独抽出来
//
// 引擎的 `Entity_Player::EvaluateItems @ 0x280804..0x28CE88` 是属性重算的总闸，它对
// `Damage`/`MoveSpeed`/`MaxFireDelay`/`ShotSpeed`/`Luck`/`TearRange` 这几格是**清零 + 重建**：
// `CACHE_DAMAGE`(bit0) 置位就先 `str wzr,[x19,#0x1844]`（Damage = 0）再从道具 `fadd`
// 累加，收尾还有两处回写（见 `runtime_constants.hpp` 的段）。
// 而整个函数体里**没有**这条回调的派发点（对外部函数的调用全是导入桩）⇒ 派发点只有我们这一处。
//
// 结论：**必须先跑原函数、再派发**。若沿用"入口钩 + 先派发再跑原函数"（本批之前的样子），
// 模组在回调里写进 `player.Damage = …` 的值会在**同一次** `EvaluateItems` 调用内被引擎重算覆盖
// ⇒ 「自定义角色的属性调整不生效」。这正是本批要修的第二个原因。
//
// ## 快照为什么要保留
//
// 引擎在这轮重算里会把 `_cacheFlags`（`Entity_Player + 0x1958`）的脏位**清掉** ⇒ 跑到
// `original()` 之后再读掩码就什么也读不到。所以要在**调用前**快照一份，逐位过滤继续用这一份。
//
// ## 为什么写成模板
//
// `hook_manager.cpp` 那个中继在宿主机上编不出来（它拖着 exlaunch/libnx）。把"快照 → 原函数 →
// 逐位派发"这段**顺序与快照语义**抽成模板后，三个动作换成可注入的回调，就能在宿主机上
// 用"假原函数 + 假派发"逐条钉住行为（`runtime/tests/test_lua_batch405_evaluate_cache_timing.py`）：
// 派发确实在 `original` 之后、逐位过滤用的是调用前快照、读不到掩码就不派发。
namespace isaac::runtime {

// 派发给模组的实参必须是 `CacheFlag` 的【值】，不是位序号。
//
// 病根（真机读数钉死的）：中继原来把 `bit`（0、1、2…）直接当 `cacheFlag` 交给模组，而模组拿它跟
// `CacheFlag.CACHE_XXX` 的值比（`CACHE_DAMAGE=1` / `CACHE_FIREDELAY=2` / `CACHE_SHOTSPEED=4` /
// `CACHE_RANGE=8` / `CACHE_SPEED=16` / `CACHE_LUCK=1024`… —— 见 `doc_lua_enum_data.cpp`）。
// ⇒ 只有"值恰好等于某个位序号"的分支才会撞上：
// * Trinity 的 `CACHE_FIREDELAY(2)` 撞到位序号 2（引擎的 `CACHE_SHOTSPEED` 位）⇒ 看着像生效
// （它写的是 `MaxFireDelay`，而那一格在这轮重算里已经算完 ⇒ 侥幸活下来）；
// * `CACHE_SPEED(16)` / `CACHE_LUCK(1024)` 要的位序号根本不在 16 个标志里 ⇒ 永远不触发；
// * `CACHE_DAMAGE(1)` 撞到位序号 1（其实是射速位）⇒ 值写进去了，随后被真正的伤害重算覆盖。
// 真机现象（Isaiah，Trinity 的增量为 damage −0.75 / tears +0.27 / speed +0.1）：
// 射速 3.00 = 2.73+0.27 ✓｜伤害 3.50（应 2.75）✗｜速度 1.00（应 1.10）✗。
// `MC_EVALUATE_CACHE` 的过滤值同样是 `CacheFlag` ⇒ 派发与过滤两处都用它。
//
// 为什么做成具名函数而不是在调用点写 `1u << bit`：① 这一条是"给模组的语义"，值得有名字；
// ② 宿主门禁能直接把它编译起来按 `CacheFlag` 表逐值钉住（见
// `runtime/tests/test_lua_batch405_evaluate_cache_timing.py`）。
[[nodiscard]] constexpr std::int32_t CacheFlagValueForBit(std::int32_t bit) noexcept {
    return static_cast<std::int32_t>(static_cast<std::uint32_t>(1U) << bit);
}

// 返回值 = 原函数是否被跑过（本函数恒跑；留作将来扩展，不参与判据）。
// `readFlags(outMask)`：读 `_cacheFlags`；返回 true 表示掩码有效。
// `original()`：跑引擎的 `EvaluateItems`（会清零 + 重建那六格，并清掉脏位）。
// `dispatch(bit)`：把第 `bit` 位派发给模组（一位一次）。
template <typename ReadFlags, typename Original, typename Dispatch>
void DispatchEvaluateCacheAfterOriginal(const ReadFlags& readFlags, const Original& original,
                                        const Dispatch& dispatch) {
    // ① 调用前快照：引擎的原函数会把脏位清掉，派发必须用这一份。
    std::uint32_t mask = 0;
    const bool readable = readFlags(&mask);
    // ② 先跑原函数：引擎在这一步清零 + 重建那六个战斗属性。
    original();
    // ③ 再按快照逐位派发：模组此刻写进去的属性值不会再被同一次重算覆盖。
    if (!readable) {
        // 掩码读不到 ⇒ 不派发（不编造 CacheFlag：过滤值是模组建索引用的，给错的比给不到更糟）。
        return;
    }
    for (std::int32_t bit = 0; bit < 32; ++bit) {
        if ((mask & (static_cast<std::uint32_t>(1U) << bit)) != 0U) {
            dispatch(bit);
        }
    }
}

}  // namespace isaac::runtime
