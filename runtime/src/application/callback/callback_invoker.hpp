#pragma once

#include "domain/callback/callback_descriptor.hpp"
#include "domain/runtime/status.hpp"

#include <cstdint>

namespace isaac::runtime {

// 一次回调调用**读回来的返回值**。
//
// 为什么要分开记四件事，而不是压成一个 `bool blocked`：
//   * PC 上不同回调对返回值的解释不同 —— `MC_PRE_USE_ITEM` / `MC_PRE_PICKUP_COLLISION` 是
//     "返回 true 就拦"，`MC_PRE_GET_COLLECTIBLE` / `MC_POST_GET_COLLECTIBLE` 是"返回一个整数
//     替换道具"，`MC_USE_ITEM` 的 true/false 只影响"要不要播使用动画"（不拦）；
//   * `MC_POST_GET_COLLECTIBLE` 的官方文档写着"**若 `MC_PRE_GET_COLLECTIBLE` 返回了非 nil，
//     本条就跳过**" ⇒"返回过任何非 nil 值"本身是一个必须保留的事实，压成 bool 就丢了。
struct CallbackReturn {
    //: 这条回调确实被调到了（`InvokeCollecting` 在状态无效时保持 false）。
    bool called{false};
    //: 返回了任何非 nil 值（含 false、0）。
    bool nonNil{false};
    //: 返回了 Lua 的 `true`。
    bool truthy{false};
    //: 返回了一个整数（Lua 的 integer 子类型；`3.0` 这类浮点不算 —— 与既有
    //: `DispatchPreGetCollectible` 的口径一致，那一条是真机验过的）。
    bool hasInteger{false};
    //: `hasInteger` 为真时的值。
    std::int64_t integer{0};
};

// Calls one registered callback. The Lua adapter implements this interface, so
// the dispatcher never sees a lua_State and never links against Lua.
class ICallbackInvoker {
public:
    virtual ~ICallbackInvoker() = default;

    // A failure is isolated to this callback; the dispatcher keeps going.
    [[nodiscard]] virtual Status Invoke(const CallbackDescriptor& descriptor) noexcept = 0;

    // 同上，但**读回返回值**（PC 的"可改返回值"约定）。
    //
    // 与 `Invoke` 分成两个方法而不是给 `Invoke` 加一个出参：绝大多数派发点（36 种回调）
    // 明确不需要返回值，用 `Invoke` 就不必在调用点写 `nullptr`，也避免"顺手读了一个本来
    // 不该读的返回值"。做成纯虚而不是给默认实现：默认实现会把"这个实现方没读返回值"藏起来，
    // 而"读不读返回值"正是本轮要区分的语义（宿主侧只有一个假实现，改它一次即可）。
    [[nodiscard]] virtual Status InvokeCollecting(const CallbackDescriptor& descriptor,
                                                 CallbackReturn* result) noexcept = 0;
};

} // namespace isaac::runtime
