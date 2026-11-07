#pragma once

// 标题画面自绘入口要用的**按键查询候选顺序**（把内置菜单那套口径固化成代码 + 门禁）。
//
// ## 口径来自两处实测/查证
//
// 1. **2026-09-16 真机（021）**：引擎认的是**玩家自己的 `ControllerIndex`**（实测出现过 33），
//    猜 0/1 一律答"没按下"。⇒ 学到了就优先用它，别再猜。
// 2. **2026-09-22 静态查证**：游戏自己的菜单代码用的是 **`0xFFFFFFFF`（任意手柄）** ——
//    `Menu_Title::Update @0x41A4F0` 是 `mov w2,#-1`（controller）+ `mov w1,#0xE`（MENUCONFIRM）。
//    ⇒ 这个值必须进候选表（我们早期探针漏了它，付出了两轮真机的代价）。
// 3. **主菜单里没有玩家**（`Isaac.GetPlayer(0)` 拿不到）⇒ 候选表不能只依赖 `ControllerIndex`。
//
// ## 为什么要门禁
//
// 候选顺序错的表现是"在标题画面按键没反应"——**不报错、不崩**，只能靠人眼发现。
// 所以顺序、去重、上限这些事在这里用宿主用例钉死。

#include <cstdint>

namespace isaac::runtime {

// 候选上限：自学习值 + 玩家值 + 任意手柄 + 0..3 + 32..35 = 最多 10 个。
inline constexpr std::uint32_t kActionControllerCapacity = 10;
// 引擎自己菜单用的"任意手柄"。
inline constexpr std::uint32_t kAnyController = 0xFFFFFFFFu;

struct ActionControllerCandidates {
    std::uint32_t values[kActionControllerCapacity]{};
    std::uint32_t count{0};
};

// 按口径拼候选表：自学习值最先（学到就不再靠猜）→ 玩家自己的值 → `0xFFFFFFFF` → 兜底 0..3、32..35。
// 重复值只留第一次出现的位置（重复查询只会白花时间，而且会让"学到了哪个值"记错）。
[[nodiscard]] inline ActionControllerCandidates BuildActionControllerCandidates(
    std::uint32_t learned, bool hasLearned, std::uint32_t playerIndex,
    bool hasPlayer) noexcept {
    ActionControllerCandidates out{};
    const auto append = [&out](std::uint32_t value) {
        if (out.count >= kActionControllerCapacity) {
            return;
        }
        for (std::uint32_t i = 0; i < out.count; ++i) {
            if (out.values[i] == value) {
                return;
            }
        }
        out.values[out.count++] = value;
    };
    if (hasLearned) {
        append(learned);
    }
    if (hasPlayer) {
        append(playerIndex);
    }
    append(kAnyController);
    for (std::uint32_t fallback = 0; fallback <= 3; ++fallback) {
        append(fallback);
    }
    for (std::uint32_t fallback = 32; fallback <= 35; ++fallback) {
        append(fallback);
    }
    return out;
}

// 逐个候选问过去；谁答"是"就返回它（写进 `*learned`，之后优先问它），全否返回 false。
// `query` 的调用形状与 `input_api.cpp` 一致：接收者被跳板覆盖，实参是（动作号, controller, 出参）。
// `context` 原样传给 `query` 的第一个参数。真机上那个参数会被引擎跳板覆盖（所以传什么都行），
// 但把它透传出来是必须的 —— 否则宿主用例没法给假实现传状态（本项目刚踩过一次：传 `nullptr`
// 让假实现去解引用空指针，用例直接崩而不是判红）。
[[nodiscard]] inline bool PollActionPressed(
    bool (*query)(void*, std::uint32_t, std::uint32_t, void*), void* context,
    std::uint32_t action, const ActionControllerCandidates& candidates,
    std::uint32_t* learned) noexcept {
    if (query == nullptr) {
        return false;
    }
    for (std::uint32_t i = 0; i < candidates.count; ++i) {
        if (query(context, action, candidates.values[i], nullptr)) {
            if (learned != nullptr) {
                *learned = candidates.values[i];
            }
            return true;
        }
    }
    return false;
}

}  // namespace isaac::runtime
