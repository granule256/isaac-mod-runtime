#pragma once

#include "domain/callback/callback_descriptor.hpp"
#include "domain/runtime/status.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace isaac::runtime {

// Registered callbacks per Mod. The legacy Runtime kept one global slot per
// callback id, which made multi-Mod registration impossible; this registry is
// fixed-capacity and ordered so dispatch order is deterministic.
class CallbackRegistry {
public:
    // 2026-09-12：64 → 256。PC 允许同一 Mod 对同一 id 登记多个回调**并存**，而 EID 一家就要
    // 几十条（5 个 `MC_POST_NEW_ROOM`、10 个 `MC_PRE_USE_ITEM`、各 feature 各自的登记）。
    // 每条描述符只有几十字节，256 条的代价可以忽略。
    static constexpr std::size_t kCapacity = 256;

    //: 没有显式指定优先级时的取值。PC 的 `CallbackPriority.DEFAULT == 0`；
    //: 另两个常用值是 `EARLY == -100`、`LATE == 100`（**数值越小越早执行**）。
    static constexpr std::int32_t kDefaultCallbackPriority = 0;

    //: "这条登记没有过滤器"的哨兵值（PC 的 `AddCallback` 只传两个实参时）。
    //: 用 `int64` 的最小值而不是 0：PC 的过滤器是任意整数，`0` 是**有意义**的取值
    //: （`Card.CARD_FOOL`、`PillEffect` 里都有 0），拿 0 当"没有过滤器"会把它们吃掉。
    static constexpr std::int64_t kNoCallbackFilter = std::numeric_limits<std::int64_t>::min();

    // `filter` 是 PC `Mod:AddCallback(id, fn, entityId)` 的第三个实参（官方文档里叫 entityId，
    // 类型随回调而异：`CollectibleType` / `Card` / `PillEffect` / `PickupVariant`…）：
    // 带过滤器的登记**只在"过滤值相等"时被派发**。
    //
    // ★ 为什么不把过滤器放进 `CallbackDescriptor`：那会改"20 字节/项"的布局，而
    // `tools/read_device_state_via_gdb.py` 与离线重放都按这个尺寸解码登记表（逐字段解到
    // `+16 modReference`）。与 `AddPriorityCallback` 的优先级排序同一个理由 —— 加**平行的**
    // 一张表，描述符本身一个字节都不动。
    // `priority` 是 PC `Mod:AddPriorityCallback(id, priority, fn[, entityId])` 的第二个实参
    // （`CallbackPriority` 里的值，**数值越小越早执行**）。带优先级的登记会**先于**默认优先级的
    // 登记被派发；**同优先级之间保持登记顺序**（稳定排序）。
    [[nodiscard]] Status Register(const CallbackDescriptor& descriptor,
                                  std::int64_t filter = kNoCallbackFilter,
                                  std::int32_t priority = kDefaultCallbackPriority) noexcept;

    //: 第 `index` 条登记（**全表下标**，与 `AtIndex` 同一个坐标系）的过滤器。
    //: 越界返回 `kNoCallbackFilter`。
    [[nodiscard]] std::int64_t FilterAt(std::size_t index) const noexcept;
    //: 第 `index` 条登记（**全表下标**）的优先级。越界返回 `kDefaultCallbackPriority`。
    [[nodiscard]] std::int32_t PriorityAt(std::size_t index) const noexcept;

    [[nodiscard]] const CallbackDescriptor* Find(CallbackId id, ModHandle owner) const noexcept;

    // Removes one (id, owner) registration. When `removed` is provided the
    // caller receives the entry so it can release its Lua references.
    //
    // ⚠️ 它摘的是**第一条**匹配 `(id, owner)` 的登记。同一 Mod 对同一 id 登记多个回调是常态
    // （EID 一家就登记 5 个 `MC_POST_NEW_ROOM`）⇒ 要摘"指定的那一条"必须用下面的
    // `RemoveAtIndex()`，否则会摘错人（`Mod:RemoveCallback` 就是那种调用方）。
    std::uint32_t Remove(CallbackId id, ModHandle owner,
                         CallbackDescriptor* removed = nullptr) noexcept;

    // Removes the entry at `index`（后面的一条条前移，保持登记顺序）。
    //
    // 为什么需要它：`Remove(id, owner)` 只能按"第一个匹配"摘，而 PC 的
    // `Mod:RemoveCallback(id, function)` 是按**函数身份**摘某一条 —— 同 id 上其余登记必须留下。
    // 调用方用 `AtIndex(index)` 找到目标后把下标交进来，避免"找到了却摘错"。
    // 越界时返回 0 且不写 `removed`。
    std::uint32_t RemoveAtIndex(std::size_t index, CallbackDescriptor* removed = nullptr) noexcept;

    // Removes every callback owned by one Mod, for example on reload.
    std::uint32_t RemoveOwner(ModHandle owner) noexcept;

    [[nodiscard]] std::size_t Count() const noexcept { return count_; }
    [[nodiscard]] std::size_t CountOf(CallbackId id) const noexcept;

    // Returns the index-th registration of `id` in registration order, or
    // nullptr when there is no such entry.
    [[nodiscard]] const CallbackDescriptor* At(CallbackId id, std::size_t index) const noexcept;
    [[nodiscard]] const CallbackDescriptor* AtIndex(std::size_t index) const noexcept;

    void Reset() noexcept;

private:
    std::array<CallbackDescriptor, kCapacity> entries_{};
    //: 与 `entries_` **逐下标平行**的过滤器表（`entries_[i]` ↔ `filters_[i]`）。
    //: 任何改动 `entries_` 下标的操作（`RemoveAtIndex` / `RemoveOwner` / `Reset`）都必须同步动它，
    //: 否则"摘掉一条登记"会让剩下那些登记的过滤器整体错位 —— 症状是**别的回调静默不触发**
    //: （过滤值对不上），最难查的一类。
    std::array<std::int64_t, kCapacity> filters_{};
    //: 与 `entries_` **逐下标平行**的优先级表。与过滤器同一套办法（放进 `CallbackDescriptor`
    //: 会改"20 字节/项"的布局，读数工具与离线解码都得跟着改）。
    //: 派发时按它**升序稳定排序**：同优先级保持登记顺序。
    std::array<std::int32_t, kCapacity> priorities_{};
    std::size_t count_{0};
};

} // namespace isaac::runtime
