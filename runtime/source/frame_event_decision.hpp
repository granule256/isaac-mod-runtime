#pragma once

// 每帧"要不要派发 `MC_POST_NEW_LEVEL` / `MC_POST_NEW_ROOM`"的**纯判定**。
//
// ## 为什么单独抽出来（2026-09-22）
//
// 这两条事件的判定原本写在 `lua_runtime.cpp` 的 `DispatchFrameEvents()` 里，和"读身份、
// 扫实体、清表"混在一起 ⇒ 宿主上只能做**文本断言**（"那段代码还在"），验不了行为。
// 而这个判定最容易出的错恰恰是"**静默少派一次**"：不崩、不报错、模组那边只是少了一次事件。
//
// 真机症状（2026-09-22，用户报"重启后第一次进局正好在献祭房，EID 的房间信息不显示"）：
// 开局所在的那间房**从来没有**收到过 `NEW_LEVEL` / `NEW_ROOM` —— 旧代码的注释写得很清楚：
// "第一次读到身份时不判变化（那时这一局刚开局，`MC_POST_GAME_STARTED` 已经承担了'开局'）"。
// 但 PC 的语义不是这样：PC 在开局时**照发** `POST_NEW_LEVEL` → `POST_NEW_ROOM`
// （EID 的房间信息就是在 `POST_NEW_ROOM` 里算并画出来的），所以"第一次读到身份"必须补一次。
// 读数证据：那一局 `19 MC_POST_NEW_ROOM = 0 次`、`18 MC_POST_NEW_LEVEL = 0 次`，
// 而 `15 MC_POST_GAME_STARTED = 1 次` ⇒ 事件送到了，就是这两条没发。
//
// ## 口径（三条，逐条都有宿主用例）
//
// 1. **开局起始房间**：`initialRoomPending != 0` 且这一帧读到了身份 ⇒ 补派 `NEW_LEVEL` + `NEW_ROOM`
//    各一次，并告诉调用方"标志可以清了"。**顺序照 PC**：先 `NEW_LEVEL` 再 `NEW_ROOM`
//    （调用方按本结构体的字段顺序派发）。
// 2026-10-14 更正：上述历史顺序写反；PC 官方要求先 NEW_ROOM 再 NEW_LEVEL。
//    字段布局仅存判定结果，实际派发顺序由 DispatchFrameEvents 保证。
// 2. **中途读不到身份**：`haveLocation == false` ⇒ 什么都不派发，且**不清标志**
//    （下一帧重试；一次瞬时读失败不该把开局那次补派吞掉）。
// 3. **运行时在该层中途才加载**：`initialRoomPending == 0` 且 `roomKnown == 0` ⇒ 不判变化
//    （没有"上一次"可比，拿残值当身份会派发成"每帧一次"）。这条是原行为，保留。

#include <cstdint>

namespace isaac::runtime {

// 一帧的判定结果。字段顺序就是派发顺序（`newLevel` 在前，照 PC 的观感）。
// 2026-10-14 更正：上述字段顺序不代表派发顺序；实际先 newRoom 再 newLevel，字段布局保留。
struct FrameRoomDecision {
    bool newLevel;              // 派发 `MC_POST_NEW_LEVEL`
    bool newRoom;               // 派发 `MC_POST_NEW_ROOM`
    bool initialRoomConsumed;   // 调用方据此清掉"开局起始房间还没补派"的标志
};

// 纯判定：不读全局、不碰内存，只按传进来的事实回答"这一帧派什么"。
[[nodiscard]] constexpr FrameRoomDecision DecideFrameRoomEvents(
    bool haveLocation, bool roomKnown, bool levelKnown, bool sameStage, bool sameRoom,
    std::uint32_t initialRoomPending) noexcept {
    FrameRoomDecision decision{false, false, false};
    if (!haveLocation) {
        // 口径 2：读不到身份就什么都不判 —— 也**不消费**开局那次补派。
        return decision;
    }
    // 口径 3：只有"知道上一次身份"时才判变化。
    if (roomKnown && !sameRoom) {
        decision.newRoom = true;
    }
    if (levelKnown && !sameStage) {
        decision.newLevel = true;
        // 房号是层内索引；两个不同层的起始房可以恰好都是84。
        decision.newRoom = true;
    }
    // 口径 1：开局那间房补一次（放在最后，覆盖上面两条 —— 无论上面判出什么，
    // 开局这一次都必须发，而且只发一次）。
    if (initialRoomPending != 0) {
        decision.newLevel = true;
        decision.newRoom = true;
        decision.initialRoomConsumed = true;
    }
    return decision;
}

}  // namespace isaac::runtime
