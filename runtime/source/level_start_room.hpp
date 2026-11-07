#pragma once

#include <cstdint>

namespace LuaRuntime {

// `Level:GetStartingRoomIndex()` 的派生实现。
//
// ## 为什么是"派生"而不是"读引擎字段"
//
// 引擎里**没有** `Level::GetStartingRoomIndex` 这个符号（符号表 16,361 条里没有；Ghidra 的
// 类型库里也没有该字段名；镜像里连 `GetStartingRoomIndex` 这个字符串都没有 —— Switch 版自带的
// Lua 胶水是 PC 的子集）。当时就把它记成"得先做字段/布局取证"，而 106 这一批把
// **能做的取证都做了**（符号表、Ghidra、RoomDescriptor 的 24 个标志、`RoomConfig::Room` 的字段、
// `Level/Game` 那一族偏移 0x215xx 的全镜像扫描）—— 都没有找到它 ⇒ **没有编造一个字段**。
//
// 于是改成记账：**本层第一次被看到的那个房间索引**就是"起始房间"。正常路径与 PC 一致
// （模组/运行时在开局或换层后第一次看到新层时，玩家正站在本层的起始房间里），
// 已知会偏的只有一种情形（写进 `api_deviation.cpp`）：运行时在"某一层中途"才加载
// （模组重载/换卡）时，记到的是我们第一次看到的那个房间。
//
// ## 为什么放在这里（而不是 API 层）
//
// 判据必须"每帧都在看"，而 `Level:GetStartingRoomIndex()` 是**模组按需调用**的 —— 如果等模组来问
// 才记，模组在房间 5 问一次就会把房间 5 记成起始房间。所以记账挂在**帧事件**那条路径上
// （`DispatchFrameEvents` 本来就在每帧读 `GameLocationKey`，里面就有 `roomIndex`）。
//
// 本类是**纯逻辑**（只吃三个整数、不碰引擎内存）⇒ 宿主可以直接测它的语义。
class LevelStartRoomTracker {
public:
    // "还不知道"的取值（也是还没观察到任何一层时 `Value()` 的返回值）。
    static constexpr std::uint32_t kUnknownRoomIndex = 0xFFFFFFFFu;

    // 每帧拿到当前身份后调一次。层号（stage + stageType）变了、或这是第一次
    // （`started_ == false`）时，把 `roomIndex` 记成本层的起始房间。
    void Observe(std::uint32_t stage, std::uint32_t stageType, std::uint32_t roomIndex) noexcept {
        if (started_ && stage == stage_ && stageType == stageType_) {
            return;  // 还是同一层：不动记录（这正是"起始"两个字的意思）
        }
        started_ = true;
        stage_ = stage;
        stageType_ = stageType;
        startRoom_ = roomIndex;
    }

    // 当前层的起始房间索引；还没观察到任何一层时给 `kUnknownRoomIndex`。
    [[nodiscard]] std::uint32_t Value() const noexcept { return startRoom_; }

    // 新建 Lua 会话时清空（与其它会话级状态同一个口径）。
    void Reset() noexcept {
        started_ = false;
        stage_ = 0;
        stageType_ = 0;
        startRoom_ = kUnknownRoomIndex;
    }

private:
    bool started_{false};
    std::uint32_t stage_{0};
    std::uint32_t stageType_{0};
    std::uint32_t startRoom_{kUnknownRoomIndex};
};

} // namespace LuaRuntime
